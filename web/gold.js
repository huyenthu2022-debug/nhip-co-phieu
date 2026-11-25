// Tab Vàng XAUUSD: biểu đồ TradingView OANDA:XAUUSD, tín hiệu từ data/gold.json, giá giao ngay trực tiếp và cảnh báo.
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
  };
  const fmt = (v, nd = 2) => v == null ? "–" : Number(v).toLocaleString("vi-VN", { minimumFractionDigits: nd, maximumFractionDigits: nd });
  const pill = t => `<span class="pill ${t === "Tăng" ? "t-up" : t === "Giảm" ? "t-down" : "t-flat"}">${t}</span>`;
  const sidePill = s => `<span class="pill ${s === "MUA" ? "sig-buy" : "sig-sell"}">${s}</span>`;
  const cssVar = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const LIVE_MS = 15000, DATA_MS = 120000;
  let G = null, live = null, prevLive = null, chart = null, tf = "m15", tvLoaded = false;

  /* ---------- TradingView (chỉ tải khi mở tab để trang chứng khoán không chậm) ---------- */
  function loadTV() {
    if (tvLoaded) return;
    tvLoaded = true;
    const dark = matchMedia("(prefers-color-scheme: dark)").matches && document.documentElement.dataset.theme !== "light"
      || document.documentElement.dataset.theme === "dark";
    const box = $("#tvBox");
    box.innerHTML = '<div class="tradingview-widget-container"><div class="tradingview-widget-container__widget"></div></div>';
    const sc = document.createElement("script");
    sc.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    sc.async = true;
    sc.textContent = JSON.stringify({
      autosize: true, symbol: "OANDA:XAUUSD", interval: "15", timezone: "Asia/Ho_Chi_Minh",
      theme: dark ? "dark" : "light", style: "1", locale: "vi_VN", allow_symbol_change: true,
      withdateranges: true, hide_side_toolbar: false, details: false, calendar: false,
      studies: ["STD;EMA", "STD;RSI"], support_host: "https://www.tradingview.com",
    });
    box.firstChild.appendChild(sc);
  }

  /* ---------- Giá trực tiếp ---------- */
  async function spot() {
    try {
      const j = await fetch("https://api.gold-api.com/price/XAU", { cache: "no-store" }).then(r => r.json());
      if (j && j.price) return { price: +j.price, src: "gold-api.com" };
    } catch {}
    const j = await fetch("https://data-api.binance.vision/api/v3/ticker/price?symbol=PAXGUSDT", { cache: "no-store" }).then(r => r.json());
    return { price: +j.price, src: "PAXG" };
  }
  function setLive(state, text) { const el = $("#gLive"); el.dataset.state = state; el.textContent = text; }
  const marketOpen = () => { // Vàng giao dịch từ 5:00 sáng thứ 2 đến gần 4:00 sáng thứ 7 giờ VN (nghỉ ~1 giờ mỗi sáng)
    const d = new Date(Date.now() + 7 * 3600e3), wd = d.getUTCDay(), h = d.getUTCHours();
    if (wd === 0 || (wd === 6 && h >= 4) || (wd === 1 && h < 5)) return false;
    return true;
  };
  let liveTimer;
  async function liveTick() {
    try {
      const q = await spot();
      prevLive = live; live = q.price;
      setLive(marketOpen() ? "open" : "off", `${marketOpen() ? "Trực tiếp" : "Thị trường nghỉ"} · ${new Date().toLocaleTimeString("vi-VN", { hour12: false })}`);
      paintHead(); paintSignal(); paintBo(); checkAlerts();
    } catch { setLive("error", "Không lấy được giá trực tiếp"); }
    clearTimeout(liveTimer);
    liveTimer = setTimeout(liveTick, marketOpen() ? LIVE_MS : 300000);
  }

  /* ---------- Cảnh báo ---------- */
  let seen = store.get("goldSeen", {});
  function alertUser(text, body) {
    const el = $("#toast");
    if (el) { el.textContent = `XAUUSD: ${text}`; el.hidden = false; clearTimeout(el._t); el._t = setTimeout(() => el.hidden = true, 8000); }
    try { if (window.Notification && Notification.permission === "granted") new Notification(`XAUUSD: ${text}`, { body, tag: "xauusd-" + text }); } catch {}
  }
  function once(key, text, body) {
    if (seen[key]) return;
    seen[key] = Date.now();
    const keep = Object.entries(seen).sort((a, b) => b[1] - a[1]).slice(0, 100);
    seen = Object.fromEntries(keep); store.set("goldSeen", seen);
    alertUser(text, body);
  }
  function checkBo() {
    const b = G.bo, o = b && b.open;
    if (!o) return;
    const id = o.id, d = o.side === "MUA" ? 1 : -1, past = p => live != null && d * (live - p) >= 0;
    once("bo:" + id, `[Hệ 2] ${o.side} ${fmt(o.entry)} (phá ${d > 0 ? "đỉnh" : "đáy"} 20 nến H1)`, `Dừng lỗ ${fmt(o.sl_now)} · hoà vốn khi tới ${fmt(o.be)} · kéo SL từ ${fmt(o.trail)} · tối đa ${fmt(o.tp)}`);
    if (live == null) return;
    if (d * (live - o.sl_now) <= 0) once(id + ":sl" + o.sl_now, `[Hệ 2] ${o.trailing ? "Chạm SL đã kéo theo lãi" : o.be_hit ? "Về giá vào (hoà vốn)" : "Chạm dừng lỗ"} ${fmt(o.sl_now)}`, `Lệnh ${o.side} từ ${fmt(o.entry)}`);
    else if (past(o.tp)) once(id + ":tp", `[Hệ 2] Đạt tối đa ${fmt(o.tp)} (1:8)`, `Lệnh ${o.side} từ ${fmt(o.entry)}`);
    else if (past(o.trail)) once(id + ":trail", `[Hệ 2] Đạt 1:3 tại ${fmt(o.trail)}, bắt đầu kéo SL`, `Lệnh ${o.side} từ ${fmt(o.entry)}`);
    else if (!o.be_hit && past(o.be)) once(id + ":be", `[Hệ 2] Đạt 1:1 tại ${fmt(o.be)}, dời SL về giá vào`, `Lệnh ${o.side} từ ${fmt(o.entry)}`);
  }
  function checkAlerts() {
    if (!G || G.demo) return;
    checkBo();
    const o = G.open;
    if (!o) return;
    const id = o.id || o.side + o.t_in;
    if (G.fresh && G.fresh.id === o.id) once("in:" + id, `${o.side} ngay ${fmt(o.entry)} · ${o.kind || "quét thanh khoản"}`, `Dừng lỗ ${fmt(o.sl_now)} · hoà vốn khi tới ${fmt(o.be)} · kéo SL từ ${fmt(o.trail)} · tối đa ${fmt(o.tp)}`);
    if (live == null) return;
    const d = o.side === "MUA" ? 1 : -1, past = p => d * (live - p) >= 0;
    if (d * (live - o.sl_now) <= 0) once(id + ":sl" + o.sl_now, `${o.trailing ? "Chạm SL đã kéo theo lãi" : o.be_hit ? "Về giá vào (hoà vốn)" : "Chạm dừng lỗ"} ${fmt(o.sl_now)}`, `Lệnh ${o.side} từ ${fmt(o.entry)}`);
    else if (past(o.tp)) once(id + ":tp", `Đạt tối đa ${fmt(o.tp)} (1:8), chốt lời`, `Lệnh ${o.side} từ ${fmt(o.entry)}`);
    else if (past(o.trail)) once(id + ":trail", `Đạt 1:3 tại ${fmt(o.trail)}, bắt đầu kéo dừng lỗ cách 1,5R`, `Lệnh ${o.side} từ ${fmt(o.entry)}`);
    else if (!o.be_hit && past(o.be)) once(id + ":be", `Đạt 1:1 tại ${fmt(o.be)}, dời dừng lỗ về giá vào`, `Lệnh ${o.side} từ ${fmt(o.entry)}`);
  }
  $("#goldNotify").addEventListener("click", async () => {
    try { const p = await Notification.requestPermission(); $("#goldNotify").textContent = p === "granted" ? "Đã bật thông báo" : "Trình duyệt chặn thông báo"; }
    catch { $("#goldNotify").textContent = "Trình duyệt không hỗ trợ"; }
  });

  /* ---------- Tín hiệu realtime: tính lại 3 khung ngay trong trình duyệt khi mỗi nến M15 đóng ----------
     Cùng quy tắc với engine/gold.py, trên nến PAXG/USDT (Binance, cập nhật tức thì) dời theo giá XAU giao ngay. */
  const RR = { BE: 1, TRAIL: 3, GAP: 1.5, TP: 8 }, SWEEP = 20, BUF = 0.1, REF = 3850, MIN_R = 10, MAX_R = 15, RSI_MAX = 50, SKIP_H = [21, 22, 23, 0, 1, 2];
  const PIV = { K: 3, W: 96, TOL: 0.6, GAP: 5 }; // đáy/đỉnh xoay chiều: 3 nến mỗi bên, trong 96 nến, quét sâu tối đa 0,6 ATR
  const hourVN = t => new Date((t + 7 * 3600) * 1000).getUTCHours();
  const KL = "https://data-api.binance.vision/api/v3/klines?symbol=PAXGUSDT&interval=";
  let RT = null, rtTimer;
  async function klines(iv, n, off) {
    const r = await fetch(`${KL}${iv}&limit=${n}`, { cache: "no-store" });
    if (!r.ok) throw new Error(r.status);
    const now = Date.now(), k = (await r.json()).filter(x => x[6] < now); // chỉ nến đã đóng
    const col = j => k.map(x => +x[j] + off);
    return { t: k.map(x => x[0] / 1000), o: col(1), h: col(2), l: col(3), c: col(4) };
  }
  const ewm = (a, alpha) => { let e = null; return a.map(v => (v == null ? e : (e = e == null ? v : e + alpha * (v - e)))); };
  const emaA = (a, n) => ewm(a, 2 / (n + 1));
  function rsiA(c, n = 14) {
    const d = c.map((v, i) => (i ? v - c[i - 1] : null));
    const up = ewm(d.map(x => (x == null ? null : Math.max(x, 0))), 1 / n), dn = ewm(d.map(x => (x == null ? null : Math.max(-x, 0))), 1 / n);
    return c.map((_, i) => (up[i] == null || !dn[i] ? 50 : 100 - 100 / (1 + up[i] / dn[i])));
  }
  const atrA = b => ewm(b.c.map((c, i) => (i ? Math.max(b.h[i] - b.l[i], Math.abs(b.h[i] - b.c[i - 1]), Math.abs(b.l[i] - b.c[i - 1])) : b.h[i] - b.l[i])), 1 / 14);
  // Giá trị của nến khung lớn ĐÃ ĐÓNG gần nhất tại thời điểm mở từng nến M15
  function closedOn(H, vals, period, ts) { let j = -1; return ts.map(t => { while (j + 1 < H.t.length && H.t[j + 1] + period <= t) j++; return j < 0 ? null : vals[j]; }); }
  const isoVN = t => new Date((t + 7 * 3600) * 1000).toISOString().slice(0, 16);
  const r2j = x => Math.round(x * 100) / 100;

  function rtCompute(m, h1, h4) {
    const e50 = emaA(h4.c, 50), e200 = emaA(h4.c, 200);
    const tr4 = h4.c.map((c, i) => (c > e50[i] && e50[i] > e200[i] ? "Tăng" : c < e50[i] && e50[i] < e200[i] ? "Giảm" : "Đi ngang"));
    const a20 = emaA(h1.c, 20), a50 = emaA(h1.c, 50), rs1 = rsiA(h1.c);
    const zone = h1.c.map((c, i) => {
      if (i < 2) return "";
      const dn = [0, 1, 2].some(k => h1.l[i - k] <= a20[i - k]), upT = [0, 1, 2].some(k => h1.h[i - k] >= a20[i - k]);
      if (a20[i] > a50[i] && c > a50[i] && dn && rs1[i] < 70) return "MUA";
      if (a20[i] < a50[i] && c < a50[i] && upT && rs1[i] > 30) return "BÁN";
      return "";
    });
    const T4 = closedOn(h4, tr4, 14400, m.t), Z1 = closedOn(h1, zone, 3600, m.t);
    const n = m.c.length, atr = atrA(m), m20 = emaA(m.c, 20), m50 = emaA(m.c, 50), rsm = rsiA(m.c);
    const liqLo = [], liqHi = [], wLo = [], wHi = [], sig = [];
    // Kiểu B: đáy/đỉnh xoay chiều còn nguyên (giống patterns() trong engine)
    const minL = (a, b) => { let v = Infinity; for (let k = a; k < b; k++) v = Math.min(v, m.l[k]); return v; };
    const maxH = (a, b) => { let v = -Infinity; for (let k = a; k < b; k++) v = Math.max(v, m.h[k]); return v; };
    let lows = [], highs = [];
    const pat = i => {
      const { K, W, TOL, GAP } = PIV;
      if (i < 2 * K + 1) return null;
      const j = i - K;
      if (m.l[j] === minL(j - K, j + K + 1)) lows.push([j, m.l[j], rsm[j]]);
      if (m.h[j] === maxH(j - K, j + K + 1)) highs.push([j, m.h[j], rsm[j]]);
      lows = lows.filter(p => i - p[0] <= W); highs = highs.filter(p => i - p[0] <= W);
      const tol = TOL * atr[i], wl = Math.min(m.l[i], m.l[i - 1]), wh = Math.max(m.h[i], m.h[i - 1]);
      const rl = Math.min(rsm[i], rsm[i - 1]), rh = Math.max(rsm[i], rsm[i - 1]), c = m.c[i];
      if (c > m.o[i]) {
        const cand = lows.filter(p => i - p[0] >= GAP && minL(p[0] + 1, i - 1) > p[1] && wl < p[1] && p[1] <= wl + tol && c > p[1]);
        if (cand.length) {
          const p1 = cand.reduce((a, b) => (b[1] < a[1] ? b : a));
          const peers = lows.some(q => q[0] < p1[0] && Math.abs(q[1] - p1[1]) <= tol && minL(q[0] + 1, i - 1) >= p1[1] - tol && q[1] > wl);
          return { d: 1, wick: wl, lvl: p1[1], cnt: peers ? 3 : 2, div: rl > p1[2] };
        }
      }
      if (c < m.o[i]) {
        const cand = highs.filter(p => i - p[0] >= GAP && maxH(p[0] + 1, i - 1) < p[1] && wh > p[1] && p[1] >= wh - tol && c < p[1]);
        if (cand.length) {
          const p1 = cand.reduce((a, b) => (b[1] > a[1] ? b : a));
          const peers = highs.some(q => q[0] < p1[0] && Math.abs(q[1] - p1[1]) <= tol && maxH(q[0] + 1, i - 1) <= p1[1] + tol && q[1] < wh);
          return { d: -1, wick: wh, lvl: p1[1], cnt: peers ? 3 : 2, div: rh < p1[2] };
        }
      }
      return null;
    };
    for (let i = 0; i < n; i++) {
      liqLo[i] = i >= SWEEP + 1 ? Math.min(...m.l.slice(i - SWEEP - 1, i - 1)) : null;
      liqHi[i] = i >= SWEEP + 1 ? Math.max(...m.h.slice(i - SWEEP - 1, i - 1)) : null;
      wLo[i] = i ? Math.min(m.l[i], m.l[i - 1]) : m.l[i];
      wHi[i] = i ? Math.max(m.h[i], m.h[i - 1]) : m.h[i];
      sig[i] = null;
      const pb = pat(i);
      if (SKIP_H.includes(hourVN(m.t[i]))) continue;
      const c = m.c[i], sc = c / REF;
      let d = 0, wick, lvl, kind;
      // Kiểu A (ưu tiên): quét đáy/đỉnh 20 nến trong vùng H1 cùng chiều H4, RSI chưa quá mua/bán
      if (liqLo[i] != null && T4[i] === "Tăng" && Z1[i] === "MUA" && wLo[i] < liqLo[i] && c > liqLo[i] && c > m.o[i] && rsm[i] <= RSI_MAX) { d = 1; wick = wLo[i]; lvl = liqLo[i]; kind = "Quét đáy 20 nến"; }
      else if (liqHi[i] != null && T4[i] === "Giảm" && Z1[i] === "BÁN" && wHi[i] > liqHi[i] && c < liqHi[i] && c < m.o[i] && rsm[i] >= 100 - RSI_MAX) { d = -1; wick = wHi[i]; lvl = liqHi[i]; kind = "Quét đỉnh 20 nến"; }
      // Kiểu B: quét 2–3 đáy/đỉnh có phân kỳ RSI, cùng chiều H4
      else if (pb && pb.div && pb.d === (T4[i] === "Tăng" ? 1 : T4[i] === "Giảm" ? -1 : 0)) {
        d = pb.d; wick = pb.wick; lvl = pb.lvl; kind = `Quét ${pb.cnt} ${d > 0 ? "đáy" : "đỉnh"} + phân kỳ RSI`;
      }
      if (!d) continue;
      // Vào ngay ở giá đóng cửa nến quét; dừng lỗ sau râu + 0,1 ATR, tối thiểu 10 giá, bỏ nếu cần hơn 15 giá
      const rk = Math.max(d * (c - wick) + BUF * atr[i], MIN_R * sc);
      if (!(rk <= MAX_R * sc)) continue;
      sig[i] = { side: d > 0 ? "MUA" : "BÁN", d, entry: c, sl: c - d * rk, be: c + d * RR.BE * rk, trail: c + d * RR.TRAIL * rk, tp: c + d * RR.TP * rk, risk: rk, liq: lvl, kind, t: m.t[i] };
    }
    // Quản lý lệnh y như backtest của engine: SL trước, rồi mức tối đa 1:8; tới 1:1 dời SL về giá vào; từ 1:3 kéo SL cách đỉnh lãi 1,5R.
    const trades = []; let pos = null;
    for (let i = Math.min(200, n - 1); i < n; i++) {
      if (pos) {
        const d = pos.d, fav = d * ((d > 0 ? m.h[i] : m.l[i]) - pos.entry) / pos.risk;
        let res = null;
        if (d > 0 ? m.l[i] <= pos.slNow : m.h[i] >= pos.slNow) res = [d * (pos.slNow - pos.entry) / pos.risk];
        else if (fav >= RR.TP) res = [RR.TP];
        else {
          pos.mx = Math.max(pos.mx, fav);
          if (fav >= RR.BE && d * (pos.entry - pos.slNow) > 0) { pos.slNow = pos.entry; pos.t1 = true; }
          if (pos.mx >= RR.TRAIL) { const nsl = pos.entry + d * (pos.mx - RR.GAP) * pos.risk; if (d * (nsl - pos.slNow) > 0) pos.slNow = nsl; }
        }
        if (res) { trades.push(pos.t); pos = null; }
        continue;
      }
      if (sig[i]) pos = { ...sig[i], slNow: sig[i].sl, t1: false, mx: 0 };
    }
    const intactLo = lows.filter(p => minL(p[0] + 1, n) > p[1] && p[1] < m.c[n - 1]).map(p => p[1]);
    const intactHi = highs.filter(p => maxH(p[0] + 1, n) < p[1] && p[1] > m.c[n - 1]).map(p => p[1]);
    const piv = { lo: intactLo.length ? r2j(Math.max(...intactLo)) : null, hi: intactHi.length ? r2j(Math.min(...intactHi)) : null };
    const last = n - 1;
    const open = pos ? { side: pos.side, entry: r2j(pos.entry), sl: r2j(pos.sl), be: r2j(pos.be), trail: r2j(pos.trail), tp: r2j(pos.tp), liq: r2j(pos.liq), kind: pos.kind,
      t_in: isoVN(pos.t), id: `${pos.side}-${pos.t}`, be_hit: pos.t1, trailing: pos.mx >= RR.TRAIL, sl_now: r2j(pos.slNow) } : null;
    const fresh = open && pos.t >= m.t[Math.max(last - 3, 0)] ? open : null;
    // Hệ 2: phá đỉnh/đáy 20 nến H1 theo H4 (giống bo_backtest trong engine)
    const bo = (() => {
      const nh = h1.c.length, a1 = atrA(h1), T4h = closedOn(h4, tr4, 14400, h1.t);
      const hi20 = i => Math.max(...h1.h.slice(i - 20, i)), lo20 = i => Math.min(...h1.l.slice(i - 20, i));
      const sd = h1.c.map((c, i) => (i < 20 ? 0 : c > hi20(i) && T4h[i] === "Tăng" ? 1 : c < lo20(i) && T4h[i] === "Giảm" ? -1 : 0));
      const tr = []; let p = null;
      for (let i = Math.min(200, nh - 1); i < nh; i++) {
        if (p) {
          const d = p.d, fav = d * ((d > 0 ? h1.h[i] : h1.l[i]) - p.entry) / p.risk;
          let res = null;
          if (d > 0 ? h1.l[i] <= p.slNow : h1.h[i] >= p.slNow) res = d * (p.slNow - p.entry) / p.risk;
          else if (fav >= RR.TP) res = RR.TP;
          else {
            p.mx = Math.max(p.mx, fav);
            if (fav >= RR.BE && d * (p.entry - p.slNow) > 0) { p.slNow = p.entry; p.t1 = true; }
            if (p.mx >= RR.TRAIL) { const nsl = p.entry + d * (p.mx - RR.GAP) * p.risk; if (d * (nsl - p.slNow) > 0) p.slNow = nsl; }
          }
          if (res != null) { tr.push(p.t); p = null; }
          continue;
        }
        if (sd[i] && a1[i] > 0) {
          const d = sd[i], e = h1.c[i], rk = 2 * a1[i];
          p = { d, side: d > 0 ? "MUA" : "BÁN", entry: e, risk: rk, sl: e - d * rk, slNow: e - d * rk, be: e + d * rk, trail: e + d * RR.TRAIL * rk, tp: e + d * RR.TP * rk, t: h1.t[i], mx: 0, t1: false };
        }
      }
      const li = nh - 1, t4b = T4h[li];
      const open = p ? { side: p.side, entry: r2j(p.entry), sl: r2j(p.sl), be: r2j(p.be), trail: r2j(p.trail), tp: r2j(p.tp), t_in: isoVN(p.t),
        be_hit: p.t1, trailing: p.mx >= RR.TRAIL, sl_now: r2j(p.slNow), id: `BO-${p.side}-${p.t}` } : null;
      const hiN = Math.max(...h1.h.slice(li - 19, li + 1)), loN = Math.min(...h1.l.slice(li - 19, li + 1));
      const status = open ? `Đang giữ lệnh ${open.side} từ ${open.entry}.` : t4b === "Tăng" ? `H4 tăng: chờ nến H1 đóng cửa trên đỉnh 20 nến ${r2j(hiN)} để MUA.`
        : t4b === "Giảm" ? `H4 giảm: chờ nến H1 đóng cửa dưới đáy 20 nến ${r2j(loN)} để BÁN.` : "H4 đi ngang: đứng ngoài.";
      return { status, trend: t4b, open, fresh: p && p.t >= h1.t[Math.max(li - 1, 0)] ? open : null, sigs: sd.map((x, i) => (x ? h1.t[i] : 0)).filter(Boolean), trades: tr, risk_now: r2j(2 * a1[li]) };
    })();
    const t4 = tr4[h4.c.length - 1], z1 = zone[h1.c.length - 1];
    const m15 = m.c[last] > m20[last] && m20[last] > m50[last] ? "Tăng" : m.c[last] < m20[last] && m20[last] < m50[last] ? "Giảm" : "Đi ngang";
    let status;
    if (open) status = `Đang giữ lệnh ${open.side} từ ${open.entry} (${open.kind}).`;
    else if (t4 === "Đi ngang") status = "H4 đi ngang: đứng ngoài, chờ xu hướng rõ.";
    else {
      const up = t4 === "Tăng", w = up ? "đáy" : "đỉnh", pv = up ? piv.lo : piv.hi, lq = up ? liqLo[last] : liqHi[last], parts = [];
      if (z1 === (up ? "MUA" : "BÁN")) parts.push(`quét ${w} 20 nến ${lq.toFixed(2)}`);
      if (pv != null && !(parts.length && Math.abs(pv - lq) < 0.01)) parts.push(`quét ${w} cũ ${pv.toFixed(2)} có phân kỳ RSI`);
      status = (SKIP_H.includes(hourVN(Date.now() / 1000)) ? "Ngoài giờ vào lệnh (21h–3h giờ VN). " : "") + (parts.length
        ? `H4 ${t4.toLowerCase()}: chờ M15 ${parts.join(" hoặc ")} rồi đóng cửa quay lại để ${up ? "MUA" : "BÁN"} ngay.` : `H4 ${t4.toLowerCase()}: chưa có ${w} nào để chờ quét.`);
    }
    return {
      tf: { H4: t4, H1: z1 || "Chưa có vùng", M15: m15 }, status, fresh, open, piv, bo,
      rsi_m15: r2j(rsm[last]), rsi_h1: r2j(rs1[h1.c.length - 1]), bar: isoVN(m.t[last] + 900),
      sigs: sig.filter(Boolean).map(x => x.t), trades,
    };
  }
  function applyRT() {
    if (!RT || !G || G.demo) return false;
    const key = () => JSON.stringify([G.tf, G.status, G.fresh, G.open, G.bo && [G.bo.status, G.bo.open]]);
    const before = key();
    Object.assign(G, { tf: RT.tf, status: RT.status, fresh: RT.fresh, open: RT.open, piv: RT.piv, rsi_m15: RT.rsi_m15, rsi_h1: RT.rsi_h1, rt_bar: RT.bar });
    if (G.bo) Object.assign(G.bo, { status: RT.bo.status, trend: RT.bo.trend, open: RT.bo.open, fresh: RT.bo.fresh, risk_now: RT.bo.risk_now });
    return before !== key();
  }
  async function rtTick() {
    clearTimeout(rtTimer);
    try {
      if (live == null) { const q = await spot(); live = q.price; }
      const p0 = await klines("15m", 2, 0), off = live - p0.c[p0.c.length - 1]; // chênh PAXG so với XAU giao ngay
      const [m, h1, h4] = await Promise.all([klines("15m", 1000, off), klines("1h", 500, off), klines("4h", 1000, off)]);
      RT = rtCompute(m, h1, h4);
      if (applyRT()) render(); else paintMeta();
      checkAlerts();
    } catch (e) { RT = null; }
    // Chạy lại 5 giây sau khi nến M15 kế tiếp đóng
    const next = Math.ceil(Date.now() / 900e3) * 900e3 + 5000 - Date.now();
    rtTimer = setTimeout(rtTick, marketOpen() ? Math.min(next, 900e3) : 1800e3);
  }

  /* ---------- Hiển thị ---------- */
  function paintHead() {
    const p = live ?? G.price, el = $("#gPrice");
    el.textContent = fmt(p);
    el.className = "gold-price " + (prevLive != null && live != null ? (live > prevLive ? "up" : live < prevLive ? "down" : "") : "");
    const prevClose = G.price / (1 + G.day_chg / 100), chg = (p / prevClose - 1) * 100;
    $("#gChg").innerHTML = `<span class="${chg >= 0 ? "up" : "down"}">${chg >= 0 ? "+" : ""}${fmt(p - prevClose)} (${chg >= 0 ? "+" : ""}${fmt(chg)}%)</span>`;
  }
  function row(label, v, rr, cls = "") { return `<span>${label}</span><span class="v ${cls}">${fmt(v)}</span><span class="rr">${rr}</span>`; }
  function paintSignal() {
    const o = G.open, p = live ?? G.price, el = $("#gSignal");
    if (!o) {
      el.innerHTML = `<div class="label">Hệ 1 · Quét thanh khoản · Trạng thái</div><div class="side" style="color:var(--muted)">Chờ tín hiệu</div>
        <p class="sub">Vào lệnh ngay khi nến M15 quét thanh khoản rồi đóng cửa quay lại, theo chiều H4, ngoài khung 21h–3h. Hai kiểu: quét đáy/đỉnh 20 nến khi H1 đã hồi về EMA20 (RSI M15 chưa quá mua/bán), hoặc quét 2–3 đáy/đỉnh cũ có phân kỳ RSI. Dừng lỗ sát râu nến quét, 10–15 giá.</p>
        <p><b>${G.status}</b></p>
        ${lastTrade()}`;
      return;
    }
    const t = o, d = t.side === "MUA" ? 1 : -1, risk = Math.abs(t.entry - t.sl), rNow = d * (p - t.entry) / risk;
    const slLabel = o.trailing ? "Dừng lỗ (đang kéo theo lãi)" : o.be_hit ? "Dừng lỗ (đã về giá vào)" : "Dừng lỗ";
    el.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center">
        <div><div class="label">Hệ 1 · Lệnh đang mở · ${t.kind || "Quét thanh khoản"}</div><div class="side ${d > 0 ? "up" : "down"}">${d > 0 ? "BUY" : "SELL"} ${fmt(t.entry)}</div></div>
        <div style="text-align:right"><div class="label">Lãi/lỗ hiện tại</div><div class="num ${rNow >= 0 ? "up" : "down"}" style="font-size:18px;font-weight:700">${rNow >= 0 ? "+" : ""}${fmt(rNow)}R</div></div></div>
      <div class="lv">
        ${t.liq != null ? row(`${d > 0 ? "Đáy" : "Đỉnh"} bị quét`, t.liq, "") : ""}
        ${row("Giá vào", t.entry, "")}
        ${row(slLabel, o.sl_now, `−${fmt(risk)}`, "down")}
        ${row(`Dời SL hoà vốn${o.be_hit ? " ✓" : ""}`, t.be, "1:1", "")}
        ${row(`Bắt đầu kéo SL${o.trailing ? " ✓" : ""}`, t.trail, "1:3", "up")}
        ${row("Chốt tối đa", t.tp, "1:8", "up")}
      </div>
      ${ladder(t, p)}
      <p class="sig-meta">Vào lúc ${t.t_in.replace("T", " ")} (giờ VN, giá đóng cửa nến M15 quét). Tới 1:1 dời SL về giá vào; từ 1:3 kéo SL luôn cách mức lãi cao nhất 1,5R; chốt hết ở 1:8.</p>
      ${lastTrade()}`;
  }
  function paintBo() {
    const b = G.bo, el = $("#gBo");
    if (!b) { el.innerHTML = '<div class="empty">Chưa có dữ liệu hệ 2.</div>'; return; }
    const o = b.open, p = live ?? G.price;
    if (!o) {
      el.innerHTML = `<div class="label">Hệ 2 · Trạng thái</div><div class="side" style="color:var(--muted)">Chờ tín hiệu</div>
        <p><b>${b.status}</b></p><p class="sub">Dừng lỗ hiện tại sẽ khoảng ${fmt(b.risk_now)} giá (2 ATR H1). Vào lệnh ngay khi nến H1 đóng cửa phá vỡ.</p>`;
    } else {
      const d = o.side === "MUA" ? 1 : -1, risk = Math.abs(o.entry - o.sl), rNow = d * (p - o.entry) / risk;
      el.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center">
          <div><div class="label">Hệ 2 · Lệnh đang mở</div><div class="side ${d > 0 ? "up" : "down"}">${d > 0 ? "BUY" : "SELL"} ${fmt(o.entry)}</div></div>
          <div style="text-align:right"><div class="label">Lãi/lỗ hiện tại</div><div class="num ${rNow >= 0 ? "up" : "down"}" style="font-size:18px;font-weight:700">${rNow >= 0 ? "+" : ""}${fmt(rNow)}R</div></div></div>
        <div class="lv">
          ${row("Giá vào", o.entry, "")}
          ${row(o.trailing ? "Dừng lỗ (đang kéo theo lãi)" : o.be_hit ? "Dừng lỗ (đã về giá vào)" : "Dừng lỗ", o.sl_now, `−${fmt(risk)}`, "down")}
          ${row(`Dời SL hoà vốn${o.be_hit ? " ✓" : ""}`, o.be, "1:1", "")}
          ${row(`Bắt đầu kéo SL${o.trailing ? " ✓" : ""}`, o.trail, "1:3", "up")}
          ${row("Chốt tối đa", o.tp, "1:8", "up")}
        </div>
        ${ladder(o, p)}
        <p class="sig-meta">Vào lúc ${o.t_in.replace("T", " ")} (giờ VN, nến H1). ${b.status}</p>`;
    }
    const s = b.stats || {}, card = (l, v, sub = "") => `<div class="stat"><div class="label">${l}</div><div class="v">${v}</div>${sub ? `<div class="sub">${sub}</div>` : ""}</div>`;
    $("#gBoStats").innerHTML = s.n ? [
      card("Số lệnh", s.n, `từ ${s.from.slice(0, 10)}`),
      card("Thắng/hoà/thua", `${fmt(s.win, 0)}/${fmt(s.be_pct, 0)}/${fmt(s.loss_pct, 0)}%`),
      card("Lợi nhuận TB", (s.avg_r >= 0 ? "+" : "") + fmt(s.avg_r) + "R", "mỗi lệnh"),
      card("Tổng", (s.total_r >= 0 ? "+" : "") + fmt(s.total_r, 1) + "R"),
      card("Hệ số lợi nhuận", s.pf == null ? "–" : fmt(s.pf)),
      card("Sụt giảm lớn nhất", "−" + fmt(s.max_dd_r, 1) + "R"),
    ].join("") : "";
    $("#gBoTrades").innerHTML = `<thead><tr><th>Vào lúc</th><th>Lệnh</th><th class="n">Giá vào</th><th class="n">Dừng lỗ</th><th>Ra lúc</th><th class="n">Giá ra</th><th>Lý do</th><th class="n">Kết quả</th></tr></thead><tbody>${
      (b.trades || []).slice(0, 12).map(x => `<tr><td class="mono">${x.t_in.replace("T", " ")}</td><td>${sidePill(x.side)}</td><td class="n">${fmt(x.entry)}</td><td class="n down">${fmt(x.sl)}</td><td class="mono">${x.t_out.replace("T", " ")}</td><td class="n">${fmt(x.exit)}</td><td>${x.reason}</td><td class="n ${x.r >= 0 ? "up" : "down"}">${x.r > 0 ? "+" : ""}${fmt(x.r)}R</td></tr>`).join("")
    }</tbody>`;
  }
  function ladder(t, p) {
    const lo = Math.min(t.sl, t.tp), hi = Math.max(t.sl, t.tp), span = hi - lo || 1;
    const pos = v => Math.max(0, Math.min(100, (v - lo) / span * 100));
    const buy = t.side === "MUA", e = pos(t.entry);
    const bg = buy ? `linear-gradient(90deg, var(--down-soft) 0 ${e}%, var(--up-soft) ${e}% 100%)` : `linear-gradient(90deg, var(--up-soft) 0 ${e}%, var(--down-soft) ${e}% 100%)`;
    return `<div class="ladder" style="background:${bg}"><span class="tick" style="left:${pos(t.be)}%"></span><i style="left:calc(${pos(p)}% - 1px)" title="Giá hiện tại"></i></div>`;
  }
  function lastTrade() {
    const x = G.trades[0];
    return x ? `<div class="sig-meta" style="border-top:1px solid var(--line);padding-top:10px">Lệnh gần nhất: ${sidePill(x.side)} ${fmt(x.entry)} → ${fmt(x.exit)} · ${x.reason} · <b class="${x.r >= 0 ? "up" : "down"}">${x.r > 0 ? "+" : ""}${fmt(x.r)}R</b></div>` : "";
  }
  function paintStats() {
    const s = G.stats;
    $("#gStatSub").textContent = s.n ? `Chạy quy tắc trên nến M15 từ ${s.from.slice(0, 10)} (nguồn miễn phí chỉ có 60 ngày M15), một lệnh mỗi lúc, tính theo R (1R = khoảng cách giá vào tới dừng lỗ). Kiểm định dài hơn trên 2 năm M15 của PAXG/USDT (vào ngay khi quét, SL 10–15 giá, đã trừ phí chênh lệch): 232 lệnh, khoảng 10 lệnh/tháng, thắng 28%, hoà 29%, thua 43%, lệnh thắng trung bình +3,4R, +0,49R mỗi lệnh, hệ số lợi nhuận 2,09, sụt giảm lớn nhất 11,5R. Kết quả quá khứ không bảo đảm tương lai.` : "Chưa đủ dữ liệu.";
    const card = (l, v, sub = "") => `<div class="stat"><div class="label">${l}</div><div class="v">${v}</div>${sub ? `<div class="sub">${sub}</div>` : ""}</div>`;
    $("#gStats").innerHTML = s.n ? [
      card("Số lệnh", s.n),
      card("Thắng/hoà/thua", `${fmt(s.win, 0)}/${fmt(s.be_pct, 0)}/${fmt(s.loss_pct, 0)}%`, "thắng = thoát có lãi, hoà = về giá vào"),
      card("Lợi nhuận TB", (s.avg_r >= 0 ? "+" : "") + fmt(s.avg_r) + "R", "mỗi lệnh"),
      card("Tổng", (s.total_r >= 0 ? "+" : "") + fmt(s.total_r, 1) + "R"),
      card("Hệ số lợi nhuận", s.pf == null ? "–" : fmt(s.pf), "tổng lãi / tổng lỗ"),
      card("Sụt giảm lớn nhất", "−" + fmt(s.max_dd_r, 1) + "R"),
    ].join("") : "";
    $("#gTrades").innerHTML = `<thead><tr><th>Vào lúc</th><th>Lệnh</th><th class="n">Giá vào</th><th class="n">Dừng lỗ</th><th>Kiểu</th><th>Ra lúc</th><th class="n">Giá ra</th><th>Lý do</th><th class="n">Kết quả</th></tr></thead><tbody>${
      G.trades.map(x => `<tr><td class="mono">${x.t_in.replace("T", " ")}</td><td>${sidePill(x.side)}</td><td class="n">${fmt(x.entry)}</td><td class="n down">${fmt(x.sl)}</td><td>${x.kind || "–"}</td><td class="mono">${x.t_out.replace("T", " ")}</td><td class="n">${fmt(x.exit)}</td><td>${x.reason}</td><td class="n ${x.r >= 0 ? "up" : "down"}">${x.r > 0 ? "+" : ""}${fmt(x.r)}R</td></tr>`).join("")
    }</tbody>`;
  }
  function paintChart() {
    const el = $("#goldChart");
    if (!window.LightweightCharts) { el.innerHTML = '<div class="empty">Không tải được thư viện biểu đồ.</div>'; return; }
    if (chart) { chart.remove(); chart = null; }
    const c = G[tf], up = cssVar("--up"), down = cssVar("--down");
    const off = 7 * 3600; // hiển thị giờ VN
    chart = LightweightCharts.createChart(el, {
      autoSize: true,
      layout: { background: { color: cssVar("--surface") }, textColor: cssVar("--muted"), fontFamily: "IBM Plex Mono, monospace", fontSize: 11 },
      grid: { vertLines: { color: cssVar("--line") }, horzLines: { color: cssVar("--line") } },
      rightPriceScale: { borderColor: cssVar("--line") }, timeScale: { borderColor: cssVar("--line"), timeVisible: true },
      localization: { locale: "vi-VN" },
    });
    const candles = chart.addCandlestickSeries({ upColor: up, downColor: down, borderVisible: false, wickUpColor: up, wickDownColor: down });
    candles.setData(c.t.map((t, i) => ({ time: t + off, open: c.o[i], high: c.h[i], low: c.l[i], close: c.c[i] })));
    const line = (arr, color) => { const l = chart.addLineSeries({ color, lineWidth: 1.5, priceLineVisible: false, lastValueVisible: false }); l.setData(c.t.map((t, i) => ({ time: t + off, value: arr[i] })).filter(p => p.value != null)); };
    line(c.ema20, cssVar("--accent")); line(c.ema50, cssVar("--ref")); line(c.ema200, cssVar("--ceil"));
    // Đặt mũi tên vào nến chứa thời điểm vào lệnh
    const toTs = s => Date.parse(s + ":00+07:00") / 1000;
    const step = { m15: 900, h1: 3600, h4: 14400 }[tf], t0 = c.t[0];
    const snap = ts => c.t[0] + Math.floor((ts - t0) / step) * step;
    const all = [...G.trades, ...(G.open ? [G.open] : [])];
    const marks = all.map(x => ({ ts: snap(toTs(x.t_in)), x })).filter(m => m.ts >= t0).map(({ ts, x }) => x.side === "MUA"
      ? { time: ts + off, position: "belowBar", color: up, shape: "arrowUp", text: "Mua" }
      : { time: ts + off, position: "aboveBar", color: down, shape: "arrowDown", text: "Bán" });
    candles.setMarkers(marks.sort((a, b) => a.time - b.time));
    const t = G.open;
    if (t) [[t.sl_now, down, "Dừng lỗ"], [t.entry, cssVar("--muted"), "Vào"], [t.be, cssVar("--muted"), "Hoà vốn 1:1"], [t.trail, up, "Kéo SL 1:3"], [t.tp, up, "Tối đa 1:8"]]
      .forEach(([p, col, title]) => candles.createPriceLine({ price: p, color: col, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title }));
    chart.timeScale().setVisibleLogicalRange({ from: c.t.length - 140, to: c.t.length + 3 });
  }
  $$("#gTf button").forEach(b => b.addEventListener("click", () => {
    tf = b.dataset.tf; $$("#gTf button").forEach(x => x.setAttribute("aria-pressed", x === b)); if (G) paintChart();
  }));

  function paintMeta() {
    const zp = z => z === "MUA" ? pill("Tăng").replace(">Tăng<", ">Vùng MUA<") : z === "BÁN" ? pill("Giảm").replace(">Giảm<", ">Vùng BÁN<") : pill("Đi ngang").replace(">Đi ngang<", ">Chưa có vùng<");
    $("#gTrend").innerHTML = `<span class="sub">H4</span>${pill(G.tf.H4)} <span class="sub">H1</span>${zp(G.tf.H1)} <span class="sub">M15</span>${pill(G.tf.M15)}`;
    $("#gInd").textContent = `${fmt(G.rsi_m15, 0)} · ${fmt(G.rsi_h1, 0)}`;
    $("#gAsof").textContent = G.rt_bar ? `Tín hiệu realtime · nến M15 đóng ${G.rt_bar.slice(11)}` : `Tín hiệu tính lúc ${G.generated_at.slice(11)} ${G.generated_at.slice(8, 10)}/${G.generated_at.slice(5, 7)}${G.demo ? "" : " · đang nối realtime…"}`;
  }
  function render() {
    $("#gDemo").hidden = !G.demo;
    paintMeta(); paintHead(); paintSignal(); paintBo(); paintStats();
    if (visible()) paintChart();
  }
  const visible = () => !$('section[data-view="vang"]').hidden;
  let started = false;
  function onShow() {
    if (!visible()) return;
    loadTV();
    if (G && !chart) paintChart();
    if (!started && G) { started = true; if (!G.demo) { liveTick(); rtTick(); } }
  }
  new MutationObserver(onShow).observe($('section[data-view="vang"]'), { attributes: true, attributeFilter: ["hidden"] });

  async function load() {
    try {
      const r = await fetch("data/gold.json", { cache: "no-cache" });
      if (!r.ok) throw new Error(r.status);
      const nd = await r.json();
      const changed = !G || nd.generated_at !== G.generated_at;
      G = nd;
      applyRT();
      if (changed) { render(); checkAlerts(); }
      onShow();
      // Cảnh báo tín hiệu mới vẫn chạy khi đang xem tab khác
      if (!started && !G.demo && window.Notification?.permission === "granted") { started = true; liveTick(); rtTick(); }
    } catch (e) {
      if (!G) $("#gSignal").innerHTML = `<div class="empty">Chưa có dữ liệu vàng (data/gold.json). Chạy <span class="mono">python engine/gold.py</span>.</div>`;
    }
    setTimeout(load, DATA_MS);
  }
  load();
  onShow();
})();
