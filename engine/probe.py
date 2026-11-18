"""So sánh nhiều phương pháp giao dịch XAUUSD trên cùng dữ liệu, cùng phí spread và cùng cách quản lý lệnh."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import gold  # noqa: E402
from indicators import ema, rsi  # noqa: E402

SPREAD = 0.35  # USD mỗi lệnh (spread + trượt giá), trừ vào kết quả
H4P, H1P = pd.Timedelta(hours=4), pd.Timedelta(hours=1)


def ind(df):
    df = gold.add_ind(df)
    c = df["close"]
    df["ema9"], df["ema21"] = ema(c, 9), ema(c, 21)
    df["rsi2"] = rsi(c, 2)
    mid, sd = c.rolling(20).mean(), c.rolling(20).std()
    df["bbu"], df["bbl"] = mid + 2 * sd, mid - 2 * sd
    line = ema(c, 12) - ema(c, 26)
    df["macd"], df["macds"] = line, ema(line, 9)
    df["dhi"], df["dlo"] = df["high"].rolling(20).max().shift(1), df["low"].rolling(20).min().shift(1)
    # Supertrend (10, 3)
    hl2, a = (df["high"] + df["low"]) / 2, df["atr"]
    up, dn = (hl2 - 3 * a).to_numpy(), (hl2 + 3 * a).to_numpy()
    cl = c.to_numpy(); st = np.zeros(len(df)); dirn = np.ones(len(df))
    for i in range(1, len(df)):
        up[i] = max(up[i], up[i - 1]) if cl[i - 1] > up[i - 1] else up[i]
        dn[i] = min(dn[i], dn[i - 1]) if cl[i - 1] < dn[i - 1] else dn[i]
        dirn[i] = 1 if cl[i] > dn[i - 1] else -1 if cl[i] < up[i - 1] else dirn[i - 1]
        st[i] = up[i] if dirn[i] > 0 else dn[i]
    df["st"], df["stdir"] = st, dirn
    return df


def h4trend(h1raw, idx):
    h4 = gold.add_ind(h1raw.resample("4h", origin="epoch").agg(gold.OHLC).dropna())
    t = h4.apply(gold.trend_of, axis=1).map({"Tăng": 1, "Giảm": -1, "Đi ngang": 0})
    return gold.closed_on(t, H4P, idx).fillna(0).to_numpy()


def sim(df, side, risk, start, tp, be=None, trail=None):
    """Vào lệnh thị trường ở giá đóng cửa nến tín hiệu, một lệnh mỗi lúc, SL trước khi xét chốt lời."""
    H, L, C = (df[k].to_numpy() for k in ("high", "low", "close"))
    out, pos = [], None
    for i in range(start, len(df)):
        if pos:
            d = pos["d"]
            fav = d * ((H[i] if d > 0 else L[i]) - pos["e"]) / pos["r"]
            if (L[i] <= pos["sl"]) if d > 0 else (H[i] >= pos["sl"]):
                out.append((df.index[pos["t"]], d * (pos["sl"] - pos["e"]) / pos["r"], pos["r"])); pos = None
            elif fav >= tp:
                out.append((df.index[pos["t"]], tp, pos["r"])); pos = None
            else:
                pos["mx"] = max(pos["mx"], fav)
                if be and fav >= be and d * (pos["e"] - pos["sl"]) > 0:
                    pos["sl"] = pos["e"]
                if trail and pos["mx"] >= trail[0]:
                    nsl = pos["e"] + d * (pos["mx"] - trail[1]) * pos["r"]
                    if d * (nsl - pos["sl"]) > 0:
                        pos["sl"] = nsl
            continue
        if side[i] and risk[i] > 0 and np.isfinite(risk[i]):
            d = int(side[i])
            pos = {"d": d, "e": C[i], "r": risk[i], "sl": C[i] - d * risk[i], "mx": 0.0, "t": i}
    return out


def metrics(out):
    if len(out) < 8:
        return None
    raw = np.array([x[1] for x in out]); net = raw - SPREAD / np.array([x[2] for x in out])
    h = len(net) // 2
    eq = np.cumsum(net); dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max()
    pf = net[net > 0].sum() / max(-net[net < 0].sum(), 1e-9)
    w = raw > 1e-9
    return dict(n=len(net), win=w.mean() * 100, be=(np.abs(raw) <= 1e-9).mean() * 100, loss=(raw < -1e-9).mean() * 100,
                avgwin=raw[w].mean() if w.any() else 0, avg=net.mean(), tot=net.sum(), pf=pf, dd=dd,
                h1=net[:h].sum(), h2=net[h:].sum())


def methods(m15r, h1r):
    """Trả về {tên: (khung, df, side, risk)}; side 1/-1/0 tại nến tín hiệu đã đóng."""
    M, Hh = ind(m15r), ind(h1r)
    t4m, t4h = h4trend(h1r, M.index), h4trend(h1r, Hh.index)
    R = {}
    def arr(df, cond_b, cond_s):
        return np.where(cond_b, 1, np.where(cond_s, -1, 0))
    a = Hh["atr"]
    # 1 EMA 9/21 cắt nhau H1, theo H4
    xb = (Hh["ema9"] > Hh["ema21"]) & (Hh["ema9"].shift() <= Hh["ema21"].shift())
    xs = (Hh["ema9"] < Hh["ema21"]) & (Hh["ema9"].shift() >= Hh["ema21"].shift())
    R["EMA 9/21 cắt nhau (H1) theo H4"] = ("H1", Hh, arr(Hh, xb & (t4h > 0), xs & (t4h < 0)), (1.5 * a).to_numpy())
    # 2 Hồi về EMA50 H1 theo H4
    pb = (Hh["low"] <= Hh["ema50"]) & (Hh["close"] > Hh["ema50"]) & (Hh["close"] > Hh["open"])
    ps = (Hh["high"] >= Hh["ema50"]) & (Hh["close"] < Hh["ema50"]) & (Hh["close"] < Hh["open"])
    rk = np.maximum(np.where(pb, Hh["close"] - Hh["low"], Hh["high"] - Hh["close"]) + 0.2 * a, a)
    R["Hồi về EMA50 (H1) theo H4"] = ("H1", Hh, arr(Hh, pb & (t4h > 0), ps & (t4h < 0)), np.asarray(rk))
    # 3 Phá đỉnh/đáy 20 nến H1 (Donchian)
    R["Phá đỉnh/đáy 20 nến (H1)"] = ("H1", Hh, arr(Hh, Hh["close"] > Hh["dhi"], Hh["close"] < Hh["dlo"]), (2 * a).to_numpy())
    R["Phá đỉnh/đáy 20 nến (H1) theo H4"] = ("H1", Hh, arr(Hh, (Hh["close"] > Hh["dhi"]) & (t4h > 0), (Hh["close"] < Hh["dlo"]) & (t4h < 0)), (2 * a).to_numpy())
    # 4 Supertrend H1 đổi chiều
    flip_b = (Hh["stdir"] > 0) & (Hh["stdir"].shift() < 0); flip_s = (Hh["stdir"] < 0) & (Hh["stdir"].shift() > 0)
    R["Supertrend đổi chiều (H1)"] = ("H1", Hh, arr(Hh, flip_b, flip_s), np.maximum((Hh["close"] - Hh["st"]).abs(), a).to_numpy())
    # 5 MACD cắt + EMA200 H1
    mb = (Hh["macd"] > Hh["macds"]) & (Hh["macd"].shift() <= Hh["macds"].shift()) & (Hh["macd"] < 0) & (Hh["close"] > Hh["ema200"])
    ms = (Hh["macd"] < Hh["macds"]) & (Hh["macd"].shift() >= Hh["macds"].shift()) & (Hh["macd"] > 0) & (Hh["close"] < Hh["ema200"])
    R["MACD cắt nhau + EMA200 (H1)"] = ("H1", Hh, arr(Hh, mb, ms), (1.5 * a).to_numpy())
    # 6 RSI(2) hồi quy H1 theo EMA200
    R["RSI(2) quá bán/quá mua (H1) theo EMA200"] = ("H1", Hh, arr(Hh, (Hh["close"] > Hh["ema200"]) & (Hh["rsi2"] < 10), (Hh["close"] < Hh["ema200"]) & (Hh["rsi2"] > 90)), (2 * a).to_numpy())
    # 7 Inside bar H1 phá vỡ theo H4
    ib = (Hh["high"].shift() < Hh["high"].shift(2)) & (Hh["low"].shift() > Hh["low"].shift(2))
    R["Inside bar phá vỡ (H1) theo H4"] = ("H1", Hh, arr(Hh, ib & (Hh["close"] > Hh["high"].shift()) & (t4h > 0), ib & (Hh["close"] < Hh["low"].shift()) & (t4h < 0)),
                                          np.maximum(np.where(Hh["close"] > Hh["high"].shift(), Hh["close"] - Hh["low"].shift(), Hh["high"].shift() - Hh["close"]), 0.5 * a))
    am = M["atr"]
    # 8 Bollinger quay lại trong biên M15 theo H4
    bb_b = (M["close"].shift() < M["bbl"].shift()) & (M["close"] > M["bbl"]); bb_s = (M["close"].shift() > M["bbu"].shift()) & (M["close"] < M["bbu"])
    R["Bollinger quay lại trong biên (M15) theo H4"] = ("M15", M, arr(M, bb_b & (t4m > 0), bb_s & (t4m < 0)), (1.5 * am).to_numpy())
    # 9 Phá biên độ phiên Á khi London mở cửa (M15): phiên Á 00:00–07:00 UTC, vào 07:00–11:00 UTC, mỗi ngày tối đa 1 lệnh
    day = M.index.floor("D"); hr = M.index.hour
    asia = M[hr < 7].groupby(day[hr < 7]).agg(ahi=("high", "max"), alo=("low", "min"))
    ahi = pd.Series(day, index=M.index).map(asia["ahi"]).to_numpy(); alo = pd.Series(day, index=M.index).map(asia["alo"]).to_numpy()
    win = (hr >= 7) & (hr < 11)
    cb = win & (M["close"].to_numpy() > ahi); cs = win & (M["close"].to_numpy() < alo)
    first = np.zeros(len(M), bool); seen = set()
    for i in np.flatnonzero(cb | cs):
        if day[i] not in seen:
            first[i] = True; seen.add(day[i])
    rng = ahi - alo
    R["Phá biên độ phiên Á lúc London mở (M15)"] = ("M15", M, np.where(first & cb, 1, np.where(first & cs, -1, 0)), np.maximum(rng / 2, am.to_numpy()))
    R["Phá biên độ phiên Á lúc London mở (M15) theo H4"] = ("M15", M, np.where(first & cb & (t4m > 0), 1, np.where(first & cs & (t4m < 0), -1, 0)), np.maximum(rng / 2, am.to_numpy()))
    # 10 FVG (khoảng trống giá) M15 theo H4: giá quay lại vùng trống rồi đóng cửa giữ được
    H_, L_, C_ = M["high"].to_numpy(), M["low"].to_numpy(), M["close"].to_numpy()
    side = np.zeros(len(M)); risk = np.zeros(len(M)); bull = bear = None
    for i in range(2, len(M)):
        if L_[i] > H_[i - 2]:
            bull = (H_[i - 2], L_[i], i)
        if H_[i] < L_[i - 2]:
            bear = (H_[i], L_[i - 2], i)
        if bull and i - bull[2] > 1 and i - bull[2] <= 20 and t4m[i] > 0 and L_[i] <= bull[1] and C_[i] > bull[0]:
            side[i] = 1; risk[i] = max(C_[i] - bull[0] + 0.2 * am.iloc[i], am.iloc[i]); bull = None
        elif bear and i - bear[2] > 1 and i - bear[2] <= 20 and t4m[i] < 0 and H_[i] >= bear[0] and C_[i] < bear[1]:
            side[i] = -1; risk[i] = max(bear[1] - C_[i] + 0.2 * am.iloc[i], am.iloc[i]); bear = None
    R["FVG khoảng trống giá (M15) theo H4"] = ("M15", M, side, risk)
    # 11 Hồi EMA20 M15 theo H4 + H1 (3 khung, không chờ quét thanh khoản)
    z1 = gold.closed_on(gold.h1_zones(gold.add_ind(h1r)), H1P, M.index).fillna("").to_numpy()
    pb2 = (M["low"] <= M["ema20"]) & (M["close"] > M["ema20"]) & (M["close"] > M["open"])
    ps2 = (M["high"] >= M["ema20"]) & (M["close"] < M["ema20"]) & (M["close"] < M["open"])
    R["3 khung, vào khi M15 chạm EMA20 (không chờ quét)"] = ("M15", M, arr(M, pb2 & (t4m > 0) & (z1 == "MUA"), ps2 & (t4m < 0) & (z1 == "BÁN")),
                                                          np.maximum(np.where(pb2, M["close"] - M["low"], M["high"] - M["close"]) + 0.1 * am, 15 * M["close"] / 3850))
    return R, M


EXITS = {"chốt 1:2": dict(tp=2.0), "hoà vốn 1R + kéo SL từ 3R, tối đa 8R": dict(tp=8.0, be=1.0, trail=(3.0, 1.5))}


def ours(m15r, h1r, start):
    m = gold.add_sweep(gold.add_ind(m15r)); hh = gold.add_ind(h1r)
    h4 = gold.add_ind(h1r.resample("4h", origin="epoch").agg(gold.OHLC).dropna())
    t4 = gold.closed_on(h4.apply(gold.trend_of, axis=1), H4P, m.index).fillna("Đi ngang")
    z = gold.closed_on(gold.h1_zones(hh), H1P, m.index).fillna("")
    b, s = gold.setups(m, t4, z)
    tr, _, _ = gold.backtest(m, b, s, start)
    return [(x["t_in"], x["r"], abs(x["entry"] - x["sl"])) for x in tr]


def fmt(name, a, b, tag2):
    if not a:
        return f"{name:62s} ít lệnh"
    s2 = f"{tag2} {b['n']}L {b['tot']:+.0f}R TB {b['avg']:+.2f}" if b else f"{tag2} –"
    return (f"{name:62s} n={a['n']:4d} thắng {a['win']:4.1f}% hoà {a['be']:4.1f}% thua {a['loss']:4.1f}% | lệnh thắng TB {a['avgwin']:.1f}R | "
            f"TB {a['avg']:+.2f}R tổng {a['tot']:+6.1f}R pf {a['pf']:.2f} dd {a['dd']:5.1f} | nửa {a['h1']:+.0f}/{a['h2']:+.0f} | {s2}")


spot, _ = gold.spot_price()
p15, p1 = gold.binance("15m", 70000), gold.binance("1h", 20000)
g1, _ = gold.shift_to_spot(gold.clean(gold.yahoo("1h", "730d")), spot)
g15, _ = gold.shift_to_spot(gold.clean(gold.yahoo("15m", "60d")), spot)
P, PM = methods(p15, p1)
G, GM = methods(g15, g1)
# Với phương pháp H1 dùng thêm 2 năm H1 GC=F (dữ liệu độc lập) để kiểm chứng
GH, _ = methods(g15, g1)
rows = []
print(f"##### Phí mỗi lệnh {SPREAD} USD (trừ vào R). Kiểm chứng: H1 trên 2 năm GC=F; M15 trên 60 ngày GC=F.")
a = metrics(ours(p15, p1, 2000)); b = metrics(ours(g15, g1, 200))
print(fmt("★ Quét thanh khoản 3 khung + lệnh chờ + kéo SL (đang dùng)", a, b, "GC60"))
rows.append(("★ đang dùng", a))
for name, (tf, df, side, risk) in P.items():
    start = 2000 if tf == "M15" else 500
    _, gdf, gside, grisk = G[name]
    for en, kw in EXITS.items():
        a = metrics(sim(df, side, risk, start, **kw))
        b = metrics(sim(gdf, gside, grisk, 200 if tf == "M15" else 500, **kw))
        print(fmt(f"{name} · {en}", a, b, "GC2y" if tf == "H1" else "GC60"))
        if a:
            rows.append((f"{name} · {en}", a))
print("##### Xếp hạng theo lãi TB mỗi lệnh (sau phí), chỉ tính phương pháp ≥ 30 lệnh và lãi ở cả hai nửa")
ok = [(n, a) for n, a in rows if a["n"] >= 30 and a["h1"] > 0 and a["h2"] > 0]
for k, (n, a) in enumerate(sorted(ok, key=lambda x: -x[1]["avg"])[:12], 1):
    print(f"{k:2d}. {n:70s} TB {a['avg']:+.2f}R pf {a['pf']:.2f} thắng {a['win']:.0f}% n={a['n']}")
