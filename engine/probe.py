"""So khớp tín hiệu realtime trong trình duyệt (web/gold.js) với engine Python trên cùng nến PAXG/USDT."""
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import gold  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def kl(iv, n):
    now = pd.Timestamp.now(tz="UTC").value // 10**6
    k = [x for x in gold._get(f"https://data-api.binance.vision/api/v3/klines?symbol=PAXGUSDT&interval={iv}&limit={n}") if x[6] < now]
    js = {"t": [x[0] / 1000 for x in k], **{c: [float(x[j]) for x in k] for c, j in (("o", 1), ("h", 2), ("l", 3), ("c", 4))}}
    df = pd.DataFrame({"open": js["o"], "high": js["h"], "low": js["l"], "close": js["c"], "volume": 0.0},
                      index=pd.to_datetime(js["t"], unit="s", utc=True))
    return js, df


(j15, m), (j1, h1), (j4, h4) = kl("15m", 1000), kl("1h", 500), kl("4h", 1000)
Path("/tmp/k.json").write_text(json.dumps({"m15": j15, "h1": j1, "h4": j4}))
js = json.loads(subprocess.run(["node", str(ROOT / "engine/rt_check.js"), str(ROOT / "web/gold.js"), "/tmp/k.json"],
                               capture_output=True, text=True, check=True).stdout)

m = gold.add_sweep(gold.add_ind(m))
h1i, h4i = gold.add_ind(h1), gold.add_ind(h4)
h4tr = gold.closed_on(h4i.apply(gold.trend_of, axis=1), pd.Timedelta(hours=4), m.index).fillna("Đi ngang")
zone = gold.closed_on(gold.h1_zones(h1i), pd.Timedelta(hours=1), m.index).fillna("")
buy, sell = gold.setups(m, h4tr, zone)
trades, pos = gold.backtest(m, buy, sell, start=200)
py_sigs = [int(t.timestamp()) for t, b_, s_ in zip(m.index, buy, sell) if b_ or s_]
py_tr = [int(x["t_in"].timestamp()) for x in trades]
print("Tín hiệu  Python:", len(py_sigs), " JS:", len(js["sigs"]), " khớp:", py_sigs == [int(x) for x in js["sigs"]])
print("Lệnh      Python:", len(py_tr), " JS:", len(js["trades"]), " khớp:", py_tr == [int(x) for x in js["trades"]])
print("Lệnh mở   Python:", pos and (pos["side"], gold.iso(pos["t_in"]), round(pos["sl"], 2)), " JS:", js["open"])
print("Khung JS:", js["tf"], js["status"], "RSI", js["rsi_m15"], js["rsi_h1"], "nến", js["bar"])
print("Python RSI cuối:", round(m["rsi"].iloc[-1], 2), round(h1i["rsi"].iloc[-1], 2))
print("Tín hiệu gần nhất (giờ VN):", [gold.iso(pd.Timestamp(t, unit="s", tz="UTC")) for t in py_sigs[-6:]])
print("Khác nhau:", sorted(set(py_sigs) ^ {int(x) for x in js["sigs"]})[:10])

# Kiểm định engine sau khi thêm lọc chất lượng
gold.TP_R = 3.0
spot, _ = gold.spot_price()
for tag, h1r, m15r, start in (("PAXG 2 năm", gold.binance("1h", 20000), gold.binance("15m", 70000), 2000),
                               ("GC=F 60 ngày", gold.shift_to_spot(gold.clean(gold.yahoo("1h", "730d")), spot)[0],
                                gold.shift_to_spot(gold.clean(gold.yahoo("15m", "60d")), spot)[0], 200)):
    mm = gold.add_sweep(gold.add_ind(m15r))
    hh = gold.add_ind(h1r)
    h44 = gold.add_ind(h1r.resample("4h", origin="epoch").agg(gold.OHLC).dropna())
    t4s = gold.closed_on(h44.apply(gold.trend_of, axis=1), pd.Timedelta(hours=4), mm.index).fillna("Đi ngang")
    zs = gold.closed_on(gold.h1_zones(hh), pd.Timedelta(hours=1), mm.index).fillna("")
    bb, ss = gold.setups(mm, t4s, zs)
    tr, _ = gold.backtest(mm, bb, ss, start)
    print(tag, gold.stats(tr), "| 5 lệnh gần nhất:", [(gold.iso(x["t_in"]), x["side"], x["reason"], x["r"]) for x in tr[-5:]])
h1, m15, meta = gold.fetch_real()
d = gold.build(h1, m15, meta)
print("build OK:", d["status"], d["stats"])
