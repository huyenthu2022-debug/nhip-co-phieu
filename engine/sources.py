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


def listing():
    """Mọi cổ phiếu đang niêm yết HOSE/HNX/UPCoM kèm ngành ICB cấp 2 và cấp 3 (tiếng Việt)."""
    allsym = _get("https://trading.vietcap.com.vn/api/price/symbols/getAll", extra=VCI_HEADERS)
    stocks = {r["symbol"]: {"exchange": BOARD[r.get("board")], "name": r.get("organName") or ""}
              for r in allsym
              if r.get("type") == "STOCK" and r.get("board") in BOARD and len(r.get("symbol", "")) == 3}
    q = "{ CompaniesListingInfo { ticker organName icbName2 icbName3 } }"
    info = _get("https://trading.vietcap.com.vn/data-mt/graphql", {"query": q, "variables": {}}, VCI_HEADERS)
    icb = {r["ticker"]: r for r in info["data"]["CompaniesListingInfo"]}
    out = []
    for sym, s in sorted(stocks.items()):
        r = icb.get(sym) or {}
        out.append({"sym": sym, "exchange": s["exchange"], "name": r.get("organName") or s["name"],
                    "sector": r.get("icbName2") or "Chưa phân ngành", "industry": r.get("icbName3") or ""})
    if len(out) < 300:
        raise RuntimeError(f"danh sách quá ngắn ({len(out)} mã)")
    return out


def vietcap_batch(symbols, days):
    """Một yêu cầu trả về giá nhiều mã cùng lúc."""
    j = _get("https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart",
             {"timeFrame": "ONE_DAY", "symbols": list(symbols), "to": int(time.time()) + 86400,
              "countBack": int(days * 0.7)}, VCI_HEADERS)
    out = {}
    for d in j:
        if d.get("t"):
            out[d["symbol"]] = _frame([int(x) for x in d["t"]], d["o"], d["h"], d["l"], d["c"], d["v"])
    return out


def fetch_many(symbols, days=365 * 3, batch=40, workers=8, log=print):
    """Giá cho nhiều mã: lấy theo lô từ Vietcap, mã nào thiếu thì lấy lẻ song song từ DNSE/TCBS."""
    from concurrent.futures import ThreadPoolExecutor

    prices, used = {}, {}
    for i in range(0, len(symbols), batch):
        chunk = symbols[i:i + batch]
        try:
            got = vietcap_batch(chunk, days)
            for s, df in got.items():
                if len(df) >= 30:
                    if df["close"].median() > 1000:
                        df[["open", "high", "low", "close"]] /= 1000
                    prices[s] = df
                    used["vietcap"] = used.get("vietcap", 0) + 1
        except Exception as e:
            log(f"  lô {i // batch + 1}: Vietcap lỗi ({e})")
        time.sleep(0.3)
    missing = [s for s in symbols if s not in prices]
    log(f"Vietcap theo lô: {len(prices)}/{len(symbols)} mã, lấy lẻ {len(missing)} mã còn lại")

    def one(s):
        try:
            return s, *fetch(s, days=days, order=("dnse", "tcbs"))
        except Exception:
            return s, None, None
    with ThreadPoolExecutor(workers) as ex:
        for s, df, src in ex.map(one, missing):
            if df is not None:
                prices[s] = df
                used[src] = used.get(src, 0) + 1
    log(f"Nguồn đã dùng: {used}; tổng {len(prices)}/{len(symbols)} mã")
    return prices
