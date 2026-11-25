"""Tín hiệu mua/bán vàng XAUUSD theo 3 khung: ghi web/data/gold.json.

    python engine/gold.py          # dữ liệu thật (Yahoo GC=F + giá giao ngay gold-api.com)
    python engine/gold.py --demo   # dữ liệu mô phỏng, không cần mạng

Nguồn: nến 1 giờ (2 năm) và 15 phút (60 ngày) của vàng tương lai COMEX (GC=F, Yahoo), dời theo
chênh lệch với giá giao ngay hiện tại để mức giá khớp XAUUSD; dự phòng là PAXG/USDT (Binance).

Quy tắc, chỉ dùng nến đã đóng của khung lớn (không nhìn trước tương lai):
  H4  xu hướng:   Tăng khi giá > EMA50 > EMA200, Giảm khi ngược lại, còn lại đứng ngoài.
  H1  xem xét:    Vùng MUA khi EMA20 > EMA50, giá còn trên EMA50 và đã hồi chạm EMA20 trong 3 nến H1
                  gần nhất (RSI < 70). Vùng BÁN ngược lại.
  M15 điểm vào:   VÀO NGAY ở giá đóng cửa nến quét thanh khoản (không chờ giá chạy), một trong hai kiểu:
    A. Quét đáy 20 nến: trong vùng H1 cùng chiều H4, nến M15 (hiện tại hoặc ngay trước) chọc thủng đáy thấp
       nhất của 20 nến trước, nến hiện tại đóng cửa quay lại trên mức đó và là nến tăng, RSI M15 <= 50: MUA.
    B. Quét 2–3 đáy + phân kỳ RSI: có một đáy xoay chiều (thấp nhất 3 nến mỗi bên, trong 24 giờ, cách ít nhất
       5 nến) chưa bị phá; nến quét chọc xuống dưới nó không quá 0,6 ATR rồi đóng cửa quay lên trên, là nến tăng,
       RSI ở nến quét cao hơn RSI ở đáy cũ (phân kỳ tăng), cùng chiều H4: MUA. Có thêm đáy cũ ngang bằng nữa thì
       gọi là 3 đáy. BÁN ngược lại với đỉnh.
  Bỏ nến mở từ 21h đến trước 3h giờ VN. Dừng lỗ sau râu nến quét thêm 0,1 ATR M15, tối thiểu 10 giá; bỏ lệnh
  nếu dừng lỗ cần rộng hơn 15 giá (10 và 15 giá tính ở mức vàng 3.850, tự co giãn theo giá).
  Tới 1R dời dừng lỗ về giá vào; từ 3R kéo dừng lỗ luôn cách mức lãi cao nhất 1,5R; chốt hết ở 8R.

Kiểm định 2 năm nến M15 PAXG/USDT, tính cả phí chênh lệch 0,35 giá mỗi lệnh: 232 lệnh (10 lệnh/tháng),
thắng 28%, hoà 29%, thua 43%, lệnh thắng trung bình +3,4R, +0,49R mỗi lệnh, hệ số lợi nhuận 2,09,
sụt giảm lớn nhất 11,5R, 8/9 quý có lãi. Riêng kiểu B (2–3 đáy + phân kỳ): 101 lệnh, +0,61R, hệ số 2,49.
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
BE_R = 1.0                     # tới 1R: dời dừng lỗ về giá vào
TRAIL_START, TRAIL_GAP = 3.0, 1.5  # tới 3R: kéo dừng lỗ theo giá, luôn cách đỉnh lãi 1,5R
TP_R = 8.0                     # chốt toàn bộ khi đạt tối đa 8R
SWEEP_LOOK, SWEEP_RECENT, SL_BUF_ATR = 20, 1, 0.1   # đáy/đỉnh 20 nến M15; nến quét: hiện tại hoặc ngay trước
REF_PRICE, MIN_RISK_USD, MAX_RISK_USD = 3850.0, 10.0, 15.0  # dừng lỗ 10–15 giá ở mức 3.850, co giãn theo giá
RSI_MAX = 50                       # lọc chất lượng: MUA khi RSI M15 <= 50 (giá vừa hồi thật), BÁN khi >= 50
SKIP_HOURS_VN = {21, 22, 23, 0, 1, 2}  # bỏ nến M15 mở từ 21h đến trước 3h sáng giờ VN (Mỹ mở cửa, cuối phiên Mỹ)
PIV_K, PIV_WIN, PIV_TOL_ATR, PIV_GAP = 3, 96, 0.6, 5  # đáy/đỉnh xoay chiều: 3 nến mỗi bên, trong 96 nến, quét sâu tối đa 0,6 ATR
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


def add_sweep(m15):
    """Mức thanh khoản (đáy/đỉnh 20 nến trước) và râu nến quét, dùng cho tín hiệu và dừng lỗ."""
    k = SWEEP_RECENT + 1
    m15["liq_lo"] = m15["low"].shift(k).rolling(SWEEP_LOOK).min()
    m15["liq_hi"] = m15["high"].shift(k).rolling(SWEEP_LOOK).max()
    m15["wick_lo"] = m15["low"].rolling(k).min()
    m15["wick_hi"] = m15["high"].rolling(k).max()
    return m15


def patterns(m15):
    """Quét 2–3 đáy/đỉnh: nến hiện tại (hoặc trước) chọc thủng một đáy xoay chiều còn nguyên không quá PIV_TOL_ATR,
    nến hiện tại đóng cửa quay lại và cùng màu chiều lệnh. Trả về chiều (1/-1/0), râu quét, mức đáy/đỉnh bị quét,
    số đáy (2 hoặc 3), có phân kỳ RSI hay không, và đáy/đỉnh còn nguyên gần giá nhất ở nến cuối (để theo dõi)."""
    H, L, C, O = (m15[k].to_numpy() for k in ("high", "low", "close", "open"))
    R, A = m15["rsi"].to_numpy(), m15["atr"].to_numpy()
    K, W, gap = PIV_K, PIV_WIN, PIV_GAP
    n = len(m15)
    side, wick, lvl = np.zeros(n, int), np.full(n, np.nan), np.full(n, np.nan)
    cnt, div = np.zeros(n, int), np.zeros(n, bool)
    lows, highs = [], []  # (vị trí, giá, RSI) của đáy/đỉnh xoay chiều đã xác nhận
    for i in range(2 * K + 1, n):
        j = i - K  # nến i mới xác nhận được xoay chiều tại j (cần K nến mỗi bên)
        if L[j] == L[j - K:j + K + 1].min():
            lows.append((j, L[j], R[j]))
        if H[j] == H[j - K:j + K + 1].max():
            highs.append((j, H[j], R[j]))
        lows = [p for p in lows if i - p[0] <= W]
        highs = [p for p in highs if i - p[0] <= W]
        tol = PIV_TOL_ATR * A[i]
        wl, wh = min(L[i], L[i - 1]), max(H[i], H[i - 1])
        rl, rh = min(R[i], R[i - 1]), max(R[i], R[i - 1])
        if C[i] > O[i]:
            cand = [p for p in lows if i - p[0] >= gap and L[p[0] + 1:i - 1].min(initial=np.inf) > p[1]
                    and wl < p[1] <= wl + tol and C[i] > p[1]]
            if cand:
                p1 = min(cand, key=lambda p: p[1])
                peers = [q for q in lows if q[0] < p1[0] and abs(q[1] - p1[1]) <= tol
                         and L[q[0] + 1:i - 1].min(initial=np.inf) >= p1[1] - tol and q[1] > wl]
                side[i], wick[i], lvl[i], cnt[i], div[i] = 1, wl, p1[1], 3 if peers else 2, rl > p1[2]
                continue
        if C[i] < O[i]:
            cand = [p for p in highs if i - p[0] >= gap and H[p[0] + 1:i - 1].max(initial=-np.inf) < p[1]
                    and wh > p[1] >= wh - tol and C[i] < p[1]]
            if cand:
                p1 = max(cand, key=lambda p: p[1])
                peers = [q for q in highs if q[0] < p1[0] and abs(q[1] - p1[1]) <= tol
                         and H[q[0] + 1:i - 1].max(initial=-np.inf) <= p1[1] + tol and q[1] < wh]
                side[i], wick[i], lvl[i], cnt[i], div[i] = -1, wh, p1[1], 3 if peers else 2, rh < p1[2]
    last = C[-1] if n else np.nan
    lo_ok = [p[1] for p in lows if L[p[0] + 1:].min(initial=np.inf) > p[1] and p[1] < last]
    hi_ok = [p[1] for p in highs if H[p[0] + 1:].max(initial=-np.inf) < p[1] and p[1] > last]
    watch = {"lo": max(lo_ok) if lo_ok else None, "hi": min(hi_ok) if hi_ok else None}
    return side, wick, lvl, cnt, div, watch


def setups(m15, h4tr, zone):
    """Tín hiệu M15: kiểu A (quét đáy/đỉnh 20 nến, ưu tiên) hoặc kiểu B (quét 2–3 đáy/đỉnh + phân kỳ RSI).
    Trả về chiều, râu quét, mức bị quét, tên kiểu, khoảng dừng lỗ; đã bỏ tín hiệu cần dừng lỗ rộng hơn 15 giá."""
    c, o, rs, at = (m15[k].to_numpy() for k in ("close", "open", "rsi", "atr"))
    llo, lhi, wlo, whi = (m15[k].to_numpy() for k in ("liq_lo", "liq_hi", "wick_lo", "wick_hi"))
    hour_ok = ~pd.Series((m15.index + pd.Timedelta(hours=7)).hour).isin(SKIP_HOURS_VN).to_numpy()
    t4, z = np.asarray(h4tr), np.asarray(zone)
    with np.errstate(invalid="ignore"):
        ab = (t4 == "Tăng") & (z == "MUA") & (wlo < llo) & (c > llo) & (c > o) & (rs <= RSI_MAX) & hour_ok
        as_ = (t4 == "Giảm") & (z == "BÁN") & (whi > lhi) & (c < lhi) & (c < o) & (rs >= 100 - RSI_MAX) & hour_ok
    ps, pw, pl, pc, pdv, watch = patterns(m15)
    tsign = np.where(t4 == "Tăng", 1, np.where(t4 == "Giảm", -1, 0))
    pb = (ps != 0) & pdv & (ps == tsign) & hour_ok
    side = np.where(ab, 1, np.where(as_, -1, np.where(pb, ps, 0)))
    wick = np.where(ab, wlo, np.where(as_, whi, pw))
    lvl = np.where(ab, llo, np.where(as_, lhi, pl))
    kind = np.where(ab, "Quét đáy 20 nến", np.where(as_, "Quét đỉnh 20 nến", np.where(
        ps > 0, np.where(pc == 3, "Quét 3 đáy + phân kỳ RSI", "Quét 2 đáy + phân kỳ RSI"),
        np.where(pc == 3, "Quét 3 đỉnh + phân kỳ RSI", "Quét 2 đỉnh + phân kỳ RSI"))))
    scale = c / REF_PRICE
    with np.errstate(invalid="ignore"):
        risk = np.maximum(side * (c - wick) + SL_BUF_ATR * at, MIN_RISK_USD * scale)
        side = np.where((side != 0) & (risk <= MAX_RISK_USD * scale), side, 0)
    return side, wick, lvl, kind, risk, watch


def backtest(m15, side, lvl, kind, risk, start=200):
    """Một lệnh mỗi lúc, vào ngay ở giá đóng cửa nến quét; quản lý từ nến sau (dừng lỗ xét trước mục tiêu).
    Kết quả theo R: dừng lỗ = -1R; về giá vào = 0R; dừng lỗ đã kéo theo lãi = +R tương ứng; đạt tối đa = +8R."""
    hi, lo, cl = (m15[k].to_numpy() for k in ("high", "low", "close"))
    t = m15.index
    trades, pos = [], None
    for i in range(start, len(m15)):
        if pos is not None:
            d = pos["d"]
            fav = d * ((hi[i] if d == 1 else lo[i]) - pos["entry"]) / pos["risk"]
            res = None
            if (lo[i] <= pos["sl"]) if d == 1 else (hi[i] >= pos["sl"]):
                r = d * (pos["sl"] - pos["entry"]) / pos["risk"]
                res = r, ("Dừng lỗ" if r < 0 else "Hoà vốn" if r == 0 else "Chạm SL đã kéo theo lãi"), pos["sl"]
            elif fav >= TP_R:
                res = TP_R, f"Đạt tối đa 1:{TP_R:g}", pos["tp"]
            else:
                pos["mx"] = max(pos["mx"], fav)
                if fav >= BE_R and d * (pos["entry"] - pos["sl"]) > 0:
                    pos["sl"], pos["t1"] = pos["entry"], True
                if pos["mx"] >= TRAIL_START:
                    nsl = pos["entry"] + d * (pos["mx"] - TRAIL_GAP) * pos["risk"]
                    if d * (nsl - pos["sl"]) > 0:
                        pos["sl"] = nsl
            if res:
                trades.append({**{k: pos[k] for k in ("side", "entry", "be", "trail", "tp", "liq", "kind", "t_in")}, "sl": pos["sl0"],
                               "t_out": t[i], "exit": float(res[2]), "r": round(float(res[0]), 2) + 0.0, "reason": res[1]})
                pos = None
            continue
        if side[i]:
            d, e, rk = int(side[i]), float(cl[i]), float(risk[i])
            pos = {"d": d, "side": "MUA" if d == 1 else "BÁN", "entry": e, "risk": rk, "sl": e - d * rk, "sl0": e - d * rk,
                   "be": e + d * BE_R * rk, "trail": e + d * TRAIL_START * rk, "tp": e + d * TP_R * rk,
                   "liq": float(lvl[i]), "kind": str(kind[i]), "t_in": t[i], "mx": 0.0, "t1": False}
    return trades, pos


# ---------- Hệ 2: phá đỉnh/đáy 20 nến H1 theo xu hướng H4 ----------
# Nến H1 đóng cửa trên đỉnh cao nhất 20 nến H1 trước đó khi H4 tăng: MUA ngay giá đóng cửa (BÁN ngược lại).
# Dừng lỗ 2 ATR H1; tới 1R dời SL về giá vào; từ 3R kéo SL cách mức lãi cao nhất 1,5R; chốt hết ở 8R.
# Đứng thứ nhất trong lần so 12 phương pháp (2 năm PAXG: 167 lệnh, +0,69R sau phí, hệ số 2,54; 2 năm GC=F: +78R).
BO_LOOK, BO_ATR = 20, 2.0


def bo_setups(h1, h4tr_h1):
    dhi = h1["high"].rolling(BO_LOOK).max().shift(1)
    dlo = h1["low"].rolling(BO_LOOK).min().shift(1)
    side = np.where((h1["close"] > dhi) & (h4tr_h1 == "Tăng"), 1, np.where((h1["close"] < dlo) & (h4tr_h1 == "Giảm"), -1, 0))
    return side, (BO_ATR * h1["atr"]).to_numpy(), dhi, dlo


def bo_backtest(h1, side, risk, start=500):
    """Một lệnh mỗi lúc, vào ở giá đóng cửa nến tín hiệu, quản lý trên nến H1 (SL xét trước)."""
    hi, lo, cl = (h1[k].to_numpy() for k in ("high", "low", "close"))
    t = h1.index
    trades, pos = [], None
    for i in range(start, len(h1)):
        if pos is not None:
            d = pos["d"]
            fav = d * ((hi[i] if d == 1 else lo[i]) - pos["entry"]) / pos["risk"]
            res = None
            if (lo[i] <= pos["sl"]) if d == 1 else (hi[i] >= pos["sl"]):
                r = d * (pos["sl"] - pos["entry"]) / pos["risk"]
                res = r, ("Dừng lỗ" if r < 0 else "Hoà vốn" if r == 0 else "Chạm SL đã kéo theo lãi"), pos["sl"]
            elif fav >= TP_R:
                res = TP_R, f"Đạt tối đa 1:{TP_R:g}", pos["tp"]
            else:
                pos["mx"] = max(pos["mx"], fav)
                if fav >= BE_R and d * (pos["entry"] - pos["sl"]) > 0:
                    pos["sl"], pos["t1"] = pos["entry"], True
                if pos["mx"] >= TRAIL_START:
                    nsl = pos["entry"] + d * (pos["mx"] - TRAIL_GAP) * pos["risk"]
                    if d * (nsl - pos["sl"]) > 0:
                        pos["sl"] = nsl
            if res:
                trades.append({**{k: pos[k] for k in ("side", "entry", "be", "trail", "tp", "t_in")}, "sl": pos["sl0"],
                               "t_out": t[i], "exit": float(res[2]), "r": round(float(res[0]), 2) + 0.0, "reason": res[1]})
                pos = None
            continue
        if side[i] and np.isfinite(risk[i]) and risk[i] > 0:
            d, e, rk = int(side[i]), float(cl[i]), float(risk[i])
            pos = {"d": d, "side": "MUA" if d == 1 else "BÁN", "entry": e, "risk": rk, "sl": e - d * rk, "sl0": e - d * rk,
                   "be": e + d * BE_R * rk, "trail": e + d * TRAIL_START * rk, "tp": e + d * TP_R * rk,
                   "t_in": t[i], "mx": 0.0, "t1": False}
    return trades, pos


def bo_build(h1, h4tr_all, now):
    H1, H4 = pd.Timedelta(hours=1), pd.Timedelta(hours=4)
    h4tr_h1 = closed_on(h4tr_all, H4, h1.index).fillna("Đi ngang")
    side, risk, dhi, dlo = bo_setups(h1, h4tr_h1)
    trades, pos = bo_backtest(h1, side, risk)
    i_h = last_closed(h1, H1, now)
    last = h1.iloc[i_h]
    open_pos = None
    if pos:
        open_pos = {**trade_out({**pos, "sl": pos["sl0"]}), "be_hit": bool(pos["t1"]), "trailing": bool(pos["mx"] >= TRAIL_START),
                    "sl_now": r2(pos["sl"]), "id": f"BO-{pos['side']}-{int(pos['t_in'].timestamp())}"}
    fresh = open_pos if pos and pos["t_in"] >= h1.index[max(i_h - 1, 0)] else None
    t4 = h4tr_h1.iloc[i_h]
    hi20, lo20 = dhi.iloc[i_h], dlo.iloc[i_h]
    if open_pos:
        status = f"Đang giữ lệnh {open_pos['side']} từ {open_pos['entry']}."
    elif t4 == "Tăng":
        status = f"H4 tăng: chờ nến H1 đóng cửa trên đỉnh 20 nến {r2(h1['high'].iloc[i_h - BO_LOOK + 1:i_h + 1].max())} để MUA."
    elif t4 == "Giảm":
        status = f"H4 giảm: chờ nến H1 đóng cửa dưới đáy 20 nến {r2(h1['low'].iloc[i_h - BO_LOOK + 1:i_h + 1].min())} để BÁN."
    else:
        status = "H4 đi ngang: đứng ngoài."
    return {"name": "Phá đỉnh/đáy 20 nến H1 theo H4", "status": status, "trend": t4, "open": open_pos, "fresh": fresh,
            "stats": stats(trades), "trades": [trade_out(x) for x in trades[-30:]][::-1],
            "atr_h1": r2(last["atr"]), "risk_now": r2(BO_ATR * last["atr"])}


def stats(trades):
    if not trades:
        return {"n": 0}
    r = np.array([x["r"] for x in trades])
    gain, loss = r[r > 0].sum(), -r[r < 0].sum()
    eq = np.cumsum(r)
    dd = float((np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max())
    return {"n": len(r), "win": round(float((r > 0).mean() * 100), 1),
            "be_pct": round(float((r == 0).mean() * 100), 1), "loss_pct": round(float((r < 0).mean() * 100), 1), "avg_r": round(float(r.mean()), 2),
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
    o = {k: r2(x[k]) for k in ("entry", "sl", "be", "tp") if k in x}
    if x.get("trail") is not None:
        o["trail"] = r2(x["trail"])
    o.update(side=x["side"], t_in=iso(x["t_in"]))
    if x.get("t_sig") is not None:
        o["t_sig"] = iso(x["t_sig"])
    if x.get("liq") is not None:
        o["liq"] = r2(x["liq"])
    if x.get("kind"):
        o["kind"] = x["kind"]
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
    m15 = add_sweep(m15)
    h4 = add_ind(h1_raw.resample("4h", origin="epoch").agg(OHLC).dropna())
    d1 = h1_raw.resample("1D").agg(OHLC).dropna()
    h4tr_all, zone_all = h4.apply(trend_of, axis=1), h1_zones(h1)
    h4tr = closed_on(h4tr_all, H4, m15.index).fillna("Đi ngang")
    zone = closed_on(zone_all, H1, m15.index).fillna("")
    side, wick, lvl, kind, risk, watch = setups(m15, h4tr, zone)
    i_m = last_closed(m15, M15, now)
    side[i_m + 1:] = 0  # nến M15 chưa đóng thì chưa có tín hiệu
    trades, pos = backtest(m15, side, lvl, kind, risk)

    last = m15.iloc[-1]
    prev_day = d1["close"].iloc[-2] if len(d1) > 1 else last["close"]
    open_pos = None
    if pos:
        d = pos["d"]
        open_pos = {**trade_out({**pos, "sl": pos["sl0"]}), "be_hit": bool(pos["t1"]), "trailing": bool(pos["mx"] >= TRAIL_START),
                    "sl_now": r2(pos["sl"]), "id": f"{pos['side']}-{int(pos['t_in'].timestamp())}",
                    "r_now": round(float(d * (last["close"] - pos["entry"]) / pos["risk"]), 2)}
    # Lệnh mới vào trong 4 nến M15 đã đóng gần nhất
    fresh = open_pos if pos and pos["t_in"] >= m15.index[max(i_m - 3, 0)] else None

    i_h4, i_h1 = last_closed(h4, H4, now), last_closed(h1, H1, now)
    t4, z1 = trend_of(h4.iloc[i_h4]), zone_all.iloc[i_h1]
    lm = m15.iloc[i_m]
    m15_state = "Tăng" if lm["close"] > lm["ema20"] > lm["ema50"] else "Giảm" if lm["close"] < lm["ema20"] < lm["ema50"] else "Đi ngang"
    piv = {"lo": r2(watch["lo"]), "hi": r2(watch["hi"])}
    off = "Ngoài giờ vào lệnh (21h–3h giờ VN). " if (now + pd.Timedelta(hours=7)).hour in SKIP_HOURS_VN else ""
    if open_pos:
        status = f"Đang giữ lệnh {open_pos['side']} từ {open_pos['entry']} ({open_pos['kind']})."
    elif t4 == "Đi ngang":
        status = "H4 đi ngang: đứng ngoài, chờ xu hướng rõ."
    else:
        up = t4 == "Tăng"
        w, pv = ("đáy", piv["lo"]) if up else ("đỉnh", piv["hi"])
        parts = []
        if z1 == ("MUA" if up else "BÁN"):
            parts.append(f"quét {w} 20 nến {lm['liq_lo' if up else 'liq_hi']:.2f}")
        if pv is not None and not (parts and abs(pv - lm['liq_lo' if up else 'liq_hi']) < 0.01):
            parts.append(f"quét {w} cũ {pv:.2f} có phân kỳ RSI")
        status = off + (f"H4 {t4.lower()}: chờ M15 " + " hoặc ".join(parts) + f" rồi đóng cửa quay lại để {'MUA' if up else 'BÁN'} ngay."
                        if parts else f"H4 {t4.lower()}: chưa có {w} nào để chờ quét.")
    s = stats(trades)
    bo = bo_build(h1, h4tr_all, now)
    return {
        "generated_at": datetime.now(VN_TZ).strftime("%Y-%m-%dT%H:%M"),
        "symbol": "XAUUSD", "demo": meta["source"] == "MÔ PHỎNG", **meta,
        "price": r2(last["close"]), "day_chg": r2(last["close"] / prev_day * 100 - 100),
        "rsi_m15": r2(lm["rsi"]), "rsi_h1": r2(h1["rsi"].iloc[i_h1]), "atr_m15": r2(lm["atr"]),
        "liq": {"lo": r2(lm["liq_lo"]), "hi": r2(lm["liq_hi"])}, "tf": {"H4": t4, "H1": z1 or "Chưa có vùng", "M15": m15_state}, "status": status,
        "piv": piv, "fresh": fresh, "open": open_pos, "stats": s,
        "rr": {"be": BE_R, "trail": TRAIL_START, "gap": TRAIL_GAP, "tp": TP_R, "min_risk": MIN_RISK_USD, "max_risk": MAX_RISK_USD},
        "trades": [trade_out(x) for x in trades[-30:]][::-1],
        "bo": bo,
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
        msgs.append((f["id"], f"{icon} XAUUSD {f['side']} {f['entry']} (vào ngay) · {f.get('kind')} tại {f.get('liq')}\n"
                     f"Dừng lỗ: {f['sl']}\nTới {f['be']} (1:1): dời SL về giá vào\nTới {f.get('trail')} (1:{TRAIL_START:g}): kéo SL cách {TRAIL_GAP:g}R\n"
                     f"Chốt tối đa (1:{TP_R:g}): {f['tp']}\nH4 {data['tf']['H4']}. Không phải khuyến nghị đầu tư."))
    b = data.get("bo") or {}
    bf = b.get("fresh")
    if bf and bf["id"] not in sent:
        icon = "🟢" if bf["side"] == "MUA" else "🔴"
        msgs.append((bf["id"], f"{icon} [Hệ 2 · Phá đỉnh/đáy H1] XAUUSD {bf['side']} {bf['entry']} (vào ngay)\nDừng lỗ: {bf['sl']}\n"
                     f"Tới {bf['be']} (1:1): dời SL về giá vào\nTới {bf['trail']} (1:{TRAIL_START:g}): kéo SL cách {TRAIL_GAP:g}R\n"
                     f"Chốt tối đa (1:{TP_R:g}): {bf['tp']}\nKhông phải khuyến nghị đầu tư."))
    for t in b.get("trades", [])[:3]:
        key = f"x-bo-{t['side']}-{t['t_in']}"
        pb = ((prev or {}).get("bo") or {}).get("open")
        if key not in sent and pb and pb["t_in"] == t["t_in"]:
            msgs.append((key, f"⚪ [Hệ 2] Đóng lệnh {t['side']} XAUUSD vào {t['entry']}: {t['reason']} tại {t['exit']} ({t['r']:+}R)"))
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
    b = data["bo"]
    print(f"Hệ 2: {b['status']} | mở: {b['open']} | thống kê: {b['stats']}")
    print(f"Backtest M15 từ {s.get('from')}: {s['n']} lệnh, thắng {s.get('win')}%, TB {s.get('avg_r')}R, "
          f"tổng {s.get('total_r')}R, PF {s.get('pf')}, sụt giảm {s.get('max_dd_r')}R")


if __name__ == "__main__":
    main()
