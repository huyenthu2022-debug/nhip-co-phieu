"""Xuất toàn bộ lệnh của hệ vàng hiện tại: 60 ngày GC=F và 2 năm PAXG/USDT, dạng CSV trong log."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import gold  # noqa: E402


def run(h1r, m15r):
    m15 = gold.add_sweep(gold.add_ind(m15r))
    h1 = gold.add_ind(h1r)
    h4 = gold.add_ind(h1r.resample("4h", origin="epoch").agg(gold.OHLC).dropna())
    h4tr = gold.closed_on(h4.apply(gold.trend_of, axis=1), pd.Timedelta(hours=4), m15.index).fillna("Đi ngang")
    zone = gold.closed_on(gold.h1_zones(h1), pd.Timedelta(hours=1), m15.index).fillna("")
    b, s = gold.setups(m15, h4tr, zone)
    return gold.backtest(m15, b, s, start=2000 if len(m15) > 20000 else 200)


def dump(tag, tr):
    print(f"=== {tag} ===")
    print("t_in,t_out,side,liq,entry,sl,be,tp,exit,r,reason")
    for t in tr:
        print(",".join(str(x) for x in (gold.iso(t["t_in"]), gold.iso(t["t_out"]), t["side"], round(t["liq"], 2),
                                         round(t["entry"], 2), round(t["sl"], 2), round(t["be"], 2), round(t["tp"], 2),
                                         round(t["exit"], 2), t["r"], t["reason"])))


spot, _ = gold.spot_price()
gh1, _ = gold.shift_to_spot(gold.clean(gold.yahoo("1h", "730d")), spot)
gm15, _ = gold.shift_to_spot(gold.clean(gold.yahoo("15m", "60d")), spot)
tr, pos = run(gh1, gm15)
dump("GC=F 60 ngày", tr)
print("đang mở:", pos)
tr2, _ = run(gold.binance("1h", 20000), gold.binance("15m", 70000))
dump("PAXG 2 năm", tr2)
