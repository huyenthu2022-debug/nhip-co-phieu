"""Tạo dữ liệu cho giao diện: web/data/signals.json và web/data/charts/<MÃ>.json.

    python engine/build.py            # toàn thị trường, dữ liệu thật từ API công khai
    python engine/build.py --demo     # dữ liệu mô phỏng, không cần mạng
    python engine/build.py --limit 100  # chỉ 100 mã đầu, để thử nhanh
"""
import argparse
import json
import math
import shutil
import sys
import time
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import indicators as ind  # noqa: E402
import sources  # noqa: E402
from universe import INDEX, fallback_listing  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "web" / "data"
HISTORY_DAYS = 365 * 3
CHART_BARS = 160
MIN_SESSIONS = 130
# Mã thanh khoản thấp dễ cho tín hiệu giả, nên chỉ phát tín hiệu và tính nhật ký khi GTGD TB20 đạt ngưỡng này.
MIN_SIGNAL_VALUE_BN = 1.0


# ---------- Nguồn dữ liệu ----------

def fetch_real(limit=None):
    try:
        lst = sources.listing()
        print(f"Danh sách: {len(lst)} cổ phiếu HOSE/HNX/UPCoM")
    except Exception as e:
        print(f"Không lấy được danh sách toàn thị trường ({e}), dùng danh sách dự phòng", file=sys.stderr)
        lst = fallback_listing()
    if limit:
        lst = lst[:limit]
    prices = {}
    try:
        prices[INDEX], _ = sources.fetch(INDEX, is_index=True, days=HISTORY_DAYS)
    except Exception as e:
        sys.exit(f"Không lấy được VNINDEX ({e}), dừng.")
    prices.update(sources.fetch_many([r["sym"] for r in lst], days=HISTORY_DAYS))
    # Chưa có nguồn chỉ số cơ bản miễn phí ổn định; giao diện hiện "–" cho P/E, P/B, ROE.
    return lst, prices, {}


def demo_data(seed=6):
    """Giá mô phỏng có tương quan ngành và chu kỳ thị trường. KHÔNG phải giá thật."""
    lst = fallback_listing()
    rng = np.random.default_rng(seed)
    days = pd.bdate_range(end=pd.Timestamp(date.today()) - pd.Timedelta(days=1), periods=760)
    n = len(days)
    regime = np.repeat(rng.choice([-0.0012, 0.0002, 0.0014], size=n // 60 + 1, p=[0.3, 0.3, 0.4]), 60)[:n]
    mkt = regime + rng.normal(0, 0.011, n)
    sector_f = {r["sector"]: np.repeat(rng.normal(0, 0.0012, n // 80 + 1), 80)[:n] + rng.normal(0, 0.008, n)
                for r in lst}

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
    for r in lst:
        beta = rng.uniform(0.7, 1.5)
        alpha = rng.normal(0, 0.0006)
        rets = alpha + beta * mkt + sector_f[r["sector"]] + rng.normal(0, 0.014, n)
        prices[r["sym"]] = make(rets, rng.uniform(12, 110), rng.uniform(1e6, 2.5e7))
        funda[r["sym"]] = {"pe": round(float(rng.uniform(6, 28)), 1), "pb": round(float(rng.uniform(0.8, 4.5)), 2),
                           "roe": round(float(rng.uniform(5, 28)), 1)}
    return lst, prices, funda


# ---------- Tính toán ----------

def r2(x, nd=2):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), nd)


def snapshot(meta, df, index_close):
    e = ind.enrich(df)
    last = e.iloc[-1]
    ts = ind.trend_short(last, e["ema20"].iloc[-6])
    tm = ind.trend_mid(last, e["ema50"].iloc[-11])
    vol_ratio = float(last["volume"] / last["vol20"]) if last["vol20"] else 0
    value_bn = float((e["close"] * e["volume"]).iloc[-20:].mean() * 1000 / 1e9)  # tỷ đồng/phiên
    liquid = value_bn >= MIN_SIGNAL_VALUE_BN
    trades, pos = ind.backtest(e) if liquid else ([], None)

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

    row = {
        "sym": meta["sym"], "ex": meta["exchange"], "sector": meta["sector"], "ind": meta["industry"],
        "name": meta["name"],
        "price": r2(last["close"]), "chg": r2((last["close"] / e["close"].iloc[-2] - 1) * 100),
        "chg20": r2((last["close"] / e["close"].iloc[-21] - 1) * 100, 1),
        "trend_s": ts, "trend_m": tm,
        "_rs_raw": ind.rs_raw(df["close"]),
        "rs_line_high": bool(rs_line.iloc[-1] >= rs_line.iloc[-63:].max() * 0.995),
        "cmf": r2(last["cmf"]), "mfi": r2(last["mfi"], 0), "vol_ratio": r2(vol_ratio),
        "value_bn": r2(value_bn, 1), "flow": ind.money_flow_label(float(last["cmf"]), vol_ratio),
        "mtf": ind.multi_tf(df), "rsi": r2(last["rsi"], 0),
        "signal": signal, "sig": sig, "_trades": trades,
    }
    chart = {
        "d": [d.strftime("%Y-%m-%d") for d in tail.index],
        "o": [r2(v) for v in tail["open"]], "h": [r2(v) for v in tail["high"]],
        "l": [r2(v) for v in tail["low"]], "c": [r2(v) for v in tail["close"]],
        "v": [int(v) for v in tail["volume"]],
        "e20": [r2(v) for v in tail["ema20"]], "e50": [r2(v) for v in tail["ema50"]],
        "m": markers,
    }
    return row, chart, float(tail["ema50"].iloc[-1])


def journal(rows, prices, index_df):
    traded = [r for r in rows if r["value_bn"] >= MIN_SIGNAL_VALUE_BN]
    trades = [dict(t, sym=r["sym"]) for r in traded for t in r["_trades"]]
    if not trades:
        return {"n": 0, "recent": []}
    rets = np.array([t["ret"] for t in trades])
    wins, losses = rets[rets > 0], rets[rets <= 0]
    first = index_df.index[60]
    last = index_df.index[-1]
    years = max((last - first).days / 365.25, 0.1)

    # Chiến lược: mỗi mã một phần vốn bằng nhau, lãi kép theo từng lệnh của mã đó.
    # Chỉ tính mã có đủ lịch sử từ ngày bắt đầu để so công bằng với mua và nắm giữ.
    full = [r for r in traded if prices[r["sym"]].index[0] <= first]
    eq = [np.prod([1 + t["ret"] for t in r["_trades"] if t["entry_date"] >= first]) for r in full]
    bh = [prices[r["sym"]]["close"].iloc[-1] / prices[r["sym"]]["close"].loc[first:].iloc[0] for r in full]
    idx = index_df["close"].iloc[-1] / index_df["close"].loc[first:].iloc[0]

    def cagr(x):
        return r2((x ** (1 / years) - 1) * 100, 1) if x and x > 0 else None

    recent = sorted(trades, key=lambda t: t["exit_date"], reverse=True)[:60]
    return {
        "n": len(trades), "n_stocks": len(traded), "win_rate": r2(len(wins) / len(trades) * 100, 1),
        "avg_win": r2(wins.mean() * 100 if len(wins) else 0, 1),
        "avg_loss": r2(losses.mean() * 100 if len(losses) else 0, 1),
        "profit_factor": r2(wins.sum() / -losses.sum() if losses.sum() < 0 else None),
        "avg_days": r2(np.mean([t["days"] for t in trades]), 1),
        "years": r2(years, 1), "from": first.strftime("%Y-%m-%d"), "min_value_bn": MIN_SIGNAL_VALUE_BN,
        "cagr_strategy": cagr(np.mean(eq)) if eq else None, "cagr_bh": cagr(np.mean(bh)) if bh else None,
        "cagr_index": cagr(idx),
        "recent": [{"sym": t["sym"], "in": t["entry_date"].strftime("%Y-%m-%d"),
                    "out": t["exit_date"].strftime("%Y-%m-%d"), "entry": r2(t["entry"]), "exit": r2(t["exit"]),
                    "ret": r2(t["ret"] * 100, 1), "reason": t["reason"], "days": t["days"]} for t in recent],
    }


def sector_stats(rows):
    """Thống kê theo ngành ICB cấp 2, kèm các ngành con cấp 3. Trung bình chỉ tính mã đủ thanh khoản."""
    out = []
    for sec in sorted({r["sector"] for r in rows}):
        all_ = [r for r in rows if r["sector"] == sec]
        liq = [r for r in all_ if r["value_bn"] >= MIN_SIGNAL_VALUE_BN] or all_
        out.append({
            "name": sec, "n": len(all_), "n_liq": sum(r["value_bn"] >= MIN_SIGNAL_VALUE_BN for r in all_),
            "rs": r2(np.mean([r["rs"] for r in liq]), 0), "score": r2(np.mean([r["score"] for r in liq]), 1),
            "chg20": r2(np.mean([r["chg20"] for r in liq]), 1),
            "up": sum(r["trend_m"] == "Tăng" for r in liq), "base": len(liq),
            "n_buy": sum(r["signal"] == "MUA" for r in all_),
            "value_bn": r2(sum(r["value_bn"] for r in all_), 0),
            "top": [r["sym"] for r in sorted(liq, key=lambda x: -x["score"])[:3]],
            "subs": sorted({r["ind"] for r in all_ if r["ind"]}),
        })
    out.sort(key=lambda s: -s["score"])
    return out


def build(lst, prices, funda, demo):
    index_df = prices[INDEX]
    rows, charts, above50 = [], {}, []
    t0 = time.time()
    for meta in lst:
        df = prices.get(meta["sym"])
        if df is None or len(df) < MIN_SESSIONS or df["close"].iloc[-1] <= 0:
            continue
        # Bỏ mã đã ngừng giao dịch (phiên cuối cũ hơn VN-Index quá 10 ngày)
        if (index_df.index[-1] - df.index[-1]).days > 10:
            continue
        try:
            row, chart, e50 = snapshot(meta, df, index_df["close"])
        except Exception as ex:
            print(f"  {meta['sym']}: bỏ qua ({ex})", file=sys.stderr)
            continue
        row.update(funda.get(meta["sym"]) or {})
        rows.append(row)
        charts[meta["sym"]] = chart
        if row["value_bn"] >= MIN_SIGNAL_VALUE_BN:
            above50.append(row["price"] > e50)
    print(f"Tính chỉ báo {len(rows)} mã trong {time.time() - t0:.0f}s")

    # RS 1-99: xếp hạng phần trăm của hiệu suất có trọng số trên toàn bộ mã
    raw = pd.Series({r["sym"]: r["_rs_raw"] for r in rows})
    rank = (raw.rank(pct=True) * 98 + 1).round()
    for r in rows:
        v = rank[r["sym"]]
        r["rs"] = int(v) if not math.isnan(v) else 1
        r["score"] = ind.core_score(r["trend_s"], r["trend_m"], r["rs"], r["cmf"] or 0, r["vol_ratio"] or 0, r["mtf"])

    jr = journal(rows, prices, index_df)
    for r in rows:
        r.pop("_rs_raw"); r.pop("_trades")

    ie = ind.enrich(index_df)
    il = ie.iloc[-1]
    by_ex = {}
    for r in rows:
        by_ex[r["ex"]] = by_ex.get(r["ex"], 0) + 1
    data = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "as_of": index_df.index[-1].strftime("%Y-%m-%d"),
        "demo": demo, "min_value_bn": MIN_SIGNAL_VALUE_BN, "by_exchange": by_ex,
        "market": {
            "index": r2(il["close"]), "chg": r2((il["close"] / ie["close"].iloc[-2] - 1) * 100),
            "trend_s": ind.trend_short(il, ie["ema20"].iloc[-6]), "trend_m": ind.trend_mid(il, ie["ema50"].iloc[-11]),
            "breadth50": r2(np.mean(above50) * 100 if above50 else 0, 0),
            "n_up": sum(r["chg"] > 0 for r in rows), "n_down": sum(r["chg"] < 0 for r in rows),
            "n_buy": sum(r["signal"] == "MUA" for r in rows), "n_hold": sum(r["signal"] == "NẮM GIỮ" for r in rows),
            "n_sell": sum(r["signal"] == "BÁN" for r in rows),
            "chart": {"d": [d.strftime("%Y-%m-%d") for d in ie.index[-CHART_BARS:]],
                      "c": [r2(v) for v in ie["close"].iloc[-CHART_BARS:]]},
        },
        "sectors": sector_stats(rows), "stocks": sorted(rows, key=lambda r: -r["score"]), "journal": jr,
    }
    return data, charts


def write(data, charts):
    DATA.mkdir(parents=True, exist_ok=True)
    cdir = DATA / "charts"
    shutil.rmtree(cdir, ignore_errors=True)
    cdir.mkdir()
    for sym, c in charts.items():
        (cdir / f"{sym}.json").write_text(json.dumps(c, separators=(",", ":")), encoding="utf-8")
    out = DATA / "signals.json"
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Đã ghi {out} ({out.stat().st_size // 1024} KB, {len(data['stocks'])} mã) và {len(charts)} biểu đồ")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="dùng dữ liệu mô phỏng")
    ap.add_argument("--limit", type=int, help="chỉ lấy N mã đầu danh sách (để thử)")
    a = ap.parse_args()
    lst, prices, funda = demo_data() if a.demo else fetch_real(a.limit)
    got = len(prices) - 1
    if got < len(lst) // 2:
        sys.exit(f"Chỉ lấy được {got}/{len(lst)} mã, dừng để không đăng dữ liệu thiếu.")
    data, charts = build(lst, prices, funda, a.demo)
    write(data, charts)


if __name__ == "__main__":
    main()
