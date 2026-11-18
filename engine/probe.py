"""Chạy thử engine vàng với dữ liệu thật từ máy chủ GitHub."""
import json
import runpy
import sys
from pathlib import Path

sys.argv = ["gold.py"]
runpy.run_path(str(Path(__file__).parent / "gold.py"), run_name="__main__")
d = json.loads((Path(__file__).resolve().parent.parent / "web/data/gold.json").read_text())
print({k: d[k] for k in ("source", "spot_source", "spot", "basis", "price", "day_chg", "trend", "fresh", "open", "stats", "stats_90d")})
for t in d["trades"][:8]:
    print(t)
print("h1 bars", len(d["h1"]["t"]), "h4 bars", len(d["h4"]["t"]))
