"""So sánh cách dừng lỗ, bộ lọc và cách chốt lời của hệ 3 khung trên 2 năm PAXG/USDT M15."""
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import gold  # noqa: E402

m15 = gold.add_ind(gold.binance("15m", 70000))
h1r = gold.binance("1h", 20000)
h1 = gold.add_ind(h1r)
h4 = gold.add_ind(h1r.resample("4h", origin="epoch").agg(gold.OHLC).dropna())
d1 = gold.add_ind(h1r.resample("1D").agg(gold.OHLC).dropna())
H1, H4 = pd.Timedelta(hours=1), pd.Timedelta(hours=4)
h4tr = gold.closed_on(h4.apply(gold.trend_of, axis=1), H4, m15.index).fillna("Đi ngang")
zone = gold.closed_on(gold.h1_zones(h1), H1, m15.index).fillna("")
d1up = gold.closed_on(d1["close"] > d1["ema50"], pd.Timedelta(days=1), m15.index).fillna(False).astype(bool).to_numpy()
h1lo = gold.closed_on(h1["low"].rolling(6).min(), H1, m15.index).to_numpy()
h1hi = gold.closed_on(h1["high"].rolling(6).max(), H1, m15.index).to_numpy()
a1 = gold.closed_on(h1["atr"], H1, m15.index).to_numpy()
B0, S0 = gold.setups(m15, h4tr, zone)
HI, LO, CL, ATR = (m15[k].to_numpy() for k in ("high", "low", "close", "atr"))
T = m15.index
N = len(m15)
half = T[N // 2]


def risk_of(side, i, sl):
    e, a = CL[i], ATR[i]
    if sl == "h1":
        r = (e - h1lo[i] + 0.2 * a1[i]) if side > 0 else (h1hi[i] - e + 0.2 * a1[i])
        return min(max(r, 1.0 * a), 10 * a)
    lo, hi = LO[max(0, i - 11):i + 1].min(), HI[max(0, i - 11):i + 1].max()
    r = (e - lo + 0.3 * a) if side > 0 else (hi - e + 0.3 * a)
    return min(max(r, 1.0 * a), 4 * a)


def bt(sl, d1f, mg):
    """mg: ('part', tp1, tp2)  chốt 1/2 ở tp1 rồi dời SL về giá vào, phần còn lại ở tp2
           ('one', tp)         một mục tiêu
           ('be', tp)          một mục tiêu, chạm 1R thì dời SL về giá vào
           ('trail', k)        chạm 1R dời SL về giá vào, sau đó kéo SL cách giá k*ATR M15, không mục tiêu
           ('ptrail', tp1, k)  chốt 1/2 ở tp1 (SL về giá vào), phần còn lại kéo SL cách giá k*ATR"""
    b, s = B0.copy(), S0.copy()
    if d1f:
        b, s = b & d1up, s & ~d1up
    res, pos = [], None
    for i in range(2000, N):
        if pos:
            d, e, R = pos["d"], pos["e"], pos["R"]
            fav = HI[i] if d > 0 else LO[i]
            adv = LO[i] if d > 0 else HI[i]
            out = None
            if d * (adv - pos["sl"]) <= 0:  # chạm SL (tính trước, thận trọng)
                out = pos["bank"] + pos["w"] * d * (pos["sl"] - e) / R
            else:
                kind = mg[0]
                best = d * (fav - e) / R
                if kind in ("part", "ptrail") and not pos["t1"] and best >= mg[1]:
                    pos["t1"], pos["bank"], pos["w"], pos["sl"] = True, 0.5 * mg[1], 0.5, e
                if kind == "part" and best >= mg[2]:
                    out = pos["bank"] + pos["w"] * mg[2]
                if kind in ("one", "be") and best >= mg[1]:
                    out = mg[1]
                if kind in ("be", "trail") and best >= 1 and d * (pos["sl"] - e) < 0:
                    pos["sl"] = e
                if (kind == "trail" and best >= 1) or (kind == "ptrail" and pos["t1"]):
                    k = mg[1] if kind == "trail" else mg[2]
                    cand = fav - d * k * ATR[i]
                    if d * (cand - pos["sl"]) > 0:
                        pos["sl"] = cand
            if out is not None:
                res.append((pos["t"], pos["d"], out))
                pos = None
                continue
        if pos is None and (b[i] or s[i]):
            d = 1 if b[i] else -1
            pos = {"d": d, "e": CL[i], "R": risk_of(d, i, sl), "t": T[i], "t1": False, "bank": 0.0, "w": 1.0}
            pos["sl"] = pos["e"] - d * pos["R"]
    return res


def summ(res):
    if not res:
        return "n=0"
    r = np.array([x[2] for x in res])
    eq = np.cumsum(r)
    dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max()
    h1_, h2_ = sum(x[2] for x in res if x[0] < half), sum(x[2] for x in res if x[0] >= half)
    buy, sell = sum(x[2] for x in res if x[1] > 0), sum(x[2] for x in res if x[1] < 0)
    pf = r[r > 0].sum() / max(-r[r < 0].sum(), 1e-9)
    win = r[r > 0]
    return (f"n={len(r):3d} win={(r > 0).mean() * 100:4.1f}% avgwin={win.mean() if len(win) else 0:.2f}R avg={r.mean():+.2f}R "
            f"tot={r.sum():+6.1f}R pf={pf:.2f} dd={dd:4.1f} | nửa1 {h1_:+.1f} nửa2 {h2_:+.1f} | MUA {buy:+.1f} BÁN {sell:+.1f}")


MG = [("part", 2, 3), ("one", 2), ("one", 3), ("one", 4), ("be", 3), ("be", 4),
      ("trail", 2.0), ("trail", 3.0), ("ptrail", 2, 2.0), ("ptrail", 2, 3.0)]
print("dữ liệu M15:", T[0], "→", T[-1], N, "nến; nửa sau từ", half)
for sl, d1f, mg in itertools.product(("m15", "h1"), (False, True), MG):
    print(f"SL {sl:3s} D1 {'có' if d1f else '–':2s} {str(mg):18s}", summ(bt(sl, d1f, mg)))
