"""Thử bộ lọc chất lượng điểm vào cho hệ quét thanh khoản (chốt 1:3) trên 2 năm PAXG và 60 ngày GC=F."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import gold  # noqa: E402
from indicators import ema  # noqa: E402

H1, H4, D1 = pd.Timedelta(hours=1), pd.Timedelta(hours=4), pd.Timedelta(days=1)


def prep(h1r, m15r):
    m = gold.add_sweep(gold.add_ind(m15r))
    h1 = gold.add_ind(h1r)
    h4 = gold.add_ind(h1r.resample("4h", origin="epoch").agg(gold.OHLC).dropna())
    d1 = h1r.resample("1D").agg(gold.OHLC).dropna()
    d1["ema20"], d1["ema50"] = ema(d1["close"], 20), ema(d1["close"], 50)
    h4tr = gold.closed_on(h4.apply(gold.trend_of, axis=1), H4, m.index).fillna("Đi ngang")
    zone = gold.closed_on(gold.h1_zones(h1), H1, m.index).fillna("")
    b, s = gold.setups(m, h4tr, zone)
    a = m["atr"]
    rng = (m["high"] - m["low"]).replace(0, np.nan)
    f = pd.DataFrame(index=m.index)
    f["dir"] = np.where(b, 1, np.where(s, -1, 0))
    d = f["dir"]
    f["depth"] = np.where(d > 0, (m["liq_lo"] - m["wick_lo"]) / a, (m["wick_hi"] - m["liq_hi"]) / a)
    f["reclaim"] = np.where(d > 0, (m["close"] - m["liq_lo"]) / a, (m["liq_hi"] - m["close"]) / a)
    f["body"] = (m["close"] - m["open"]).abs() / rng
    f["cpos"] = np.where(d > 0, (m["close"] - m["low"]) / rng, (m["high"] - m["close"]) / rng)
    f["rsi"] = np.where(d > 0, m["rsi"], 100 - m["rsi"])          # thấp = quá bán theo chiều lệnh
    lo_age = m["low"].shift(2).rolling(20).apply(lambda x: 19 - np.argmin(x), raw=True)
    hi_age = m["high"].shift(2).rolling(20).apply(lambda x: 19 - np.argmax(x), raw=True)
    f["age"] = np.where(d > 0, lo_age, hi_age)                      # số nến kể từ khi đáy/đỉnh thanh khoản hình thành
    f["hour"] = (m.index + pd.Timedelta(hours=7)).hour
    f["atrq"] = a / a.rolling(960).median()
    h1e = gold.closed_on(h1["ema20"], H1, m.index)
    h1a = gold.closed_on(h1["atr"], H1, m.index)
    f["h1dist"] = d * (m["close"] - h1e) / h1a
    d1c = gold.closed_on(d1["close"], D1, m.index)
    d1e = gold.closed_on(d1["ema50"], D1, m.index)
    f["d1"] = np.sign(d1c - d1e) * d
    raw = np.where(d > 0, m["close"] - m["wick_lo"], m["wick_hi"] - m["close"]) + 0.1 * a
    f["rawrisk"] = raw * gold.REF_PRICE / m["close"]
    f["macd"] = np.sign(m["macdh"] - m["macdh"].shift(1)) * d     # động lượng M15 quay đầu theo chiều lệnh
    return m, b, s, f


def run(m, b, s, mask, start):
    mk = mask.to_numpy() if hasattr(mask, "to_numpy") else mask
    tr, _ = gold.backtest(m, b & mk, s & mk, start)
    if len(tr) < 5:
        return None
    r = np.array([x["r"] for x in tr])
    h = len(r) // 2
    eq = np.cumsum(r)
    dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max()
    pf = r[r > 0].sum() / max(-r[r < 0].sum(), 1e-9)
    return dict(n=len(r), win=(r > 0).mean() * 100, loss=(r < 0).mean() * 100, avg=r.mean(), tot=r.sum(), pf=pf, dd=dd,
                h1=r[:h].sum(), h2=r[h:].sum())


gold.TP_R = 3.0
spot, _ = gold.spot_price()
P = prep(gold.binance("1h", 20000), gold.binance("15m", 70000))
gh1, _ = gold.shift_to_spot(gold.clean(gold.yahoo("1h", "730d")), spot)
gm15, _ = gold.shift_to_spot(gold.clean(gold.yahoo("15m", "60d")), spot)
G = prep(gh1, gm15)

def V(fn):
    return fn
variants = {"gốc": lambda f: f["dir"] != 99}
for t in (0.1, 0.2, 0.3, 0.5): variants[f"quét sâu ≥{t}ATR"] = (lambda t: lambda f: f["depth"] >= t)(t)
for t in (1.0, 1.5, 2.0): variants[f"quét nông ≤{t}ATR"] = (lambda t: lambda f: f["depth"] <= t)(t)
for t in (0.1, 0.2, 0.3): variants[f"đóng lại ≥{t}ATR"] = (lambda t: lambda f: f["reclaim"] >= t)(t)
for t in (0.4, 0.5, 0.6): variants[f"thân nến ≥{t}"] = (lambda t: lambda f: f["body"] >= t)(t)
for t in (0.6, 0.7, 0.8): variants[f"đóng gần đỉnh ≥{t}"] = (lambda t: lambda f: f["cpos"] >= t)(t)
for t in (40, 45, 50): variants[f"RSI theo chiều ≤{t}"] = (lambda t: lambda f: f["rsi"] <= t)(t)
for t in (3, 5, 8): variants[f"đáy thanh khoản cũ ≥{t} nến"] = (lambda t: lambda f: f["age"] >= t)(t)
for t in (0.7, 1.5): variants[f"ATR so trung vị ≤{t}" if t > 1 else f"ATR so trung vị ≥{t}"] = (lambda t: lambda f: f["atrq"] <= t if t > 1 else f["atrq"] >= t)(t)
for t in (0.5, 1.0): variants[f"gần EMA20 H1 ≤{t}ATR"] = (lambda t: lambda f: f["h1dist"] <= t)(t)
variants["D1 cùng chiều"] = lambda f: f["d1"] > 0
for t in (12, 15, 18): variants[f"SL gốc ≤{t} (chưa nới)"] = (lambda t: lambda f: f["rawrisk"] <= t)(t)
variants["MACD M15 quay đầu"] = lambda f: f["macd"] > 0
variants["bỏ 22h–4h VN"] = lambda f: ~f["hour"].isin([22, 23, 0, 1, 2, 3])
variants["bỏ 19h–23h VN (Mỹ mở)"] = lambda f: ~f["hour"].isin([19, 20, 21, 22])
variants["chỉ 6h–18h VN"] = lambda f: f["hour"].between(6, 18)
variants["bỏ 13h–15h VN"] = lambda f: ~f["hour"].isin([13, 14])

def show(name, mask_fn):
    a = run(P[0], P[1], P[2], mask_fn(P[3]).fillna(False), 2000)
    g = run(G[0], G[1], G[2], mask_fn(G[3]).fillna(False), 200)
    if not a:
        print(f"{name:28s} quá ít lệnh"); return
    gs = f"GC {g['n']:2d}L {g['tot']:+5.1f}R pf{g['pf']:.2f}" if g else "GC –"
    print(f"{name:28s} n={a['n']:3d} thắng {a['win']:4.1f}% thua {a['loss']:4.1f}% TB {a['avg']:+.2f}R tổng {a['tot']:+5.1f}R "
          f"pf {a['pf']:.2f} dd {a['dd']:4.1f} | nửa {a['h1']:+5.1f}/{a['h2']:+5.1f} | {gs}")

print("##### Từng bộ lọc")
for k, fn in variants.items():
    show(k, fn)

# Giờ trong ngày: tổng R theo khung 3 giờ (giờ VN), để thấy phiên nào kém
tr, _ = gold.backtest(P[0], P[1], P[2], 2000)
hr = pd.Series({x["t_in"]: x["r"] for x in tr})
hb = ((hr.index + pd.Timedelta(hours=7)).hour // 3) * 3
print("##### R theo giờ VN (khối 3h):", hr.groupby(hb).agg(["count", "sum"]).round(1).to_dict("index"))
# Phân vị đặc trưng của lệnh thắng vs thua
F = P[3]
rows = []
for x in tr:
    row = F.loc[x["t_in"]].to_dict(); row["r"] = x["r"]; rows.append(row)
D = pd.DataFrame(rows)
print("##### Trung vị đặc trưng: thắng / hoà / thua")
print(D.groupby(np.sign(D["r"]))[["depth", "reclaim", "body", "cpos", "rsi", "age", "atrq", "h1dist", "d1", "rawrisk", "macd"]].median().round(2).to_string())
import itertools
print("##### Kết hợp 2 bộ lọc tốt nhất (theo TB R, cần ≥80 lệnh và cả hai nửa dương)")
keys = [k for k in variants if k != "gốc"]
res = []
for k1, k2 in itertools.combinations(keys, 2):
    fn = (lambda a1, a2: lambda f: a1(f).fillna(False) & a2(f).fillna(False))(variants[k1], variants[k2])
    a = run(P[0], P[1], P[2], fn(P[3]), 2000)
    if a and a["n"] >= 80 and a["h1"] > 0 and a["h2"] > 0:
        res.append((a["avg"], k1, k2, fn))
for avg, k1, k2, fn in sorted(res, reverse=True)[:12]:
    show(f"{k1} + {k2}"[:60], fn)
