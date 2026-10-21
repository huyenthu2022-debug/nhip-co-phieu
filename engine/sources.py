"""Lấy giá ngày từ các API công khai của công ty chứng khoán VN, không cần thư viện ngoài.

Thử lần lượt DNSE (Entrade), Vietcap, TCBS; nguồn nào trả dữ liệu trước thì dùng.
Các API này không có tài liệu chính thức nên có thể đổi bất cứ lúc nào.
"""
import json
import time
import urllib.request
from datetime import datetime, timedelta, timezone

import pandas as pd

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}
VN_TZ = timezone(timedelta(hours=7))


def _get(url, body=None, extra=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={**HEADERS, **(extra or {}),
                                                          **({"Content-Type": "application/json"} if data else {})})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def _frame(t, o, h, l, c, v):
    df = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": v},
                      index=pd.to_datetime(pd.Series(t, dtype="int64"), unit="s", utc=True)
                      .dt.tz_convert(VN_TZ).dt.tz_localize(None).dt.normalize())
    df = df.astype(float)
    return df[~df.index.duplicated(keep="last")].sort_index()


def dnse(sym, is_index, days):
    now = int(time.time())
    kind = "index" if is_index else "stock"
    j = _get(f"https://services.entrade.com.vn/chart-api/v2/ohlcs/{kind}"
             f"?from={now - days * 86400}&to={now}&symbol={sym}&resolution=1D")
    return _frame(j["t"], j["o"], j["h"], j["l"], j["c"], j["v"])


def vietcap(sym, is_index, days):
    j = _get("https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart",
             {"timeFrame": "ONE_DAY", "symbols": [sym], "to": int(time.time()) + 86400, "countBack": int(days * 0.7)},
             {"Referer": "https://trading.vietcap.com.vn/", "Origin": "https://trading.vietcap.com.vn"})
    d = j[0]
    return _frame([int(x) for x in d["t"]], d["o"], d["h"], d["l"], d["c"], d["v"])


def tcbs(sym, is_index, days):
    j = _get("https://apipubaws.tcbs.com.vn/stock-insight/v2/stock/bars-long-term"
             f"?ticker={sym}&type={'index' if is_index else 'stock'}&resolution=D"
             f"&to={int(time.time())}&countBack={int(days * 0.7)}")
    rows = j["data"]
    t = [int(datetime.fromisoformat(r["tradingDate"].replace("Z", "")[:19]).replace(tzinfo=VN_TZ).timestamp()) for r in rows]
    return _frame(t, [r["open"] for r in rows], [r["high"] for r in rows], [r["low"] for r in rows],
                  [r["close"] for r in rows], [r["volume"] for r in rows])


SOURCES = {"dnse": dnse, "vietcap": vietcap, "tcbs": tcbs}


def fetch(sym, is_index=False, days=365 * 3, order=("dnse", "vietcap", "tcbs")):
    """Trả về (DataFrame, tên nguồn). Giá cổ phiếu chuẩn hoá về nghìn đồng."""
    errors = []
    for name in order:
        try:
            df = SOURCES[name](sym, is_index, days)
            if len(df) < 30:
                raise ValueError(f"chỉ có {len(df)} phiên")
            if not is_index and df["close"].median() > 1000:  # nguồn trả giá theo đồng
                df[["open", "high", "low", "close"]] /= 1000
            return df, name
        except Exception as e:
            errors.append(f"{name}: {e}")
    raise RuntimeError("; ".join(errors))


# ---------- Danh sách toàn thị trường và giá theo lô ----------

VCI_HEADERS = {"Referer": "https://trading.vietcap.com.vn/", "Origin": "https://trading.vietcap.com.vn"}
BOARD = {"HSX": "HOSE", "HOSE": "HOSE", "HNX": "HNX", "UPCOM": "UPCOM"}


def _vnd_industries(level):
    """{mã: tên ngành tiếng Việt} theo phân ngành ICB cấp `level` của VNDirect."""
    j = _get(f"https://api-finfo.vndirect.com.vn/v4/industry_classification?q=industryLevel:{level}&size=200")
    out = {}
    for r in j["data"]:
        for sym in (r.get("codeList") or "").split(","):
            if sym.strip():
                out[sym.strip()] = r.get("vietnameseName") or r.get("englishName") or ""
    return out


def listing():
    """Mọi cổ phiếu đang niêm yết HOSE/HNX/UPCoM kèm ngành ICB cấp 2 và cấp 3 (tiếng Việt)."""
    allsym = _get("https://trading.vietcap.com.vn/api/price/symbols/getAll", extra=VCI_HEADERS)
    stocks = {r["symbol"]: {"exchange": BOARD[r.get("board")], "name": r.get("organShortName") or r.get("organName") or ""}
              for r in allsym
              if r.get("type") == "STOCK" and r.get("board") in BOARD and len(r.get("symbol", "")) == 3}
    try:
        sec2, sec3 = _vnd_industries(2), _vnd_industries(3)
    except Exception as e:
        print(f"  Không lấy được phân ngành ICB ({e})")
        sec2, sec3 = {}, {}
    out = [{"sym": sym, "exchange": s["exchange"], "name": s["name"],
            "sector": sec2.get(sym) or "Chưa phân ngành", "industry": sec3.get(sym) or ""}
           for sym, s in sorted(stocks.items())]
    if len(out) < 300:
        raise RuntimeError(f"danh sách quá ngắn ({len(out)} mã)")
    print(f"  Phân ngành: {sum(r['sector'] != 'Chưa phân ngành' for r in out)}/{len(out)} mã có ngành ICB")
    return out


def fetch_many(symbols, days=365 * 3, workers=10, log=print):
    """Giá cho nhiều mã, lấy song song. API Vietcap chỉ trả đúng khi hỏi từng mã một."""
    from concurrent.futures import ThreadPoolExecutor

    prices, used, failed = {}, {}, []

    def one(s):
        try:
            return s, *fetch(s, days=days, order=("vietcap", "dnse", "tcbs"))
        except Exception:
            return s, None, None
    t0 = time.time()
    with ThreadPoolExecutor(workers) as ex:
        for k, (s, df, src) in enumerate(ex.map(one, symbols), 1):
            if df is not None:
                prices[s] = df
                used[src] = used.get(src, 0) + 1
            else:
                failed.append(s)
            if k % 200 == 0:
                log(f"  {k}/{len(symbols)} mã, {time.time() - t0:.0f}s")
    log(f"Nguồn đã dùng: {used}; lấy được {len(prices)}/{len(symbols)} mã; lỗi {len(failed)}: {' '.join(failed[:30])}")
    return prices
