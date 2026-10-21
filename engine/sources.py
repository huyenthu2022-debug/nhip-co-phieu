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
