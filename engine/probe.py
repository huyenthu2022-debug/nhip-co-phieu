"""Kiểm thử bản chốt lời 1:3 bằng chính backtest của engine trên 2 năm PAXG/USDT và 60 ngày GC=F."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import gold  # noqa: E402


def prep(h1r, m15r):
    m15 = gold.add_sweep(gold.add_ind(m15r))
    h1 = gold.add_ind(h1r)
    h4 = gold.add_ind(h1r.resample("4h", origin="epoch").agg(gold.OHLC).dropna())
    h4tr = gold.closed_on(h4.apply(gold.trend_of, axis=1), pd.Timedelta(hours=4), m15.index).fillna("Đi ngang")
    zone = gold.closed_on(gold.h1_zones(h1), pd.Timedelta(hours=1), m15.index).fillna("")
    b, s = gold.setups(m15, h4tr, zone)
    return m15, b, s


def report(tag, m15, b, s, start):
    for tp in (3.0, 4.0):
        gold.TP_R = tp
        tr, _ = gold.backtest(m15, b, s, start)
        st = gold.stats(tr)
        h = len(tr) // 2
        a, z = gold.stats(tr[:h]), gold.stats(tr[h:])
        sides = {sd: round(sum(x["r"] for x in tr if x["side"] == sd), 1) for sd in ("MUA", "BÁN")}
        months = pd.Series([x["r"] for x in tr], index=pd.to_datetime([x["t_in"] for x in tr])).resample("MS").sum()
        streak = cur = 0
        for x in tr:
            cur = 0 if x["r"] > 0 else cur + 1
            streak = max(streak, cur)
        print(f"## {tag} 1:{tp:g}", st, "| nửa đầu", a.get("total_r"), "nửa sau", z.get("total_r"),
              "| theo chiều", sides, f"| tháng lãi {(months > 0).sum()}/{len(months)} | chuỗi không thắng dài nhất {streak}")
        if tp == 3.0:
            for x in tr[-6:]:
                print("   ", gold.iso(x["t_in"]), x["side"], round(x["entry"], 1), "SL", round(x["sl"], 1),
                      "TP", round(x["tp"], 1), x["reason"], x["r"])
    gold.TP_R = 3.0


spot, _ = gold.spot_price()
report("PAXG 2 năm", *prep(gold.binance("1h", 20000), gold.binance("15m", 70000)), 2000)
gh1, _ = gold.shift_to_spot(gold.clean(gold.yahoo("1h", "730d")), spot)
gm15, _ = gold.shift_to_spot(gold.clean(gold.yahoo("15m", "60d")), spot)
report("GC=F 60 ngày", *prep(gh1, gm15), 200)
h1, m15, meta = gold.fetch_real()
d = gold.build(h1, m15, meta)
print("build OK:", d["price"], d["status"], d["rr"], d["stats"], d["open"])
