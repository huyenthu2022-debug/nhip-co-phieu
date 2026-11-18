"""Tín hiệu mua/bán vàng XAUUSD: ghi web/data/gold.json.

    python engine/gold.py          # dữ liệu thật (Yahoo GC=F + giá giao ngay gold-api.com)
    python engine/gold.py --demo   # dữ liệu mô phỏng, không cần mạng

Nguồn: nến 1 giờ hợp đồng vàng tương lai COMEX (GC=F, Yahoo) được dời theo chênh lệch
với giá giao ngay hiện tại để mức giá khớp XAUUSD; dự phòng là PAXG/USDT (Binance).

Quy tắc (khung H1, lọc xu hướng bằng H4):
  MUA  khi H4 tăng (giá > EMA50 > EMA200), H1 có EMA20 > EMA50, giá vừa chạm lại EMA20
       trong 3 nến gần nhất rồi đóng cửa trên EMA20, RSI14 cắt lên 50 hoặc MACD hist chuyển dương.
  BÁN  ngược lại khi H4 giảm.
  Dừng lỗ sau đáy/đỉnh 10 nến gần nhất thêm 0,3 ATR (rủi ro giới hạn 0,8–3 ATR).
  Chốt lời TP1 = 2R (R:R 1:2), TP2 = 3R (R:R 1:3). Chạm TP1 thì chốt một nửa và dời dừng lỗ về giá vào.
"""
import argparse
import json
import math
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from indicators import atr, ema, macd_hist, rsi  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "web" / "data" / "gold.json"
VN_TZ = timezone(timedelta(hours=7))
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}
RR_TP1, RR_TP2 = 2.0, 3.0
CHART_H1, CHART_H4 = 360, 300


def _get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30) as r:
        return json.loads(r.read().decode())


# ---------- Dữ liệu ----------

def spot_price():
    try:
        return float(_get("https://api.gold-api.com/price/XAU")["price"]), "gold-api.com"
    except Exception as e:
        print(f"gold-api lỗi: {e}", file=sys.stderr)
    j = _get("https://data-api.binance.vision/api/v3/ticker/price?symbol=PAXGUSDT")
    return float(j["price"]), "PAXG/USDT"


def yahoo_h1():
    j = _get("https://query2.finance.yahoo.com/v8/finance/chart/GC=F?interval=1h&range=730d")
    r = j["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    df = pd.DataFrame({k: q[k] for k in ("open", "high", "low", "close", "volume")},
                      index=pd.to_datetime(r["timestamp"], unit="s", utc=True))
    return df.dropna(subset=["open", "high", "low", "close"]).astype(float)


def binance_h1(n=8000):
    rows, end = [], None
    while len(rows) < n:
        url = "https://data-api.binance.vision/api/v3/klines?symbol=PAXGUSDT&interval=1h&limit=1000"
        if end:
            url += f"&endTime={end}"
        k = _get(url)
        if not k:
            break
        rows = k + rows
        end = k[0][0] - 1
    df = pd.DataFrame([[float(x) for x in r[1:6]] for r in rows], columns=["open", "high", "low", "close", "volume"],
                      index=pd.to_datetime([r[0] for r in rows], unit="ms", utc=True))
    df = df[~df.index.duplicated()].sort_index()
    return df[df.index.dayofweek < 5]  # vàng giao ngay nghỉ cuối tuần, bỏ nến thứ 7


def fetch_real():
    spot, spot_src = spot_price()
    try:
        df, src = yahoo_h1(), "COMEX GC=F (Yahoo), dời theo giá giao ngay"
    except Exception as e:
        print(f"Yahoo lỗi: {e}, dùng PAXG", file=sys.stderr)
        df, src = binance_h1(), "PAXG/USDT (Binance)"
    df = df[~df.index.duplicated(keep="last")].sort_index()
    basis = spot - df["close"].iloc[-1]
    if abs(basis) < 0.05 * spot:  # chỉ dời khi chênh lệch hợp lý (phí lưu kho hợp đồng tương lai)
        for k in ("open", "high", "low", "close"):
            df[k] = df[k] + basis
    return df, {"source": src, "spot_source": spot_src, "spot": spot, "basis": round(float(basis), 2)}


def demo():
    rng = np.random.default_rng(7)
    idx = pd.date_range(end=pd.Timestamp.now(tz="UTC").floor("h"), periods=9000, freq="h")
    idx = idx[idx.dayofweek < 5]
    n = len(idx)
    drift = np.repeat(rng.choice([-0.0004, 0.0001, 0.0005], size=n // 200 + 1), 200)[:n]
    c = 3000 * np.exp(np.cumsum(drift + rng.normal(0, 0.0025, n)))
    o = np.r_[c[0], c[:-1]]
    sp = np.abs(rng.normal(0, 0.0018, n)) * c
    df = pd.DataFrame({"open": o, "high": np.maximum(o, c) + sp, "low": np.minimum(o, c) - sp, "close": c,
                       "volume": rng.integers(1000, 9000, n).astype(float)}, index=idx)
    return df, {"source": "MÔ PHỎNG", "spot_source": "MÔ PHỎNG", "spot": float(c[-1]), "basis": 0}


# ---------- Chỉ báo và tín hiệu ----------

def to_h4(df):
    return df.resample("4h", origin="epoch").agg({"open": "first", "high": "max", "low": "min",
                                                   "close": "last", "volume": "sum"}).dropna()


def add_ind(df):
    df = df.copy()
    c = df["close"]
    df["ema20"], df["ema50"], df["ema200"] = ema(c, 20), ema(c, 50), ema(c, 200)
    df["rsi"], df["macdh"], df["atr"] = rsi(c), macd_hist(c), atr(df)
    return df


def trend_of(row):
    if row["close"] > row["ema50"] > row["ema200"]:
        return "Tăng"
    if row["close"] < row["ema50"] < row["ema200"]:
        return "Giảm"
    return "Đi ngang"


def h4_trend_on_h1(h1, h4):
    """Xu hướng H4 của nến H4 đã đóng gần nhất, gắn vào từng nến H1 (không nhìn trước tương lai)."""
    tr = h4.apply(trend_of, axis=1)
    tr.index = tr.index + pd.Timedelta(hours=4)  # chỉ biết khi nến H4 đóng
    return tr.reindex(h1.index, method="ffill").fillna("Đi ngang")


def setups(h1, h4tr):
    c, e20 = h1["close"], h1["ema20"]
    touched_dn = (h1["low"] <= e20).rolling(3).max().astype(bool)
    touched_up = (h1["high"] >= e20).rolling(3).max().astype(bool)
    mom_up = ((h1["rsi"] > 50) & (h1["rsi"].shift() <= 50)) | ((h1["macdh"] > 0) & (h1["macdh"].shift() <= 0))
    mom_dn = ((h1["rsi"] < 50) & (h1["rsi"].shift() >= 50)) | ((h1["macdh"] < 0) & (h1["macdh"].shift() >= 0))
    buy = (h4tr == "Tăng") & (e20 > h1["ema50"]) & touched_dn & (c > e20) & mom_up & (h1["rsi"] < 70)
    sell = (h4tr == "Giảm") & (e20 < h1["ema50"]) & touched_up & (c < e20) & mom_dn & (h1["rsi"] > 30)
    return buy.fillna(False).to_numpy(), sell.fillna(False).to_numpy()


def plan(side, i, h1):
    """Điểm vào, dừng lỗ, TP1 (1:2), TP2 (1:3) cho tín hiệu ở nến i."""
    entry, a = float(h1["close"].iloc[i]), float(h1["atr"].iloc[i])
    lo, hi = float(h1["low"].iloc[i - 9:i + 1].min()), float(h1["high"].iloc[i - 9:i + 1].max())
    risk = (entry - lo + 0.3 * a) if side == "MUA" else (hi - entry + 0.3 * a)
    risk = min(max(risk, 0.8 * a), 3 * a)
    d = 1 if side == "MUA" else -1
    return {"side": side, "entry": entry, "sl": entry - d * risk, "tp1": entry + d * RR_TP1 * risk,
            "tp2": entry + d * RR_TP2 * risk, "risk": risk}


def backtest(h1, buy, sell, start=250):
    """Một lệnh mỗi lúc. Cùng nến chạm cả dừng lỗ và mục tiêu thì tính dừng lỗ trước (thận trọng).
    Kết quả tính theo R: thua cả lệnh = -1R; chạm TP1 rồi hoà vốn = +1R; chạm TP2 = +2,5R."""
    hi, lo, cl = (h1[k].to_numpy() for k in ("high", "low", "close"))
    t = h1.index
    trades, pos = [], None
    for i in range(start, len(h1)):
        if pos is not None:
            d = 1 if pos["side"] == "MUA" else -1
            hit_sl = (lo[i] <= pos["sl"]) if d == 1 else (hi[i] >= pos["sl"])
            hit_t1 = (hi[i] >= pos["tp1"]) if d == 1 else (lo[i] <= pos["tp1"])
            hit_t2 = (hi[i] >= pos["tp2"]) if d == 1 else (lo[i] <= pos["tp2"])
            opposite = sell[i] if d == 1 else buy[i]
            res = None
            if hit_sl:
                res = (1.0 if pos["t1"] else -1.0), ("Hoà vốn sau TP1" if pos["t1"] else "Dừng lỗ"), pos["sl"]
            elif hit_t2:
                res = 0.5 * RR_TP1 + 0.5 * RR_TP2, "Đạt TP2", pos["tp2"]
            else:
                if hit_t1 and not pos["t1"]:
                    pos["t1"], pos["sl"] = True, pos["entry"]
                if opposite:
                    r_now = d * (cl[i] - pos["entry"]) / pos["risk"]
                    r = 0.5 * RR_TP1 + 0.5 * r_now if pos["t1"] else r_now
                    res = r, "Tín hiệu ngược chiều", cl[i]
            if res:
                trades.append({**{k: pos[k] for k in ("side", "entry", "tp1", "tp2")}, "sl": pos["sl0"], "t_in": pos["t_in"],
                               "t_out": t[i], "exit": float(res[2]), "r": round(float(res[0]), 2), "reason": res[1]})
                pos = None
                if not opposite:
                    continue
        if pos is None and (buy[i] or sell[i]):
            p = plan("MUA" if buy[i] else "BÁN", i, h1)
            pos = {**p, "sl0": p["sl"], "t_in": t[i], "t1": False}
    return trades, pos


def stats(trades):
    if not trades:
        return {"n": 0}
    r = np.array([x["r"] for x in trades])
    gain, loss = r[r > 0].sum(), -r[r < 0].sum()
    eq = np.cumsum(r)
    dd = float((np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max())
    return {"n": len(r), "win": round(float((r > 0).mean() * 100), 1), "avg_r": round(float(r.mean()), 2),
            "total_r": round(float(r.sum()), 1), "pf": round(float(gain / loss), 2) if loss else None,
            "max_dd_r": round(dd, 1), "from": iso(trades[0]["t_in"])}


# ---------- Xuất dữ liệu ----------

def iso(ts):
    return pd.Timestamp(ts).tz_convert(VN_TZ).strftime("%Y-%m-%dT%H:%M")


def r2(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), 2)


def bars(df, n):
    d = df.tail(n)
    return {"t": [int(x.timestamp()) for x in d.index],
            "o": [r2(x) for x in d["open"]], "h": [r2(x) for x in d["high"]],
            "l": [r2(x) for x in d["low"]], "c": [r2(x) for x in d["close"]],
            "ema20": [r2(x) for x in d["ema20"]], "ema50": [r2(x) for x in d["ema50"]],
            "ema200": [r2(x) for x in d["ema200"]]}


def trade_out(x):
    o = {k: r2(x[k]) for k in ("entry", "sl", "tp1", "tp2")}
    o.update(side=x["side"], t_in=iso(x["t_in"]))
    if "t_out" in x:
        o.update(t_out=iso(x["t_out"]), exit=r2(x["exit"]), r=x["r"], reason=x["reason"])
    return o


def build(df, meta):
    h1 = add_ind(df)
    h4 = add_ind(to_h4(df))
    d1 = add_ind(df.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna())
    h4tr = h4_trend_on_h1(h1, h4)
    buy, sell = setups(h1, h4tr)
    trades, pos = backtest(h1, buy, sell)
    last = h1.iloc[-1]
    prev_day = d1["close"].iloc[-2] if len(d1) > 1 else last["close"]
    open_pos = None
    if pos:
        d = 1 if pos["side"] == "MUA" else -1
        open_pos = {**trade_out({**pos, "sl": pos["sl0"]}), "tp1_hit": pos["t1"], "sl_now": r2(pos["sl"]),
                    "r_now": round(float(d * (last["close"] - pos["entry"]) / pos["risk"]), 2)}
    # Tín hiệu trên nến vừa đóng (bỏ qua nến cuối nếu còn dở dang)
    i_closed = len(h1) - 1 if (pd.Timestamp.now(tz="UTC") - h1.index[-1]) >= pd.Timedelta(hours=1) else len(h1) - 2
    fresh = None
    if buy[i_closed] or sell[i_closed]:
        p = plan("MUA" if buy[i_closed] else "BÁN", i_closed, h1)
        fresh = {**trade_out({**p, "t_in": h1.index[i_closed]}), "id": f"{p['side']}-{int(h1.index[i_closed].timestamp())}"}
    trend = {"H1": "Tăng" if last["ema20"] > last["ema50"] and last["close"] > last["ema20"] else
             ("Giảm" if last["ema20"] < last["ema50"] and last["close"] < last["ema20"] else "Đi ngang"),
             "H4": trend_of(h4.iloc[-1]), "D1": trend_of(d1.iloc[-1])}
    s = stats(trades)
    s30 = stats([x for x in trades if x["t_in"] >= h1.index[-1] - pd.Timedelta(days=90)])
    return {
        "generated_at": datetime.now(VN_TZ).strftime("%Y-%m-%dT%H:%M"),
        "symbol": "XAUUSD", "demo": meta["source"] == "MÔ PHỎNG", **meta,
        "price": r2(last["close"]), "day_chg": r2(last["close"] / prev_day * 100 - 100),
        "rsi_h1": r2(last["rsi"]), "atr_h1": r2(last["atr"]), "atr_h4": r2(h4["atr"].iloc[-1]),
        "trend": trend, "fresh": fresh, "open": open_pos,
        "stats": s, "stats_90d": s30, "rr": [RR_TP1, RR_TP2],
        "trades": [trade_out(x) for x in trades[-30:]][::-1],
        "h1": bars(h1, CHART_H1), "h4": bars(h4, CHART_H4),
    }


# ---------- Telegram (tuỳ chọn) ----------

def telegram(data, prev):
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (tok and chat) or data["demo"]:
        return
    sent = set((prev or {}).get("tg_sent", []))
    msgs = []
    f = data["fresh"]
    if f and f["id"] not in sent:
        icon = "🟢" if f["side"] == "MUA" else "🔴"
        msgs.append((f["id"], f"{icon} XAUUSD {f['side']} {f['entry']}\nDừng lỗ: {f['sl']}\nTP1 (1:2): {f['tp1']}\n"
                     f"TP2 (1:3): {f['tp2']}\nXu hướng H4: {data['trend']['H4']}, RSI H1: {data['rsi_h1']}\n"
                     f"Nến H1 {f['t_in']} (giờ VN). Không phải khuyến nghị đầu tư."))
    for t in data["trades"][:3]:
        key = f"x-{t['side']}-{t['t_in']}"
        if key not in sent and (prev or {}).get("open") and prev["open"]["t_in"] == t["t_in"]:
            msgs.append((key, f"⚪ Đóng lệnh {t['side']} XAUUSD vào {t['entry']}: {t['reason']} tại {t['exit']} ({t['r']:+}R)"))
    for key, text in msgs:
        try:
            body = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
            urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/sendMessage", data=body, timeout=20)
            sent.add(key)
        except Exception as e:
            print(f"Telegram lỗi: {e}", file=sys.stderr)
    data["tg_sent"] = sorted(sent)[-50:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    df, meta = demo() if a.demo else fetch_real()
    data = build(df, meta)
    prev = None
    try:
        prev = json.loads(OUT.read_text())
    except Exception:
        pass
    if prev and not data["demo"]:
        data["tg_sent"] = prev.get("tg_sent", [])
    telegram(data, prev)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    s = data["stats"]
    print(f"XAUUSD {data['price']} | xu hướng {data['trend']} | mới: {data['fresh']} | đang mở: {data['open']}")
    print(f"Backtest từ {s.get('from')}: {s['n']} lệnh, thắng {s.get('win')}%, TB {s.get('avg_r')}R, tổng {s.get('total_r')}R, PF {s.get('pf')}")


if __name__ == "__main__":
    main()
