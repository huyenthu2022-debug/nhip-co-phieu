"""Kiểm định dài hạn hệ 3 khung trên PAXG/USDT (Binance có nhiều năm nến M15)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gold  # noqa: E402

m15 = gold.binance("15m", 70000)
h1 = gold.binance("1h", 20000)
print("m15", m15.index[0], m15.index[-1], len(m15), "h1", h1.index[0], len(h1))
d = gold.build(h1, m15, {"source": "PAXG", "spot_source": "", "spot": 0, "basis": 0})
print("Toàn bộ:", d["stats"])
import pandas as pd  # noqa: E402
m = gold.add_ind(m15)
# Thống kê theo từng năm
h4 = gold.add_ind(h1.resample("4h", origin="epoch").agg(gold.OHLC).dropna())
h4tr = gold.closed_on(h4.apply(gold.trend_of, axis=1), pd.Timedelta(hours=4), m.index).fillna("Đi ngang")
zone = gold.closed_on(gold.h1_zones(gold.add_ind(h1)), pd.Timedelta(hours=1), m.index).fillna("")
b, s = gold.setups(m, h4tr, zone)
tr, _ = gold.backtest(m, b, s)
for y in sorted({t["t_in"].year for t in tr}):
    print(y, gold.stats([t for t in tr if t["t_in"].year == y]))
for side in ("MUA", "BÁN"):
    print(side, gold.stats([t for t in tr if t["side"] == side]))
