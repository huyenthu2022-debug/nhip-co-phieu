"""So sánh mức chốt lời (R:R) cho cùng điểm vào hiện tại trên 2 năm PAXG/USDT và 60 ngày GC=F."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import gold  # noqa: E402


def prep(h1r, m15r):
    m15 = gold.add_sweep(gold.add_ind(m15r))
    h1 = gold.add_ind(h1r)
    h4 = gold.add_ind(h1r.resample("4h", origin="epoch").agg(gold.OHLC).dropna())
    h4tr = gold.closed_on(h4.apply(gold.trend_of, axis=1), pd.Timedelta(hours=4), m15.index).fillna("Đi ngang")
    zone = gold.closed_on(gold.h1_zones(h1), pd.Timedelta(hours=1), m15.index).fillna("")
    b, s = gold.setups(m15, h4tr, zone)
    return m15, b, s


def bt(m15, b, s, tp, be, start):
    HI, LO, CL = (m15[k].to_numpy() for k in ("high", "low", "close"))
    res, pos = [], None
    for i in range(start, len(m15)):
        if pos:
            d, e, R = pos
            fav, adv = (HI[i], LO[i]) if d > 0 else (LO[i], HI[i])
            sl = pos_sl[0]
            out = None
            if d * (adv - sl) <= 0:
                out = d * (sl - e) / R
            elif d * (fav - e) / R >= tp:
                out = tp
            elif be and d * (fav - e) / R >= be:
                pos_sl[0] = e
            if out is not None:
                res.append(out)
                pos = None
                continue
        if pos is None and (b[i] or s[i]):
            p = gold.plan("MUA" if b[i] else "BÁN", i, m15)
            d = 1 if b[i] else -1
            pos = (d, p["entry"], p["risk"])
            pos_sl = [p["sl"]]
    r = np.array(res)
    return r


def line(name, r):
    eq = np.cumsum(r)
    dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max()
    pf = r[r > 0].sum() / max(-r[r < 0].sum(), 1e-9)
    print(f"{name:18s} n={len(r):3d} thắng={(r > 0).mean() * 100:5.1f}% hoà={(r == 0).mean() * 100:5.1f}% "
          f"thua={(r < 0).mean() * 100:5.1f}% avg={r.mean():+.2f}R tot={r.sum():+6.1f}R pf={pf:.2f} dd={dd:4.1f}R")


spot, _ = gold.spot_price()
sets = [("PAXG 2 năm", *prep(gold.binance("1h", 20000), gold.binance("15m", 70000)), 2000)]
gh1, _ = gold.shift_to_spot(gold.clean(gold.yahoo("1h", "730d")), spot)
gm15, _ = gold.shift_to_spot(gold.clean(gold.yahoo("15m", "60d")), spot)
sets.append(("GC=F 60 ngày", *prep(gh1, gm15), 200))
for tag, m15, b, s, start in sets:
    print("#####", tag)
    for be in (None, 1.0):
        for tp in (1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0):
            if be and tp <= be:
                continue
            line(f"1:{tp:g} {'hoà vốn 1:1' if be else 'không dời'}", bt(m15, b, s, tp, be, start))
