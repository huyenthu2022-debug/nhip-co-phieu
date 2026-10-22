"""Kiểm tra API nào cho phép trình duyệt (CORS) lấy giá trực tiếp từ trang github.io."""
import urllib.error
import urllib.request

ORIGIN = "https://huyenthu2022-debug.github.io"
URLS = [
    ("GET", "https://services.entrade.com.vn/chart-api/v2/ohlcs/stock?from=1792000000&to=1793000000&symbol=FPT&resolution=1D"),
    ("GET", "https://trading.vietcap.com.vn/api/price/symbols/getAll"),
    ("GET", "https://iboard-query.ssi.com.vn/stock/exchange/hose"),
    ("GET", "https://iboard-query.ssi.com.vn/v2/stock/group/VN30"),
    ("GET", "https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/second-tc-price?tickers=FPT,HPG"),
    ("GET", "https://api-finfo.vndirect.com.vn/v4/stock_prices?sort=date&q=code:FPT&size=1"),
    ("GET", "https://bgapidatafeed.vps.com.vn/getliststockdata/FPT,HPG"),
    ("GET", "https://banggia.cafef.vn/stockhandler.ashx?center=1"),
]
for method, url in URLS:
    req = urllib.request.Request(url, headers={"Origin": ORIGIN, "User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read(300).decode("utf-8", "replace")
            print(f"== {r.status} ACAO={r.headers.get('Access-Control-Allow-Origin')} {url}\n   {body[:250]}")
    except urllib.error.HTTPError as e:
        print(f"== {e.code} ACAO={e.headers.get('Access-Control-Allow-Origin')} {url}")
    except Exception as e:
        print(f"== LỖI {e} {url}")
