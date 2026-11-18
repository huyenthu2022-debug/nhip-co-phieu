"""So sánh cách đặt cắt lỗ hẹp (15–20 giá) cho hệ 3 khung trên 2 năm PAXG/USDT M15."""
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
H1, H4 = pd.Timedelta(hours=1), pd.Timedelta(hours=4)
h4tr = gold.closed_on(h4.apply(gold.trend_of, axis=1), H4, m15.index).fillna("Đi ngang")
zone = gold.closed_on(gold.h1_zones(h1), H1, m15.index).fillna("")
h1lo = gold.closed_on(h1["low"].rolling(6).min(), H1, m15.index).to_numpy()
h1hi = gold.closed_on(h1["high"].rolling(6).max(), H1, m15.index).to_numpy()
a1 = gold.closed_on(h1["atr"], H1, m15.index).to_numpy()
B, S = gold.setups(m15, h4tr, zone)
HI, LO, CL, ATR = (m15[k].to_numpy() for k in ("high", "low", "close", "atr"))
T = m15.index
N = len(m15)
half = T[N // 2]
REF = 3850.0  # giá hiện tại: quy đổi "giá" sang % để công bằng với giai đoạn vàng còn rẻ hơn


def swing_risk(d, i):
    r = (CL[i] - h1lo[i] + 0.2 * a1[i]) if d > 0 else (h1hi[i] - CL[i] + 0.2 * a1[i])
    return min(max(r, ATR[i]), 10 * ATR[i])


def bt(mode, lo_usd=None, hi_usd=None, be=1.0, tp=4.0):
    res, pos, skipped = [], None, 0
    for i in range(2000, N):
        if pos:
            d, e, R = pos["d"], pos["e"], pos["R"]
            fav, adv = (HI[i], LO[i]) if d > 0 else (LO[i], HI[i])
            out = None
            if d * (adv - pos["sl"]) <= 0:
                out = d * (pos["sl"] - e) / R
            elif d * (fav - e) / R >= tp:
                out = tp
            elif d * (fav - e) / R >= be:
                pos["sl"] = e
            if out is not None:
                res.append((pos["t"], d, out, R / CL[pos["i"]] * REF))
                pos = None
                continue
        if pos is None and (B[i] or S[i]):
            d = 1 if B[i] else -1
            scale = CL[i] / REF  # 20 giá ở giá 3850 = 0,52%
            lo, hi = (lo_usd or 0) * scale, (hi_usd or 1e9) * scale
            sw = swing_risk(d, i)
            if mode == "swing":
                R = sw
            elif mode == "cap":          # SL theo đáy/đỉnh H1 nhưng không rộng quá hi, không hẹp quá lo
                R = min(max(sw, lo), hi)
            elif mode == "skip":         # SL theo đáy/đỉnh H1, bỏ lệnh nếu rộng quá hi
                if sw > hi:
                    skipped += 1
                    continue
                R = max(sw, lo)
            else:                        # cố định
                R = hi
            pos = {"d": d, "e": CL[i], "R": R, "t": T[i], "i": i}
            pos["sl"] = CL[i] - d * R
    return res, skipped


def summ(res, skipped):
    r = np.array([x[2] for x in res])
    eq = np.cumsum(r)
    dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max()
    h1_, h2_ = sum(x[2] for x in res if x[0] < half), sum(x[2] for x in res if x[0] >= half)
    pf = r[r > 0].sum() / max(-r[r < 0].sum(), 1e-9)
    sl = np.array([x[3] for x in res])
    return (f"n={len(r):3d} bỏ={skipped:3d} thắng={(r > 0).mean() * 100:4.1f}% hoà={(r == 0).mean() * 100:4.1f}% "
            f"avg={r.mean():+.2f}R tot={r.sum():+6.1f}R pf={pf:.2f} dd={dd:4.1f}R | nửa1 {h1_:+.1f} nửa2 {h2_:+.1f} | "
            f"SL TB {sl.mean():.1f} giá (trung vị {np.median(sl):.1f})")


CASES = [
    ("Hiện tại: SL đáy/đỉnh H1", ("swing",), {}),
    ("Giới hạn SL 15–20 giá", ("cap", 15, 20), {}),
    ("Giới hạn SL ≤ 20 giá", ("cap", None, 20), {}),
    ("Bỏ lệnh SL > 20, tối thiểu 15", ("skip", 15, 20), {}),
    ("Bỏ lệnh SL > 25", ("skip", None, 25), {}),
    ("SL cố định 15 giá", ("fixed", None, 15), {}),
    ("SL cố định 18 giá", ("fixed", None, 18), {}),
    ("SL cố định 20 giá", ("fixed", None, 20), {}),
    ("Giới hạn 15–20, chốt 1:3", ("cap", 15, 20), {"tp": 3.0}),
    ("SL cố định 20, chốt 1:3", ("fixed", None, 20), {"tp": 3.0}),
]
print("dữ liệu:", T[0], "→", T[-1], "| nửa sau từ", half, "| 'giá' quy về mức vàng 3.850")
for name, (mode, *args), kw in CASES:
    lo_usd, hi_usd = (list(args) + [None, None])[:2]
    print(f"{name:32s}", summ(*bt(mode, lo_usd, hi_usd, **kw)))
