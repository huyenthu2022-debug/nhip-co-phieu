"""Tín hiệu mua/bán vàng XAUUSD theo 3 khung: ghi web/data/gold.json.

    python engine/gold.py          # dữ liệu thật (Yahoo GC=F + giá giao ngay gold-api.com)
    python engine/gold.py --demo   # dữ liệu mô phỏng, không cần mạng

Nguồn: nến 1 giờ (2 năm) và 15 phút (60 ngày) của vàng tương lai COMEX (GC=F, Yahoo), dời theo
chênh lệch với giá giao ngay hiện tại để mức giá khớp XAUUSD; dự phòng là PAXG/USDT (Binance).

Quy tắc, chỉ dùng nến đã đóng của khung lớn (không nhìn trước tương lai):
  H4  xu hướng:   Tăng khi giá > EMA50 > EMA200, Giảm khi ngược lại, còn lại đứng ngoài.
  H1  xem xét:    Vùng MUA khi EMA20 > EMA50, giá còn trên EMA50 và đã hồi chạm EMA20 trong 3 nến H1
                  gần nhất (RSI < 70). Vùng BÁN ngược lại.
  M15 điểm vào:   trong vùng H1 cùng chiều H4, nến M15 đóng cửa vượt lại EMA20 kèm RSI14 cắt 50
                  hoặc MACD hist đổi dấu theo chiều lệnh.
  Dừng lỗ sau đáy/đỉnh 12 nến M15 thêm 0,3 ATR (rủi ro giới hạn 1–4 ATR M15).
  TP1 = 2R (R:R 1:2): chốt một nửa và dời dừng lỗ về giá vào. TP2 = 3R (R:R 1:3).
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
SWING_BARS, SL_BUF_ATR, MIN_RISK_ATR, MAX_RISK_ATR = 12, 0.3, 1.0, 4.0
CHART = {"m15": 400, "h1": 360, "h4": 300}
OHLC = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}


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


def yahoo(interval, rng):
    j = _get(f"https://query2.finance.yahoo.com/v8/finance/chart/GC=F?interval={interval}&range={rng}")
    r = j["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    df = pd.DataFrame({k: q[k] for k in ("open", "high", "low", "close", "volume")},
                      index=pd.to_datetime(r["timestamp"], unit="s", utc=True))
    return df.dropna(subset=["open", "high", "low", "close"]).astype(float)


def binance(interval, n):
    rows, end = [], None
    while len(rows) < n:
        url = f"https://data-api.binance.vision/api/v3/klines?symbol=PAXGUSDT&interval={interval}&limit=1000"
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


def clean(df):
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df[df.index.second == 0]  # Yahoo đôi khi thêm một nến "hiện tại" lệch mốc


def shift_to_spot(df, spot):
    basis = spot - df["close"].iloc[-1]
    if abs(basis) < 0.05 * spot:  # chỉ dời khi chênh lệch hợp lý (phí lưu kho hợp đồng tương lai)
        df = df.copy()
        for k in ("open", "high", "low", "close"):
            df[k] = df[k] + basis
    return df, basis


def fetch_real():
    spot, spot_src = spot_price()
    try:
        h1, m15, src = yahoo("1h", "730d"), yahoo("15m", "60d"), "COMEX GC=F (Yahoo), dời theo giá giao ngay"
    except Exception as e:
        print(f"Yahoo lỗi: {e}, dùng PAXG", file=sys.stderr)
        h1, m15, src = binance("1h", 9000), binance("15m", 6000), "PAXG/USDT (Binance)"
    h1, _ = shift_to_spot(clean(h1), spot)
    m15, basis = shift_to_spot(clean(m15), spot)
    return h1, m15, {"source": src, "spot_source": spot_src, "spot": spot, "basis": round(float(basis), 2)}


def demo():
    rng = np.random.default_rng(7)
    idx = pd.date_range(end=pd.Timestamp.now(tz="UTC").floor("15min"), periods=48000, freq="15min")
    idx = idx[idx.dayofweek < 5]
    n = len(idx)
    drift = np.repeat(rng.choice([-0.0001, 0.00002, 0.00012], size=n // 800 + 1), 800)[:n]
    c = 3000 * np.exp(np.cumsum(drift + rng.normal(0, 0.0012, n)))
    o = np.r_[c[0], c[:-1]]
    sp = np.abs(rng.normal(0, 0.0009, n)) * c
    m15 = pd.DataFrame({"open": o, "high": np.maximum(o, c) + sp, "low": np.minimum(o, c) - sp, "close": c,
                        "volume": rng.integers(100, 900, n).astype(float)}, index=idx)
    h1 = m15.resample("1h").agg(OHLC).dropna()
    return h1, m15.tail(5600), {"source": "MÔ PHỎNG", "spot_source": "MÔ PHỎNG", "spot": float(c[-1]), "basis": 0}


# ---------- Chỉ báo và tín hiệu ----------

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


def h1_zones(h1):
    """Vùng xem xét trên H1: 'MUA', 'BÁN' hoặc ''."""
    c, e20, e50 = h1["close"], h1["ema20"], h1["ema50"]
    touch_dn = (h1["low"] <= e20).rolling(3).max().astype(bool)
    touch_up = (h1["high"] >= e20).rolling(3).max().astype(bool)
    buy = (e20 > e50) & (c > e50) & touch_dn & (h1["rsi"] < 70)
    sell = (e20 < e50) & (c < e50) & touch_up & (h1["rsi"] > 30)
    return pd.Series(np.where(buy, "MUA", np.where(sell, "BÁN", "")), index=h1.index)


def closed_on(series, period, target_index):
    """Gắn giá trị của nến khung lớn ĐÃ ĐÓNG gần nhất vào từng nến khung nhỏ."""
    s = series.copy()
    s.index = s.index + period  # chỉ biết giá trị khi nến khung lớn đóng
    return s.reindex(target_index, method="ffill")


def setups(m15, h4tr, zone):
    c, e20 = m15["close"], m15["ema20"]
    mom_up = ((m15["rsi"] > 50) & (m15["rsi"].shift() <= 50)) | ((m15["macdh"] > 0) & (m15["macdh"].shift() <= 0))
    mom_dn = ((m15["rsi"] < 50) & (m15["rsi"].shift() >= 50)) | ((m15["macdh"] < 0) & (m15["macdh"].shift() >= 0))
    buy = (h4tr == "Tăng") & (zone == "MUA") & (c > e20) & mom_up & (m15["rsi"] < 70)
    sell = (h4tr == "Giảm") & (zone == "BÁN") & (c < e20) & mom_dn & (m15["rsi"] > 30)
    return buy.fillna(False).to_numpy(), sell.fillna(False).to_numpy()


def plan(side, i, m15):
    """Điểm vào, dừng lỗ, TP1 (1:2), TP2 (1:3) cho tín hiệu ở nến M15 thứ i."""
    entry, a = float(m15["close"].iloc[i]), float(m15["atr"].iloc[i])
    win = m15.iloc[max(0, i - SWING_BARS + 1):i + 1]
    risk = (entry - win["low"].min() + SL_BUF_ATR * a) if side == "MUA" else (win["high"].max() - entry + SL_BUF_ATR * a)
    risk = float(min(max(risk, MIN_RISK_ATR * a), MAX_RISK_ATR * a))
    d = 1 if side == "MUA" else -1
    return {"side": side, "entry": entry, "sl": entry - d * risk, "tp1": entry + d * RR_TP1 * risk,
            "tp2": entry + d * RR_TP2 * risk, "risk": risk}


def backtest(m15, buy, sell, start=200):
    """Một lệnh mỗi lúc. Cùng nến chạm cả dừng lỗ và mục tiêu thì tính dừng lỗ trước (thận trọng).
    Kết quả theo R: thua cả lệnh = -1R; chạm TP1 rồi hoà vốn = +1R; chạm TP2 = +2,5R."""
    hi, lo, cl = (m15[k].to_numpy() for k in ("high", "low", "close"))
    t = m15.index
    trades, pos = [], None
    for i in range(start, len(m15)):
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
                trades.append({**{k: pos[k] for k in ("side", "entry", "tp1", "tp2")}, "sl": pos["sl0"],
                               "t_in": pos["t_in"], "t_out": t[i], "exit": float(res[2]),
                               "r": round(float(res[0]), 2), "reason": res[1]})
                pos = None
                if not opposite:
                    continue
        if pos is None and (buy[i] or sell[i]):
            p = plan("MUA" if buy[i] else "BÁN", i, m15)
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


def last_closed(df, period, now):
    """Vị trí nến đã đóng gần nhất (nến cuối có thể còn dở dang)."""
    return len(df) - 1 if now - df.index[-1] >= period else len(df) - 2


def build(h1_raw, m15_raw, meta):
    now = pd.Timestamp.now(tz="UTC")
    H1, H4, M15 = pd.Timedelta(hours=1), pd.Timedelta(hours=4), pd.Timedelta(minutes=15)
    m15 = add_ind(m15_raw)
    h1 = add_ind(h1_raw)
    h4 = add_ind(h1_raw.resample("4h", origin="epoch").agg(OHLC).dropna())
    d1 = h1_raw.resample("1D").agg(OHLC).dropna()
    h4tr_all, zone_all = h4.apply(trend_of, axis=1), h1_zones(h1)
    h4tr = closed_on(h4tr_all, H4, m15.index).fillna("Đi ngang")
    zone = closed_on(zone_all, H1, m15.index).fillna("")
    buy, sell = setups(m15, h4tr, zone)
    trades, pos = backtest(m15, buy, sell)

    last = m15.iloc[-1]
    prev_day = d1["close"].iloc[-2] if len(d1) > 1 else last["close"]
    open_pos = None
    if pos:
        d = 1 if pos["side"] == "MUA" else -1
        open_pos = {**trade_out({**pos, "sl": pos["sl0"]}), "tp1_hit": pos["t1"], "sl_now": r2(pos["sl"]),
                    "r_now": round(float(d * (last["close"] - pos["entry"]) / pos["risk"]), 2)}
    # Tín hiệu mới: trên 4 nến M15 đã đóng gần nhất (bù khi lịch chạy của GitHub bị trễ)
    i_m = last_closed(m15, M15, now)
    taken = {x["t_in"] for x in trades} | ({pos["t_in"]} if pos else set())  # chỉ tín hiệu thực sự mở lệnh
    fresh = None
    for i in range(i_m, max(i_m - 4, 0), -1):
        if (buy[i] or sell[i]) and m15.index[i] in taken:
            p = plan("MUA" if buy[i] else "BÁN", i, m15)
            fresh = {**trade_out({**p, "t_in": m15.index[i]}), "id": f"{p['side']}-{int(m15.index[i].timestamp())}"}
            break

    i_h4, i_h1 = last_closed(h4, H4, now), last_closed(h1, H1, now)
    t4, z1 = trend_of(h4.iloc[i_h4]), zone_all.iloc[i_h1]
    lm = m15.iloc[i_m]
    m15_state = "Tăng" if lm["close"] > lm["ema20"] > lm["ema50"] else "Giảm" if lm["close"] < lm["ema20"] < lm["ema50"] else "Đi ngang"
    if t4 == "Đi ngang":
        status = "H4 đi ngang: đứng ngoài, chờ xu hướng rõ."
    elif z1 != ("MUA" if t4 == "Tăng" else "BÁN"):
        status = f"H4 {t4.lower()}: chờ giá H1 hồi về EMA20 để vào vùng {'MUA' if t4 == 'Tăng' else 'BÁN'}."
    else:
        status = f"H4 {t4.lower()}, H1 đang ở vùng {z1}: chờ nến M15 xác nhận để vào lệnh."
    s = stats(trades)
    return {
        "generated_at": datetime.now(VN_TZ).strftime("%Y-%m-%dT%H:%M"),
        "symbol": "XAUUSD", "demo": meta["source"] == "MÔ PHỎNG", **meta,
        "price": r2(last["close"]), "day_chg": r2(last["close"] / prev_day * 100 - 100),
        "rsi_m15": r2(lm["rsi"]), "rsi_h1": r2(h1["rsi"].iloc[i_h1]), "atr_m15": r2(lm["atr"]),
        "tf": {"H4": t4, "H1": z1 or "Chưa có vùng", "M15": m15_state}, "status": status,
        "fresh": fresh, "open": open_pos, "stats": s, "rr": [RR_TP1, RR_TP2],
        "trades": [trade_out(x) for x in trades[-30:]][::-1],
        "m15": bars(m15, CHART["m15"]), "h1": bars(h1, CHART["h1"]), "h4": bars(h4, CHART["h4"]),
    }


# ---------- Telegram (tuỳ chọn) ----------

def telegram(data, prev):
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (tok and chat) or data["demo"]:
        return
    sent = set(data.get("tg_sent", []))
    msgs = []
    f = data["fresh"]
    if f and f["id"] not in sent:
        icon = "🟢" if f["side"] == "MUA" else "🔴"
        msgs.append((f["id"], f"{icon} XAUUSD {f['side']} {f['entry']}\nDừng lỗ: {f['sl']}\nTP1 (1:2): {f['tp1']}\n"
                     f"TP2 (1:3): {f['tp2']}\nH4 {data['tf']['H4']} · H1 vùng {data['tf']['H1']} · M15 xác nhận\n"
                     f"Nến M15 {f['t_in'].replace('T', ' ')} (giờ VN). Không phải khuyến nghị đầu tư."))
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
    h1, m15, meta = demo() if a.demo else fetch_real()
    data = build(h1, m15, meta)
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
    print(f"XAUUSD {data['price']} | {data['tf']} | {data['status']}")
    print(f"Mới: {data['fresh']} | đang mở: {data['open']}")
    print(f"Backtest M15 từ {s.get('from')}: {s['n']} lệnh, thắng {s.get('win')}%, TB {s.get('avg_r')}R, "
          f"tổng {s.get('total_r')}R, PF {s.get('pf')}, sụt giảm {s.get('max_dd_r')}R")


if __name__ == "__main__":
    main()
