"""Kiểm tra các nguồn giá vàng XAUUSD từ máy chủ GitHub (dữ liệu + CORS cho trình duyệt)."""
import urllib.request

ORIGIN = "https://huyenthu2022-debug.github.io"
URLS = [
    "https://query1.finance.yahoo.com/v8/finance/chart/XAUUSD=X?interval=1h&range=5d",
    "https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=1h&range=5d",
    "https://query2.finance.yahoo.com/v8/finance/chart/GC=F?interval=1h&range=730d",
    "https://stooq.com/q/d/l/?s=xauusd&i=d",
    "https://stooq.com/q/l/?s=xauusd&f=sd2t2ohlc&h&e=csv",
    "https://data-api.binance.vision/api/v3/klines?symbol=PAXGUSDT&interval=1h&limit=3",
    "https://api.gold-api.com/price/XAU",
    "https://data-asg.goldprice.org/dbXRates/USD",
    "https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/XAU/USD",
]
for url in URLS:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Origin": ORIGIN})
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read().decode(errors="replace")
            print(f"OK {r.status} cors={r.headers.get('Access-Control-Allow-Origin')} len={len(body)} {url}")
            print("    ", body[:300].replace("\n", " | "))
    except Exception as e:
        print(f"LỖI {url}: {e}")
