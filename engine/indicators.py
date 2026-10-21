"""Chỉ báo kỹ thuật, điểm sức mạnh và quy tắc tín hiệu.

Mọi hàm nhận DataFrame giá ngày có cột open, high, low, close, volume
(đơn vị giá: nghìn đồng), index là ngày.
"""
import numpy as np
import pandas as pd

# Cổ phiếu VN thanh toán T+2: mua phiên T thì sớm nhất bán được phiên T+2.
MIN_HOLD_SESSIONS = 2


def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def rsi(close, n=14):
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def macd_hist(close):
    line = ema(close, 12) - ema(close, 26)
    return line - ema(line, 9)


def atr(df, n=14):
    prev = df["close"].shift()
    tr = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def cmf(df, n=20):
    rng = (df["high"] - df["low"]).replace(0, np.nan)
    mfm = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / rng
    mfv = (mfm.fillna(0) * df["volume"])
    return mfv.rolling(n).sum() / df["volume"].rolling(n).sum()


def mfi(df, n=14):
    tp = (df["high"] + df["low"] + df["close"]) / 3
    flow = tp * df["volume"]
    pos = flow.where(tp > tp.shift(), 0).rolling(n).sum()
    neg = flow.where(tp < tp.shift(), 0).rolling(n).sum()
    return (100 - 100 / (1 + pos / neg.replace(0, np.nan))).fillna(50)


def enrich(df):
    """Thêm toàn bộ cột chỉ báo cần cho tín hiệu và giao diện."""
    df = df.copy()
    c = df["close"]
    df["ema20"] = ema(c, 20)
    df["ema50"] = ema(c, 50)
    df["ma200"] = c.rolling(200, min_periods=120).mean()
    df["rsi"] = rsi(c)
    df["macdh"] = macd_hist(c)
    df["atr"] = atr(df)
    df["cmf"] = cmf(df)
    df["mfi"] = mfi(df)
    df["vol20"] = df["volume"].rolling(20).mean()
    df["hh20"] = df["high"].rolling(20).max().shift()
    return df


def trend_short(row, ema20_5ago):
    slope = row["ema20"] - ema20_5ago
    if row["close"] > row["ema20"] and slope > 0:
        return "Tăng"
    if row["close"] < row["ema20"] and slope < 0:
        return "Giảm"
    return "Đi ngang"


def trend_mid(row, ema50_10ago):
    up = row["ema50"] > ema50_10ago
    ma200 = row["ma200"] if not np.isnan(row["ma200"]) else row["ema50"]
    if row["close"] > row["ema50"] and row["ema50"] >= ma200 and up:
        return "Tăng"
    if row["close"] < row["ema50"] and row["ema50"] <= ma200 and not up:
        return "Giảm"
    return "Đi ngang"


def tf_momentum(close):
    """Trạng thái động lượng 0-3 trên một khung: giá > EMA10, MACD hist > 0, RSI > 50."""
    if len(close) < 30:
        return None
    pts = int(close.iloc[-1] > ema(close, 10).iloc[-1]) + int(macd_hist(close).iloc[-1] > 0) + int(rsi(close).iloc[-1] > 50)
    return pts


def multi_tf(df):
    c = df["close"]
    return {
        "D": tf_momentum(c),
        "W": tf_momentum(c.resample("W-FRI").last().dropna()),
        "M": tf_momentum(c.resample("ME").last().dropna()),
    }


def rs_raw(close):
    """Hiệu suất có trọng số kiểu IBD: 40% quý gần nhất, 20% mỗi quý trước."""
    def ret(n):
        return close.iloc[-1] / close.iloc[-n - 1] - 1 if len(close) > n else np.nan
    parts = [ret(63), ret(126), ret(189), ret(252)]
    w = [0.4, 0.2, 0.2, 0.2]
    vals = [(p, wi) for p, wi in zip(parts, w) if not np.isnan(p)]
    if not vals:
        return np.nan
    return sum(p * wi for p, wi in vals) / sum(wi for _, wi in vals)


def money_flow_label(cmf_v, vol_ratio):
    if cmf_v > 0.1 and vol_ratio > 1.3:
        return "Vào mạnh"
    if cmf_v > 0.05:
        return "Vào"
    if cmf_v < -0.1 and vol_ratio > 1.3:
        return "Ra mạnh"
    if cmf_v < -0.05:
        return "Ra"
    return "Trung tính"


def core_score(ts, tm, rs, cmf_v, vol_ratio, mtf):
    """Điểm sức mạnh 0-10: xu hướng 3.5, RS 3, dòng tiền 1.5, động lượng đa khung 2."""
    s = {"Tăng": 1.5, "Đi ngang": 0.6, "Giảm": 0}[ts]
    s += {"Tăng": 2.0, "Đi ngang": 0.8, "Giảm": 0}[tm]
    s += 3.0 * (rs or 0) / 99
    s += 1.0 if cmf_v > 0.05 else (0.5 if cmf_v > 0 else 0)
    s += 0.5 if vol_ratio > 1 else 0
    pts = [v for v in mtf.values() if v is not None]
    s += 2.0 * (sum(pts) / (3 * len(pts))) if pts else 0
    return round(min(s, 10), 1)


def buy_setup(df, i):
    """Điều kiện mua: phá đỉnh 20 phiên, kèm khối lượng, trong xu hướng tăng."""
    r = df.iloc[i]
    return bool(
        r["close"] > r["hh20"]
        and r["volume"] > 1.3 * r["vol20"]
        and r["close"] > r["ema50"]
        and r["ema20"] > r["ema50"]
        and r["rsi"] < 80
    )


def sell_setup(df, i):
    """Điều kiện bán chủ động: đóng cửa dưới EMA20 và MACD hist chuyển âm."""
    r, p = df.iloc[i], df.iloc[i - 1]
    return bool(r["close"] < r["ema20"] and r["macdh"] < 0 and p["macdh"] >= 0)


def backtest(df, start=60):
    """Chạy quy tắc trên lịch sử. Trả về danh sách lệnh và vị thế đang mở (nếu có).

    Quản lý lệnh: dừng lỗ = giá vào - 2*ATR; T1 = +1.5R thì dời dừng lỗ về giá vào;
    T2 = +3R chốt toàn bộ; hoặc thoát khi có tín hiệu bán. Tôn trọng T+2.
    """
    trades, pos = [], None
    for i in range(start, len(df)):
        r = df.iloc[i]
        day = df.index[i]
        if pos is None:
            if buy_setup(df, i):
                entry = float(r["close"])
                risk = 2 * float(r["atr"])
                pos = {
                    "entry_date": day, "entry_i": i, "entry": entry,
                    "stop": entry - risk, "t1": entry + 1.5 * risk, "t2": entry + 3 * risk,
                    "t1_hit": False,
                }
            continue
        if i - pos["entry_i"] < MIN_HOLD_SESSIONS:
            continue
        exit_px, reason = None, None
        if r["low"] <= pos["stop"]:
            exit_px, reason = pos["stop"], "Dừng lỗ" if not pos["t1_hit"] else "Hoà vốn sau T1"
        elif r["high"] >= pos["t2"]:
            exit_px, reason = pos["t2"], "Đạt T2"
        elif sell_setup(df, i):
            exit_px, reason = float(r["close"]), "Tín hiệu bán"
        if not pos["t1_hit"] and r["high"] >= pos["t1"]:
            pos["t1_hit"] = True
            pos["stop"] = max(pos["stop"], pos["entry"])
        if exit_px is not None:
            trades.append({
                "entry_date": pos["entry_date"], "exit_date": day,
                "entry": pos["entry"], "exit": float(exit_px),
                "ret": float(exit_px) / pos["entry"] - 1, "reason": reason,
                "days": i - pos["entry_i"],
            })
            pos = None
    return trades, pos
