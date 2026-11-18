"""So sánh biến thể hệ 3 khung trên 2 năm PAXG/USDT M15."""
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
d1up = gold.closed_on(d1["close"] > d1["ema50"], pd.Timedelta(days=1), m15.index).fillna(False).astype(bool)
# Đáy/đỉnh 6 nến H1 đã đóng, gắn vào M15
h1lo = gold.closed_on(h1["low"].rolling(6).min(), H1, m15.index)
h1hi = gold.closed_on(h1["high"].rolling(6).max(), H1, m15.index)
a1 = gold.closed_on(h1["atr"], H1, m15.index)
orig_plan = gold.plan


def run(name, d1f=False, sl="m15", minr=1.0, maxr=4.0):
    b, s = gold.setups(m15, h4tr, zone)
    if d1f:
        b, s = b & d1up.to_numpy(), s & ~d1up.to_numpy()

    def plan(side, i, df):
        e, a = float(df["close"].iloc[i]), float(df["atr"].iloc[i])
        if sl == "h1":
            risk = (e - float(h1lo.iloc[i]) + 0.2 * float(a1.iloc[i])) if side == "MUA" else (float(h1hi.iloc[i]) - e + 0.2 * float(a1.iloc[i]))
        else:
            w = df.iloc[max(0, i - 11):i + 1]
            risk = (e - w["low"].min() + 0.3 * a) if side == "MUA" else (w["high"].max() - e + 0.3 * a)
        risk = float(min(max(risk, minr * a), maxr * a))
        d = 1 if side == "MUA" else -1
        return {"side": side, "entry": e, "sl": e - d * risk, "tp1": e + d * 2 * risk, "tp2": e + d * 3 * risk, "risk": risk}
    gold.plan = plan
    tr, _ = gold.backtest(m15, b, s, start=2000)
    gold.plan = orig_plan
    st = gold.stats(tr)
    half = m15.index[len(m15) // 2]
    s1, s2 = gold.stats([t for t in tr if t["t_in"] < half]), gold.stats([t for t in tr if t["t_in"] >= half])
    sides = {k: gold.stats([t for t in tr if t["side"] == k]).get("total_r") for k in ("MUA", "BÁN")}
    print(f"{name:28s} n={st['n']:3d} win={st.get('win')} avgR={st.get('avg_r')} tot={st.get('total_r')} pf={st.get('pf')} dd={st.get('max_dd_r')} | nửa1 {s1.get('total_r')} nửa2 {s2.get('total_r')} | {sides}")


run("A gốc")
run("B dừng lỗ H1", sl="h1", maxr=10)
run("C lọc D1", d1f=True)
run("D lọc D1 + dừng lỗ H1", d1f=True, sl="h1", maxr=10)
run("E rủi ro tối thiểu 1.5 ATR", minr=1.5)
run("F lọc D1 + rủi ro ≥1.5 ATR", d1f=True, minr=1.5)
run("G lọc D1 + rủi ro ≥2 ATR", d1f=True, minr=2.0, maxr=6)
