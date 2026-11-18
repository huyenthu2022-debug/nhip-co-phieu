"""Chạy thử engine vàng với dữ liệu thật từ máy chủ GitHub."""
import json
import runpy
import sys
from pathlib import Path

sys.argv = ["gold.py"]
runpy.run_path(str(Path(__file__).parent / "gold.py"), run_name="__main__")
d = json.loads((Path(__file__).resolve().parent.parent / "web/data/gold.json").read_text())
print("liq", d["liq"], "stats", d["stats"])
for t in d["trades"][:8]:
    print(t)
