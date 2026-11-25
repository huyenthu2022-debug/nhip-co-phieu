"""Kiểm định hệ 1 mới (vào ngay sau quét, SL 10–15) trên dữ liệu thật, và so khớp với bản JS trên web."""
import json, subprocess, sys, warnings
warnings.filterwarnings("ignore")
from collections import Counter
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
import gold  # noqa: E402

def run(h1r, m15r, start):
    m = gold.add_sweep(gold.add_ind(m15r)); h1 = gold.add_ind(h1r)
    h4 = gold.add_ind(h1r.resample("4h", origin="epoch").agg(gold.OHLC).dropna())
    t4 = gold.closed_on(h4.apply(gold.trend_of, axis=1), pd.Timedelta(hours=4), m.index).fillna("Đi ngang")
    z = gold.closed_on(gold.h1_zones(h1), pd.Timedelta(hours=1), m.index).fillna("")
    side, wick, lvl, kind, risk, watch = gold.setups(m, t4, z)
    tr, pos = gold.backtest(m, side, lvl, kind, risk, start=start)
    return tr, side, m, h1, h4

def rep(name, tr):
    if not tr:
        print(name, "không có lệnh"); return
    raw = np.array([t["r"] for t in tr]); rk = np.array([abs(t["entry"] - t["sl"]) for t in tr]); net = raw - 0.35 / rk
    eq = np.cumsum(net); dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max()
    idx = pd.DatetimeIndex([t["t_in"] for t in tr]); months = max((idx[-1] - idx[0]).days / 30.4, 1)
    q = pd.Series(net, index=idx).groupby(idx.tz_convert(None).to_period("Q")).sum(); h = len(net) // 2
    print(f"{name}: {len(tr)} lệnh ({len(tr)/months:.1f}/tháng) thắng {(raw>0).mean()*100:.0f}% hoà {(raw==0).mean()*100:.0f}% thua {(raw<0).mean()*100:.0f}% "
          f"| thắng TB {raw[raw>0].mean():.2f}R | TB thô {raw.mean():+.2f}R sau phí {net.mean():+.2f}R tổng {net.sum():+.1f}R "
          f"pf {net[net>0].sum()/-net[net<0].sum():.2f} dd {dd:.1f} | nửa {net[:h].sum():+.0f}/{net[h:].sum():+.0f} quý lãi {(q>0).sum()}/{len(q)} | SL TB {rk.mean():.1f}")
    for k, c in Counter(t["kind"] for t in tr).most_common():
        r = np.array([t["r"] for t in tr if t["kind"] == k]); print(f"    {k}: {c} lệnh, TB {r.mean():+.2f}R, tổng {r.sum():+.1f}R")

rep("PAXG 2 năm", run(gold.binance("1h", 20000), gold.binance("15m", 70000), 2000)[0])
spot, _ = gold.spot_price()
gh1, _ = gold.shift_to_spot(gold.clean(gold.yahoo("1h", "730d")), spot)
gm15, _ = gold.shift_to_spot(gold.clean(gold.yahoo("15m", "60d")), spot)
rep("GC=F 60 ngày", run(gh1, gm15, 200)[0])

# So khớp JS: 1000 nến M15, 500 H1 của PAXG gần nhất
ph1, pm15 = gold.binance("1h", 2000), gold.binance("15m", 3000)
m15r, h1r = pm15.tail(1000), ph1.tail(500)
h4r = h1r.resample("4h", origin="epoch").agg(gold.OHLC).dropna()
js = lambda df: {"t": [int(x.timestamp()) for x in df.index], **{k[0]: df[k].tolist() for k in ("open", "high", "low", "close")}}
Path("/tmp/bars.json").write_text(json.dumps({"m15": js(m15r), "h1": js(h1r), "h4": js(h4r)}))
out = json.loads(subprocess.check_output(["node", "engine/rt_check.js", "web/gold.js", "/tmp/bars.json"]))
tr, side, m, _, _ = run(h1r, m15r, 200)
py = [int(t["t_in"].timestamp()) for t in tr]
ps = sorted(int(x.timestamp()) for x in m.index[side != 0])
print(f"JS so với Python: lệnh {len(out['trades'])}/{len(py)} khớp={out['trades'] == py}; tín hiệu {len(out['sigs'])}/{len(ps)} khớp={sorted(out['sigs']) == ps}")
print("JS trạng thái:", out["status"], "| mở:", out["open"], "| piv:", out["piv"])

# Chạy engine đầy đủ
data = gold.build(gh1, gm15, {"source": "GC=F", "spot_source": "gold-api", "spot": spot, "basis": 0})
print("Engine:", data["status"], "| mở:", data["open"], "| piv:", data["piv"])
print("Thống kê web:", data["stats"]); print("3 lệnh gần nhất:", data["trades"][:3])
