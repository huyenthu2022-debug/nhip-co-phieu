"""Kiểm tra bảng giá CafeF theo từng sàn từ máy chủ GitHub."""
import json
import urllib.request

for c in (1, 2, 3, 9):
    url = f"https://banggia.cafef.vn/stockhandler.ashx?center={c}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Origin": "https://huyenthu2022-debug.github.io"})
        with urllib.request.urlopen(req, timeout=20) as r:
            j = json.loads(r.read().decode())
        live = [x for x in j if x.get("l")]
        print(f"center={c}: {len(j)} mã, {len(live)} có giá khớp; mẫu:", [(x["a"], x.get("b"), x.get("l"), x.get("n"), x.get("Time")) for x in j[:4]])
        for s in ("FPT", "SHS", "BSR", "VCB", "PVS"):
            m = [x for x in j if x.get("a") == s]
            if m:
                print("   ", s, {k: m[0][k] for k in ("b", "l", "k", "n", "v", "w", "Time") if k in m[0]})
    except Exception as e:
        print(f"center={c}: LỖI {e}")
