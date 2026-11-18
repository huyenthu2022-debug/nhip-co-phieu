"""Kiểm tra bảng giá CafeF: đủ các trường của một mã, chỉ số, rổ VN30."""
import json
import urllib.request

H = {"User-Agent": "Mozilla/5.0", "Origin": "https://huyenthu2022-debug.github.io"}


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=20) as r:
        return r.headers.get("Access-Control-Allow-Origin"), r.read().decode("utf-8", "replace")


for c in (1, 2, 9):
    try:
        acao, body = get(f"https://banggia.cafef.vn/stockhandler.ashx?center={c}")
        j = json.loads(body)
        print(f"center={c} ACAO={acao} n={len(j)}")
        for s in ("FPT", "VCB", "SHS", "BSR", "HPG"):
            m = [x for x in j if x.get("a") == s]
            if m:
                print("  ", json.dumps(m[0], ensure_ascii=False))
    except Exception as e:
        print(f"center={c}: LỖI {e}")

for url in [
    "https://banggia.cafef.vn/stockhandler.ashx?index=true",
    "https://banggia.cafef.vn/stockhandler.ashx?center=1&index=true",
    "https://banggia.cafef.vn/stockhandler.ashx?center=vn30",
    "https://banggia.cafef.vn/stockhandler.ashx?center=11",
    "https://banggia.cafef.vn/stockhandler.ashx?center=3",
    "https://iboard-query.ssi.com.vn/v2/stock/group/VN30",
    "https://iboard-query.ssi.com.vn/exchange-index/VNINDEX",
    "https://trading.vietcap.com.vn/api/price/symbols/getByGroup?group=VN30",
    "https://bgapidatafeed.vps.com.vn/getlistckindex/hose",
    "https://bgapidatafeed.vps.com.vn/getlistindexdetail/10,02,03,11",
]:
    try:
        acao, body = get(url)
        print(f"== ACAO={acao} {url}\n   {body[:700]}")
    except Exception as e:
        print(f"== LỖI {e} {url}")
