"""Xuất toàn bộ lệnh của hệ vàng hiện tại: 60 ngày GC=F và 2 năm PAXG/USDT, dạng CSV trong log."""
import sys
from pathlib import Path

import numpy as np
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




def report(tag, tr):
    df = pd.DataFrame(tr)
    df["t_vn"] = df["t_in"].dt.tz_convert("Asia/Ho_Chi_Minh")
    df["month"] = df["t_vn"].dt.strftime("%Y-%m")
    h = df["t_in"].dt.hour  # giờ UTC
    df["phiên"] = np.where(h < 7, "Á (7h-14h VN)", np.where(h < 13, "Âu (14h-20h VN)", "Mỹ (20h-7h VN)"))
    df["kq"] = np.where(df["r"] > 0, "thắng", np.where(df["r"] == 0, "hoà", "thua"))
    df["sl_usd"] = (df["entry"] - df["sl"]).abs()
    df["giờ giữ"] = (df["t_out"] - df["t_in"]).dt.total_seconds() / 3600

    def agg(g):
        r = g["r"]
        return pd.Series({"lệnh": len(r), "thắng": (r > 0).sum(), "hoà": (r == 0).sum(), "thua": (r < 0).sum(),
                          "tổng R": r.sum(), "TB R": round(r.mean(), 2)})
    print(f"##### {tag}")
    print("TỔNG:", agg(df).to_dict(), "| SL TB", round(df.sl_usd.mean(), 1), "giá, trung vị", round(df.sl_usd.median(), 1),
          "| giữ lệnh TB", round(df["giờ giữ"].mean(), 1), "giờ, trung vị", round(df["giờ giữ"].median(), 1))
    print("THEO CHIỀU\n" + df.groupby("side").apply(agg, include_groups=False).to_string())
    print("THEO PHIÊN\n" + df.groupby("phiên").apply(agg, include_groups=False).to_string())
    print("THEO THÁNG\n" + df.groupby("month").apply(agg, include_groups=False).to_string())
    k = (df["r"] < 0).astype(int).to_numpy()
    run = best = 0
    for x in k:
        run = run + 1 if x else 0
        best = max(best, run)
    nw = (df["r"] <= 0).astype(int).to_numpy()
    run = best2 = 0
    for x in nw:
        run = run + 1 if x else 0
        best2 = max(best2, run)
    eq = df["r"].cumsum()
    print("chuỗi thua liên tiếp dài nhất:", best, "| chuỗi lệnh không thắng dài nhất:", best2,
          "| sụt giảm lớn nhất:", round((eq.cummax().clip(lower=0) - eq).max(), 1), "R")


spot, _ = gold.spot_price()
gh1, _ = gold.shift_to_spot(gold.clean(gold.yahoo("1h", "730d")), spot)
gm15, _ = gold.shift_to_spot(gold.clean(gold.yahoo("15m", "60d")), spot)
tr, pos = run(gh1, gm15)
report("GC=F 60 ngày", tr)
tr2, _ = run(gold.binance("1h", 20000), gold.binance("15m", 70000))
report("PAXG 2 năm", tr2)
