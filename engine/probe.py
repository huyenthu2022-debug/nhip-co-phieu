"""Thử cách quản lý lệnh và vào lệnh để tăng cả tỷ lệ thắng lẫn R:R (đã có lọc RSI + giờ)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import gold  # noqa: E402


def prep(h1r, m15r):
    m = gold.add_sweep(gold.add_ind(m15r))
    h1 = gold.add_ind(h1r)
    h4 = gold.add_ind(h1r.resample("4h", origin="epoch").agg(gold.OHLC).dropna())
    h4tr = gold.closed_on(h4.apply(gold.trend_of, axis=1), pd.Timedelta(hours=4), m.index).fillna("Đi ngang")
    zone = gold.closed_on(gold.h1_zones(h1), pd.Timedelta(hours=1), m.index).fillna("")
    b, s = gold.setups(m, h4tr, zone)
    return m, b, s


def sim(m, b, s, start, tp=3.0, be=1.0, pfrac=0.0, pat=0.0, trail=None, limit=0.0, wait=4, minr=None, opp_exit=True):
    """tp/be/pat theo R. pfrac: phần chốt sớm tại pat (sau đó SL về giá vào). trail=(bắt đầu R, khoảng R).
    limit: vào lệnh chờ tại giá đóng cửa lùi về phía râu quét limit*(đóng cửa − râu), chờ tối đa `wait` nến.
    minr: SL tối thiểu (giá ở mức 3.850) khi vào lệnh chờ, mặc định giữ 15."""
    H, L, C, W_LO, W_HI, A = (m[k].to_numpy() for k in ("high", "low", "close", "wick_lo", "wick_hi", "atr"))
    out, pos, pend = [], None, None
    for i in range(start, len(m)):
        sig = 1 if b[i] else -1 if s[i] else 0
        if pos:
            d = pos["d"]
            fav = d * ((H[i] if d > 0 else L[i]) - pos["e"]) / pos["r"]
            adv_hit = (L[i] <= pos["sl"]) if d > 0 else (H[i] >= pos["sl"])
            res = None
            if adv_hit:
                res = pos["real"] + pos["rem"] * d * (pos["sl"] - pos["e"]) / pos["r"]
            elif fav >= tp:
                res = pos["real"] + pos["rem"] * tp
            else:
                pos["mx"] = max(pos["mx"], fav)
                if pfrac and not pos["pd"] and fav >= pat:
                    pos["pd"] = True; pos["real"] += pfrac * pat; pos["rem"] -= pfrac
                    pos["sl"] = pos["e"] if d * (pos["e"] - pos["sl"]) > 0 else pos["sl"]
                if be and fav >= be and d * (pos["e"] - pos["sl"]) > 0:
                    pos["sl"] = pos["e"]
                if trail and pos["mx"] >= trail[0]:
                    nsl = pos["e"] + d * (pos["mx"] - trail[1]) * pos["r"]
                    if d * (nsl - pos["sl"]) > 0:
                        pos["sl"] = nsl
                if opp_exit and sig == -d:
                    res = pos["real"] + pos["rem"] * d * (C[i] - pos["e"]) / pos["r"]
            if res is not None:
                out.append((m.index[pos["t"]], res)); pos = None
                if not (opp_exit and sig):
                    continue
        if pend and not pos:   # lệnh chờ
            d = pend["d"]
            if i > pend["i"] + wait or sig == -d:
                pend = None
            elif (L[i] <= pend["e"]) if d > 0 else (H[i] >= pend["e"]):
                pos = {**pend, "t": i, "real": 0.0, "rem": 1.0, "pd": False, "mx": 0.0}
                pend = None
                # cùng nến chạm SL: tính thua (thận trọng)
                if (L[i] <= pos["sl"]) if d > 0 else (H[i] >= pos["sl"]):
                    out.append((m.index[i], -1.0)); pos = None
                continue
        if not pos and sig:
            d = sig
            if limit:
                wick = W_LO[i] if d > 0 else W_HI[i]
                e = C[i] - limit * (C[i] - wick)
                sc = C[i] / gold.REF_PRICE
                raw = d * (e - wick) + gold.SL_BUF_ATR * A[i]
                r = max(raw, (minr if minr is not None else gold.MIN_RISK_USD) * sc)
                pend = {"d": d, "e": e, "r": r, "sl": e - d * r, "i": i}
            else:
                p = gold.plan("MUA" if d > 0 else "BÁN", i, m)
                pos = {"d": d, "e": p["entry"], "r": p["risk"], "sl": p["sl"], "t": i, "real": 0.0, "rem": 1.0, "pd": False, "mx": 0.0}
    return pd.Series([x[1] for x in out], index=[x[0] for x in out], dtype=float)


def line(name, r, g):
    if len(r) < 5:
        print(f"{name:44s} ít lệnh"); return
    w, l = r[r > 0], r[r < 0]
    h = len(r) // 2
    eq = r.cumsum().to_numpy(); dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max()
    pf = w.sum() / max(-l.sum(), 1e-9)
    rr = w.mean() / max(-l.mean(), 1e-9) if len(w) and len(l) else float("nan")
    print(f"{name:44s} n={len(r):3d} thắng {len(w)/len(r)*100:4.1f}% hoà {(r == 0).mean()*100:4.1f}% thua {len(l)/len(r)*100:4.1f}% "
          f"| lãi TB/lỗ TB {rr:4.2f} | TB {r.mean():+.2f}R tổng {r.sum():+5.1f}R pf {pf:.2f} dd {dd:4.1f} | nửa {r.iloc[:h].sum():+.0f}/{r.iloc[h:].sum():+.0f} "
          f"| GC {len(g)}L {g.sum():+.1f}R thắng {(g > 0).mean()*100:.0f}%")


spot, _ = gold.spot_price()
P = prep(gold.binance("1h", 20000), gold.binance("15m", 70000))
gh1, _ = gold.shift_to_spot(gold.clean(gold.yahoo("1h", "730d")), spot)
gm15, _ = gold.shift_to_spot(gold.clean(gold.yahoo("15m", "60d")), spot)
G = prep(gh1, gm15)
V = {
    "hiện tại: hoà vốn 1R, chốt 3R": {},
    "hoà vốn 1.5R, chốt 3R": dict(be=1.5),
    "hoà vốn 2R, chốt 3R": dict(be=2.0),
    "không dời hoà vốn, chốt 3R": dict(be=0),
    "hoà vốn 1.5R, chốt 4R": dict(be=1.5, tp=4),
    "chốt 50% ở 1R, còn lại 3R": dict(pfrac=.5, pat=1.0, be=0),
    "chốt 50% ở 1.5R, còn lại 3R": dict(pfrac=.5, pat=1.5, be=0),
    "chốt 50% ở 1.5R, còn lại 4R": dict(pfrac=.5, pat=1.5, be=0, tp=4),
    "chốt 50% ở 2R, còn lại 4R": dict(pfrac=.5, pat=2.0, be=0, tp=4),
    "chốt 50% ở 2R, còn lại 5R": dict(pfrac=.5, pat=2.0, be=0, tp=5),
    "chốt 30% ở 1.5R, còn lại 4R": dict(pfrac=.3, pat=1.5, be=0, tp=4),
    "chốt 50% ở 1.5R, còn lại kéo SL 1R, tối đa 6R": dict(pfrac=.5, pat=1.5, be=0, tp=6, trail=(2.0, 1.0)),
    "hoà vốn 1R, kéo SL cách 1.5R từ 2.5R, tối đa 6R": dict(be=1.0, tp=6, trail=(2.5, 1.5)),
    "lệnh chờ hồi 30% râu, chốt 3R": dict(limit=.3),
    "lệnh chờ hồi 50% râu, chốt 3R": dict(limit=.5),
    "lệnh chờ hồi 50% râu, hoà vốn 1.5R, chốt 3R": dict(limit=.5, be=1.5),
    "lệnh chờ hồi 50% râu, chốt 50% ở 1.5R, còn 4R": dict(limit=.5, pfrac=.5, pat=1.5, be=0, tp=4),
    "lệnh chờ hồi 50% râu, SL tối thiểu 12, chốt 3R": dict(limit=.5, minr=12),
    "lệnh chờ hồi 50% râu, SL tối thiểu 12, 50% ở 1.5R, 4R": dict(limit=.5, minr=12, pfrac=.5, pat=1.5, be=0, tp=4),
    "lệnh chờ hồi 70% râu, chốt 3R": dict(limit=.7),
}
for k, kw in V.items():
    line(k, sim(*P, 2000, **kw), sim(*G, 200, **kw))
