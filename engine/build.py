"""Tạo web/data/signals.json cho giao diện.

    python engine/build.py            # dữ liệu thật từ API công khai (DNSE, Vietcap, TCBS)
    python engine/build.py --demo     # dữ liệu mô phỏng, không cần mạng
"""
import argparse
import json
import math
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import indicators as ind  # noqa: E402
import sources  # noqa: E402
from universe import INDEX, UNIVERSE, all_symbols, sector_of  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "web" / "data" / "signals.json"
HISTORY_DAYS = 365 * 3
CHART_BARS = 160


# ---------- Nguồn dữ liệu ----------

def fetch_real(symbols):
    prices, used = {}, {}
    for sym in [INDEX] + symbols:
        try:
            prices[sym], src = sources.fetch(sym, is_index=(sym == INDEX), days=HISTORY_DAYS)
            used[src] = used.get(src, 0) + 1
        except Exception as e:
            print(f"  {sym}: không lấy được dữ liệu ({e})", file=sys.stderr)
        time.sleep(0.3)
    print(f"Nguồn đã dùng: {used}, lấy được {len(prices)}/{len(symbols) + 1} mã")
    # Chưa có nguồn chỉ số cơ bản miễn phí ổn định; giao diện hiện "–" cho P/E, P/B, ROE.
    return prices, {}


def demo_data(symbols, seed=6):
    """Giá mô phỏng có tương quan ngành và chu kỳ thị trường. KHÔNG phải giá thật."""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range(end=pd.Timestamp(date.today()) - pd.Timedelta(days=1), periods=760)
    n = len(days)
    regime = np.repeat(rng.choice([-0.0012, 0.0002, 0.0014], size=n // 60 + 1, p=[0.3, 0.3, 0.4]), 60)[:n]
    mkt = regime + rng.normal(0, 0.011, n)
    sector_f = {s: np.repeat(rng.normal(0, 0.0012, n // 80 + 1), 80)[:n] + rng.normal(0, 0.008, n) for s in UNIVERSE}

    def make(rets, start, base_vol):
        close = start * np.exp(np.cumsum(rets))
        tick = 0.05 if start < 50 else 0.1
        close = np.round(close / tick) * tick
        opn = np.round(np.r_[start, close[:-1]] * (1 + rng.normal(0, 0.004, n)) / tick) * tick
        spread = np.abs(rng.normal(0, 0.012, n)) * close
        high = np.maximum(opn, close) + spread * rng.random(n)
        low = np.minimum(opn, close) - spread * rng.random(n)
        vol = base_vol * np.exp(rng.normal(0, 0.35, n) + 12 * np.abs(rets) + 8 * np.clip(rets, 0, None))
        return pd.DataFrame({"open": opn, "high": high, "low": low, "close": close, "volume": vol.round(-2)}, index=days)

    prices = {INDEX: make(mkt, 1050, 6e8)}
    funda = {}
    for s in symbols:
        beta = rng.uniform(0.7, 1.5)
        alpha = rng.normal(0, 0.0006)
        rets = alpha + beta * mkt + sector_f[sector_of(s)] + rng.normal(0, 0.014, n)
        prices[s] = make(rets, rng.uniform(12, 110), rng.uniform(1e6, 2.5e7))
        funda[s] = {"pe": round(float(rng.uniform(6, 28)), 1), "pb": round(float(rng.uniform(0.8, 4.5)), 2),
                    "roe": round(float(rng.uniform(5, 28)), 1)}
    return prices, funda


# ---------- Tính toán ----------

def r2(x, nd=2):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), nd)


def snapshot(sym, df, index_close):
    e = ind.enrich(df)
    last = e.iloc[-1]
    ts = ind.trend_short(last, e["ema20"].iloc[-6])
    tm = ind.trend_mid(last, e["ema50"].iloc[-11])
    vol_ratio = float(last["volume"] / last["vol20"]) if last["vol20"] else 0
    trades, pos = ind.backtest(e)

    # Trạng thái tín hiệu hiện tại
    signal, sig = "—", None
    if pos is not None:
        age = len(e) - 1 - pos["entry_i"]
        signal = "MUA" if age <= 2 else "NẮM GIỮ"
        sig = {"date": pos["entry_date"].strftime("%Y-%m-%d"), "entry": r2(pos["entry"]),
               "stop": r2(pos["stop"]), "t1": r2(pos["t1"]), "t2": r2(pos["t2"]),
               "t1_hit": pos["t1_hit"], "pnl": r2((last["close"] / pos["entry"] - 1) * 100, 1), "age": age}
    elif trades and (e.index[-1] - trades[-1]["exit_date"]).days <= 4:
        signal = "BÁN"
        t = trades[-1]
        sig = {"date": t["exit_date"].strftime("%Y-%m-%d"), "entry": r2(t["entry"]), "exit": r2(t["exit"]),
               "reason": t["reason"], "pnl": r2(t["ret"] * 100, 1)}

    rs_line = (df["close"] / index_close.reindex(df.index).ffill())
    tail = e.iloc[-CHART_BARS:]
    markers = []
    for t in trades + ([{"entry_date": pos["entry_date"]}] if pos else []):
        if t["entry_date"] >= tail.index[0]:
            markers.append({"d": t["entry_date"].strftime("%Y-%m-%d"), "k": "B"})
        if "exit_date" in t and t["exit_date"] >= tail.index[0]:
            markers.append({"d": t["exit_date"].strftime("%Y-%m-%d"), "k": "S"})

    return {
        "sym": sym, "sector": sector_of(sym),
        "price": r2(last["close"]), "chg": r2((last["close"] / e["close"].iloc[-2] - 1) * 100),
        "chg20": r2((last["close"] / e["close"].iloc[-21] - 1) * 100, 1),
        "trend_s": ts, "trend_m": tm,
        "_rs_raw": ind.rs_raw(df["close"]),
        "rs_line_high": bool(rs_line.iloc[-1] >= rs_line.iloc[-63:].max() * 0.995),
        "cmf": r2(last["cmf"]), "mfi": r2(last["mfi"], 0), "vol_ratio": r2(vol_ratio),
        "value_bn": r2((e["close"] * e["volume"]).iloc[-20:].mean() * 1000 / 1e9, 1),  # tỷ đồng/phiên
        "flow": ind.money_flow_label(float(last["cmf"]), vol_ratio),
        "mtf": ind.multi_tf(df), "rsi": r2(last["rsi"], 0),
        "signal": signal, "sig": sig,
        "_trades": trades,
        "chart": {
            "d": [d.strftime("%Y-%m-%d") for d in tail.index],
            "o": [r2(v) for v in tail["open"]], "h": [r2(v) for v in tail["high"]],
            "l": [r2(v) for v in tail["low"]], "c": [r2(v) for v in tail["close"]],
            "v": [int(v) for v in tail["volume"]],
            "e20": [r2(v) for v in tail["ema20"]], "e50": [r2(v) for v in tail["ema50"]],
            "m": markers,
        },
    }


def journal(rows, prices, index_df):
    trades = [dict(t, sym=r["sym"]) for r in rows for t in r["_trades"]]
    if not trades:
        return {"n": 0, "recent": []}
    rets = np.array([t["ret"] for t in trades])
    wins, losses = rets[rets > 0], rets[rets <= 0]
    first = min(df.index[60] for s, df in prices.items() if s != INDEX)
    last = max(df.index[-1] for df in prices.values())
    years = max((last - first).days / 365.25, 0.1)

    # Chiến lược: mỗi mã một phần vốn bằng nhau, lãi kép theo từng lệnh của mã đó.
    eq = [np.prod([1 + t["ret"] for t in r["_trades"]]) for r in rows]
    bh = [prices[r["sym"]]["close"].iloc[-1] / prices[r["sym"]]["close"].loc[first:].iloc[0] for r in rows]
    idx = index_df["close"].iloc[-1] / index_df["close"].loc[first:].iloc[0]

    def cagr(x):
        return r2((x ** (1 / years) - 1) * 100, 1)

    recent = sorted(trades, key=lambda t: t["exit_date"], reverse=True)[:40]
    return {
        "n": len(trades), "win_rate": r2(len(wins) / len(trades) * 100, 1),
        "avg_win": r2(wins.mean() * 100 if len(wins) else 0, 1),
        "avg_loss": r2(losses.mean() * 100 if len(losses) else 0, 1),
        "profit_factor": r2(wins.sum() / -losses.sum() if losses.sum() < 0 else None),
        "avg_days": r2(np.mean([t["days"] for t in trades]), 1),
        "years": r2(years, 1), "from": first.strftime("%Y-%m-%d"),
        "cagr_strategy": cagr(np.mean(eq)), "cagr_bh": cagr(np.mean(bh)), "cagr_index": cagr(idx),
        "recent": [{"sym": t["sym"], "in": t["entry_date"].strftime("%Y-%m-%d"),
                    "out": t["exit_date"].strftime("%Y-%m-%d"), "entry": r2(t["entry"]), "exit": r2(t["exit"]),
                    "ret": r2(t["ret"] * 100, 1), "reason": t["reason"], "days": t["days"]} for t in recent],
    }


def build(prices, funda, demo):
    index_df = prices[INDEX]
    rows = []
    for sym in all_symbols():
        df = prices.get(sym)
        if df is None or len(df) < 130:
            continue
        row = snapshot(sym, df, index_df["close"])
        row.update(funda.get(sym) or {})
        rows.append(row)

    # RS 1-99: xếp hạng phần trăm của hiệu suất có trọng số trong danh sách theo dõi
    raw = pd.Series({r["sym"]: r["_rs_raw"] for r in rows})
    rank = (raw.rank(pct=True) * 98 + 1).round()
    for r in rows:
        r["rs"] = int(rank[r["sym"]]) if not math.isnan(rank[r["sym"]]) else None
        r["score"] = ind.core_score(r["trend_s"], r["trend_m"], r["rs"], r["cmf"] or 0, r["vol_ratio"] or 0, r["mtf"])

    jr = journal(rows, prices, index_df)
    for r in rows:
        r.pop("_rs_raw"); r.pop("_trades")

    ie = ind.enrich(index_df)
    il = ie.iloc[-1]
    sectors = []
    for sec in UNIVERSE:
        rs_ = [r for r in rows if r["sector"] == sec]
        if rs_:
            sectors.append({"name": sec, "n": len(rs_), "rs": r2(np.mean([r["rs"] for r in rs_]), 0),
                            "score": r2(np.mean([r["score"] for r in rs_]), 1),
                            "chg20": r2(np.mean([r["chg20"] for r in rs_]), 1),
                            "up": sum(r["trend_m"] == "Tăng" for r in rs_),
                            "top": [r["sym"] for r in sorted(rs_, key=lambda x: -x["score"])[:3]]})
    sectors.sort(key=lambda s: -s["score"])

    return {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "as_of": index_df.index[-1].strftime("%Y-%m-%d"),
        "demo": demo,
        "market": {
            "index": r2(il["close"]), "chg": r2((il["close"] / ie["close"].iloc[-2] - 1) * 100),
            "trend_s": ind.trend_short(il, ie["ema20"].iloc[-6]), "trend_m": ind.trend_mid(il, ie["ema50"].iloc[-11]),
            "breadth50": r2(np.mean([r["price"] > r["chart"]["e50"][-1] for r in rows]) * 100, 0),
            "n_buy": sum(r["signal"] == "MUA" for r in rows), "n_hold": sum(r["signal"] == "NẮM GIỮ" for r in rows),
            "n_sell": sum(r["signal"] == "BÁN" for r in rows),
            "chart": {"d": [d.strftime("%Y-%m-%d") for d in ie.index[-CHART_BARS:]],
                      "c": [r2(v) for v in ie["close"].iloc[-CHART_BARS:]]},
        },
        "sectors": sectors, "stocks": sorted(rows, key=lambda r: -r["score"]), "journal": jr,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="dùng dữ liệu mô phỏng")
    a = ap.parse_args()
    syms = all_symbols()
    prices, funda = demo_data(syms) if a.demo else fetch_real(syms)
    if INDEX not in prices:
        sys.exit("Không lấy được VNINDEX, dừng.")
    if len(prices) - 1 < len(syms) // 2:
        sys.exit(f"Chỉ lấy được {len(prices) - 1}/{len(syms)} mã, dừng để không đăng dữ liệu thiếu.")
    data = build(prices, funda, a.demo)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Đã ghi {OUT} ({OUT.stat().st_size // 1024} KB, {len(data['stocks'])} mã)")


if __name__ == "__main__":
    main()
