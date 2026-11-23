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

F = {
    "mọi cú quét 2–3 đáy": lambda m, s, t4, z1, c, d: s != 0,
    "+ phân kỳ RSI": lambda m, s, t4, z1, c, d: (s != 0) & d,
    "+ phân kỳ + theo H4": lambda m, s, t4, z1, c, d: (s != 0) & d & (s == t4),
    "+ phân kỳ + không ngược H4": lambda m, s, t4, z1, c, d: (s != 0) & d & (s != -t4),
    "+ phân kỳ + theo H4 + vùng H1": lambda m, s, t4, z1, c, d: (s != 0) & d & (s == t4) & (s == z1),
    "+ phân kỳ + bỏ 21h–3h": lambda m, s, t4, z1, c, d: (s != 0) & d & hourok(m),
    "+ phân kỳ + theo H4 + bỏ 21h–3h": lambda m, s, t4, z1, c, d: (s != 0) & d & (s == t4) & hourok(m),
    "+ phân kỳ + không ngược H4 + bỏ 21h–3h": lambda m, s, t4, z1, c, d: (s != 0) & d & (s != -t4) & hourok(m),
    "chỉ 3 đáy/đỉnh": lambda m, s, t4, z1, c, d: (s != 0) & (c == 3),
    "3 đáy/đỉnh + phân kỳ": lambda m, s, t4, z1, c, d: (s != 0) & (c == 3) & d,
    "3 đáy/đỉnh + phân kỳ + không ngược H4": lambda m, s, t4, z1, c, d: (s != 0) & (c == 3) & d & (s != -t4),
}
base = dict(K=3, W=96, tol_atr=0.6, div_min=2.0, min_gap=5)
print("##### A. Bộ lọc (vào ngay giá đóng cửa, SL 10–15, hoà vốn 1R + kéo SL từ 3R, tối đa 8R)")
for k, f in F.items():
    run(k, base, f, {})
print("##### B. Cách vào/thoát với 3 bộ lọc tiêu biểu")
for fk in ("+ phân kỳ RSI", "+ phân kỳ + không ngược H4", "+ phân kỳ + không ngược H4 + bỏ 21h–3h", "+ phân kỳ + theo H4"):
    for ek, ekw in {"vào ngay, chốt 1:2": dict(tp=2, be=None, trail=None), "vào ngay, chốt 1:3": dict(tp=3, be=None, trail=None),
                    "vào ngay, hoà vốn 1R, chốt 1:3": dict(tp=3, trail=None), "lệnh chờ 50%, kéo SL": dict(pull=0.5),
                    "lệnh chờ 30%, kéo SL": dict(pull=0.3)}.items():
        run(f"{fk} · {ek}", base, F[fk], ekw)
print("##### C. Độ nhạy tham số nhận diện (bộ lọc: phân kỳ + không ngược H4)")
for k, v in [("K", 2), ("K", 5), ("W", 48), ("W", 192), ("tol_atr", 0.3), ("tol_atr", 1.0), ("div_min", 0.0), ("div_min", 5.0), ("min_gap", 10)]:
    run(f"{k}={v}", {**base, k: v}, F["+ phân kỳ + không ngược H4"], {})
print("##### D. SL khác (bộ lọc: phân kỳ + không ngược H4)")
for mn, mx in ((10, 15), (8, 15), (10, 20), (12, 15)):
    run(f"SL {mn}–{mx}", base, F["+ phân kỳ + không ngược H4"], dict(minr=mn, maxr=mx))
print("##### Tham chiếu: hệ 1 hiện tại (quét + H4 + H1 + RSI≤50 + giờ, lệnh chờ, SL 15–20) ≈ 101 lệnh, +0,67R sau phí, pf 2,84")
