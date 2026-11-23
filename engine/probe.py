"""Điểm vào sau quét thanh khoản theo mô hình 2–3 đỉnh/đáy + phân kỳ RSI, SL 10–15 giá: kiểm định nhiều biến thể."""
import sys
import warnings
warnings.filterwarnings("ignore")
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import gold  # noqa: E402

SPREAD = 0.35
H4P, H1P = pd.Timedelta(hours=4), pd.Timedelta(hours=1)


def prep(h1r, m15r):
    m = gold.add_sweep(gold.add_ind(m15r))
    h1 = gold.add_ind(h1r)
    h4 = gold.add_ind(h1r.resample("4h", origin="epoch").agg(gold.OHLC).dropna())
    t4 = gold.closed_on(h4.apply(gold.trend_of, axis=1), H4P, m.index).fillna("Đi ngang").map({"Tăng": 1, "Giảm": -1, "Đi ngang": 0}).to_numpy()
    z1 = gold.closed_on(gold.h1_zones(h1), H1P, m.index).fillna("").map({"MUA": 1, "BÁN": -1, "": 0}).to_numpy()
    return m, t4, z1


def patterns(m, K=3, W=96, tol_atr=0.6, div_min=2.0, min_gap=5, need=2):
    """Tín hiệu đảo chiều sau quét: nến hiện tại (hoặc trước) chọc thủng đáy xoay chiều còn nguyên (2 đáy)
    hoặc 2 đáy xoay chiều gần bằng nhau (3 đáy), rồi đóng cửa quay lại; RSI tạo đáy cao hơn (phân kỳ).
    Trả về side, mức râu quét, số đáy (2/3), có phân kỳ hay không."""
    H, L, C, O = (m[k].to_numpy() for k in ("high", "low", "close", "open"))
    R, A = m["rsi"].to_numpy(), m["atr"].to_numpy()
    n = len(m)
    side = np.zeros(n); wick = np.full(n, np.nan); cnt = np.zeros(n); div = np.zeros(n, bool)
    lows, highs = [], []  # (index, price, rsi) đáy/đỉnh xoay chiều đã xác nhận
    for i in range(2 * K + 1, n):
        j = i - K  # nến i xác nhận xoay chiều tại j (cần K nến mỗi bên)
        if L[j] == L[j - K:j + K + 1].min():
            lows.append((j, L[j], R[j]))
        if H[j] == H[j - K:j + K + 1].max():
            highs.append((j, H[j], R[j]))
        lows = [p for p in lows if i - p[0] <= W]; highs = [p for p in highs if i - p[0] <= W]
        tol = tol_atr * A[i]
        wl, wh = min(L[i], L[i - 1]), max(H[i], H[i - 1])
        rl, rh = min(R[i], R[i - 1]), max(R[i], R[i - 1])
        # --- MUA: quét đáy
        if C[i] > O[i]:
            # đáy còn nguyên: chưa nến nào từ sau đáy đến trước nến quét đóng... (low) thấp hơn nó
            cand = [p for p in lows if i - p[0] >= min_gap and L[p[0] + 1:i - 1].min(initial=np.inf) > p[1] and wl < p[1] <= wl + tol and C[i] > p[1]]
            if cand:
                p1 = min(cand, key=lambda p: p[1])
                peers = [q for q in lows if q[0] < p1[0] and abs(q[1] - p1[1]) <= tol and L[q[0] + 1:i - 1].min(initial=np.inf) >= p1[1] - tol and q[1] > wl]
                k = 3 if peers else 2
                if k >= need:
                    side[i], wick[i], cnt[i], div[i] = 1, wl, k, rl > p1[2] + div_min
                    continue
        # --- BÁN: quét đỉnh
        if C[i] < O[i]:
            cand = [p for p in highs if i - p[0] >= min_gap and H[p[0] + 1:i - 1].max(initial=-np.inf) < p[1] and wh > p[1] >= wh - tol and C[i] < p[1]]
            if cand:
                p1 = max(cand, key=lambda p: p[1])
                peers = [q for q in highs if q[0] < p1[0] and abs(q[1] - p1[1]) <= tol and H[q[0] + 1:i - 1].max(initial=-np.inf) <= p1[1] + tol and q[1] < wh]
                k = 3 if peers else 2
                if k >= need:
                    side[i], wick[i], cnt[i], div[i] = -1, wh, k, rh < p1[2] - div_min
    return side, wick, cnt, div


def sim(m, side, wick, start, minr=10, maxr=15, pull=0.0, wait=4, tp=8.0, be=1.0, trail=(3.0, 1.5)):
    H, L, C, A = (m[k].to_numpy() for k in ("high", "low", "close", "atr"))
    out, pos, pend = [], None, None
    for i in range(start, len(m)):
        sg = int(side[i])
        if pos:
            d = pos["d"]; fav = d * ((H[i] if d > 0 else L[i]) - pos["e"]) / pos["r"]
            res = None
            if (L[i] <= pos["sl"]) if d > 0 else (H[i] >= pos["sl"]):
                res = d * (pos["sl"] - pos["e"]) / pos["r"]
            elif fav >= tp:
                res = tp
            else:
                pos["mx"] = max(pos["mx"], fav)
                if be and fav >= be and d * (pos["e"] - pos["sl"]) > 0:
                    pos["sl"] = pos["e"]
                if trail and pos["mx"] >= trail[0]:
                    nsl = pos["e"] + d * (pos["mx"] - trail[1]) * pos["r"]
                    if d * (nsl - pos["sl"]) > 0:
                        pos["sl"] = nsl
            if res is not None:
                out.append((m.index[pos["t"]], res, pos["r"])); pos = None
            continue
        if pend:
            d = pend["d"]
            if i > pend["i"] + wait or sg == -d:
                pend = None
            elif (L[i] <= pend["e"]) if d > 0 else (H[i] >= pend["e"]):
                pos = {**pend, "t": i, "mx": 0.0}; pend = None
                if (L[i] <= pos["sl"]) if d > 0 else (H[i] >= pos["sl"]):
                    out.append((m.index[i], -1.0, pos["r"])); pos = None
                continue
        if sg:
            sc = C[i] / gold.REF_PRICE
            e = C[i] - pull * (C[i] - wick[i])
            r = max(sg * (e - wick[i]) + 0.1 * A[i], minr * sc)
            if r > maxr * sc:
                continue
            p = {"d": sg, "e": e, "r": r, "sl": e - sg * r, "i": i}
            if pull:
                pend = p
            else:
                pos = {**p, "t": i, "mx": 0.0}
    return out


def met(out):
    if len(out) < 8:
        return None
    raw = np.array([x[1] for x in out]); net = raw - SPREAD / np.array([x[2] for x in out])
    idx = pd.DatetimeIndex([x[0] for x in out]); h = len(net) // 2
    eq = np.cumsum(net); dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max()
    months = max((idx[-1] - idx[0]).days / 30.4, 1)
    q = pd.Series(net, index=idx).groupby(idx.to_period("Q")).sum()
    return dict(n=len(net), pm=len(net) / months, win=(raw > 1e-9).mean() * 100, be=(np.abs(raw) <= 1e-9).mean() * 100,
                loss=(raw < -1e-9).mean() * 100, aw=raw[raw > 1e-9].mean() if (raw > 1e-9).any() else 0, avg=net.mean(), tot=net.sum(),
                pf=net[net > 0].sum() / max(-net[net < 0].sum(), 1e-9), dd=dd, h1=net[:h].sum(), h2=net[h:].sum(), q=f"{(q > 0).sum()}/{len(q)}")


def show(name, a, g):
    if not a:
        print(f"{name:58s} ít lệnh ({0 if a is None else a})"); return
    gs = f"GC60 {g['n']}L {g['tot']:+.1f}R" if g else "GC60 –"
    print(f"{name:58s} n={a['n']:3d} ({a['pm']:.1f}/tháng) thắng {a['win']:4.1f}% hoà {a['be']:4.1f}% thua {a['loss']:4.1f}% | thắng TB {a['aw']:.1f}R | "
          f"TB {a['avg']:+.2f}R tổng {a['tot']:+5.1f}R pf {a['pf']:.2f} dd {a['dd']:4.1f} | nửa {a['h1']:+.0f}/{a['h2']:+.0f} quý lãi {a['q']} | {gs}")


spot, _ = gold.spot_price()
P = prep(gold.binance("1h", 20000), gold.binance("15m", 70000))
gh1, _ = gold.shift_to_spot(gold.clean(gold.yahoo("1h", "730d")), spot)
gm15, _ = gold.shift_to_spot(gold.clean(gold.yahoo("15m", "60d")), spot)
G = prep(gh1, gm15)
cache = {}
def pat(D, key, **kw):
    k = (id(D), key)
    if k not in cache:
        cache[k] = patterns(D[0], **kw)
    return cache[k]
hourok = lambda m: ~pd.Series((m.index + pd.Timedelta(hours=7)).hour).isin([21, 22, 23, 0, 1, 2]).to_numpy()

def run(name, pkw, filt, skw, show_it=True):
    res = []
    for D, start in ((P, 2000), (G, 200)):
        m, t4, z1 = D
        side, wick, cnt, div = pat(D, str(sorted(pkw.items())), **pkw)
        f = filt(m, side, t4, z1, cnt, div)
        res.append(met(sim(m, np.where(f, side, 0), wick, start, **skw)))
    if show_it:
        show(name, *res)
    return res

# Tín hiệu hệ 1 hiện tại (quét đáy/đỉnh 20 nến + H4 + vùng H1 + RSI≤50 + giờ) dạng side/wick để so cùng cách vào
def cur(D):
    m, t4, z1 = D
    hh = gold.closed_on(pd.Series(z1, index=m.index), pd.Timedelta(0), m.index)  # giữ nguyên
    ok = hourok(m)
    c, o, r = m["close"].to_numpy(), m["open"].to_numpy(), m["rsi"].to_numpy()
    b = (t4 == 1) & (z1 == 1) & (m["wick_lo"] < m["liq_lo"]).to_numpy() & (c > m["liq_lo"].to_numpy()) & (c > o) & (r <= 50) & ok
    s_ = (t4 == -1) & (z1 == -1) & (m["wick_hi"] > m["liq_hi"]).to_numpy() & (c < m["liq_hi"].to_numpy()) & (c < o) & (r >= 50) & ok
    return np.where(b, 1, np.where(s_, -1, 0)), np.where(b, m["wick_lo"], m["wick_hi"]).astype(float)

def run2(name, build, skw):
    res = []
    for D, start in ((P, 2000), (G, 200)):
        side, wick = build(D)
        res.append(met(sim(D[0], side, wick, start, **skw)))
    show(name, *res)

def patf(D, f, **kw):
    m, t4, z1 = D
    s_, w, c, d = pat(D, str(sorted({**base, **kw}.items())), **{**base, **kw})
    return np.where(f(m, s_, t4, z1, c, d), s_, 0), w

base = dict(K=3, W=96, tol_atr=0.6, div_min=2.0, min_gap=5)
TR = {}
NOW = dict()                      # vào ngay, kéo SL
FIX3 = dict(tp=3, be=None, trail=None)
print("##### E. Vào SỚM (ngay giá đóng cửa nến quét), SL sát râu")
for sl in ((10, 15), (8, 15), (15, 20)):
    run2(f"Hệ 1 hiện tại, vào ngay, SL {sl[0]}–{sl[1]}, kéo SL", cur, dict(minr=sl[0], maxr=sl[1]))
run2("Hệ 1 hiện tại, lệnh chờ 50% (đang dùng), SL 15–20", cur, dict(minr=15, maxr=20, pull=.5))
pv = lambda m, s, t4, z1, c, d: (s != 0) & d & (s == t4) & hourok(m)
pv0 = lambda m, s, t4, z1, c, d: (s != 0) & d & (s == t4) & hourok(m)
for kw, nm in ((dict(), "phân kỳ ≥2"), (dict(div_min=0.0), "phân kỳ ≥0"), (dict(tol_atr=1.0), "phân kỳ ≥2, dung sai 1 ATR"), (dict(div_min=0.0, tol_atr=1.0), "phân kỳ ≥0, dung sai 1 ATR")):
    for sl in ((10, 15), (8, 15)):
        run2(f"2–3 đáy + {nm} + H4 + giờ, SL {sl[0]}–{sl[1]}, kéo SL", lambda D, kw=kw: patf(D, pv, **kw), dict(minr=sl[0], maxr=sl[1]))
    run2(f"2–3 đáy + {nm} + H4 + giờ, SL 10–15, chốt 1:3", lambda D, kw=kw: patf(D, pv, **kw), dict(minr=10, maxr=15, **FIX3))
rsi_f = lambda m, s, t4, z1, c, d: (s != 0) & (s == t4) & hourok(m) & np.where(s > 0, m["rsi"].to_numpy() <= 50, m["rsi"].to_numpy() >= 50)
run2("2–3 đáy + RSI≤50 (không cần phân kỳ) + H4 + giờ, SL 10–15", lambda D: patf(D, rsi_f), dict())
zone_f = lambda m, s, t4, z1, c, d: (s != 0) & (s == t4) & (s == z1) & hourok(m)
run2("2–3 đáy + H4 + vùng H1 + giờ (không cần phân kỳ), SL 10–15", lambda D: patf(D, zone_f), dict())
def union(D, f=pv, kw=dict(div_min=0.0)):
    a, wa = cur(D); b, wb = patf(D, f, **kw)
    return np.where(a != 0, a, b), np.where(a != 0, wa, wb)
run2("GỘP: hệ 1 hiện tại HOẶC 2–3 đáy+phân kỳ+H4+giờ, vào ngay, SL 10–15", union, dict())
run2("GỘP: … SL 8–15", union, dict(minr=8, maxr=15))
run2("GỘP: … SL 10–15, chốt 1:3", union, dict(**FIX3))
def union_div(D):
    a, wa = cur(D); m = D[0]
    s_, w, c, d = pat(D, str(sorted(base.items())), **base)
    keep = (a != 0)
    return np.where(keep, a, 0), wa
print("##### Tham chiếu: hệ 1 hiện tại (quét + H4 + H1 + RSI≤50 + giờ, lệnh chờ, SL 15–20) ≈ 101 lệnh, +0,67R sau phí, pf 2,84")
