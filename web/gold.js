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
      paintHead(); paintSignal(); checkAlerts();
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
  function checkAlerts() {
    if (!G || G.demo) return;
    if (G.fresh) once("sig:" + G.fresh.id, `Tín hiệu ${G.fresh.side} tại ${fmt(G.fresh.entry)}`, `Dừng lỗ ${fmt(G.fresh.sl)} · hoà vốn khi tới ${fmt(G.fresh.be)} · chốt lời ${fmt(G.fresh.tp)}`);
    const o = G.open;
    if (!o || live == null) return;
    const d = o.side === "MUA" ? 1 : -1, id = o.side + o.t_in, past = p => d * (live - p) >= 0;
    if (d * (live - o.sl_now) <= 0) once(id + ":sl", `${o.be_hit ? "Về giá vào (hoà vốn)" : "Chạm dừng lỗ"} ${fmt(o.sl_now)}`, `Lệnh ${o.side} từ ${fmt(o.entry)}`);
    else if (past(o.tp)) once(id + ":tp", `Đạt mục tiêu ${fmt(o.tp)} (1:3), chốt lời`, `Lệnh ${o.side} từ ${fmt(o.entry)}`);
    else if (!o.be_hit && past(o.be)) once(id + ":be", `Đạt 1:1 tại ${fmt(o.be)}, dời dừng lỗ về giá vào`, `Lệnh ${o.side} từ ${fmt(o.entry)}`);
  }
  $("#goldNotify").addEventListener("click", async () => {
    try { const p = await Notification.requestPermission(); $("#goldNotify").textContent = p === "granted" ? "Đã bật thông báo" : "Trình duyệt chặn thông báo"; }
    catch { $("#goldNotify").textContent = "Trình duyệt không hỗ trợ"; }
  });

  /* ---------- Tín hiệu realtime: tính lại 3 khung ngay trong trình duyệt khi mỗi nến M15 đóng ----------
     Cùng quy tắc với engine/gold.py, trên nến PAXG/USDT (Binance, cập nhật tức thì) dời theo giá XAU giao ngay. */
  const RR = { BE: 1, TP: 3 }, SWEEP = 20, BUF = 0.1, REF = 3850, MIN_R = 15, MAX_R = 20;
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
    for (let i = 0; i < n; i++) {
      liqLo[i] = i >= SWEEP + 1 ? Math.min(...m.l.slice(i - SWEEP - 1, i - 1)) : null;
      liqHi[i] = i >= SWEEP + 1 ? Math.max(...m.h.slice(i - SWEEP - 1, i - 1)) : null;
      wLo[i] = i ? Math.min(m.l[i], m.l[i - 1]) : m.l[i];
      wHi[i] = i ? Math.max(m.h[i], m.h[i - 1]) : m.h[i];
      sig[i] = null;
      if (liqLo[i] == null) continue;
      const c = m.c[i], sc = c / REF;
      let side = null, raw;
      if (T4[i] === "Tăng" && Z1[i] === "MUA" && wLo[i] < liqLo[i] && c > liqLo[i] && c > m.o[i]) { side = "MUA"; raw = c - wLo[i]; }
      else if (T4[i] === "Giảm" && Z1[i] === "BÁN" && wHi[i] > liqHi[i] && c < liqHi[i] && c < m.o[i]) { side = "BÁN"; raw = wHi[i] - c; }
      if (!side) continue;
      const risk = Math.max(raw + BUF * atr[i], MIN_R * sc);
      if (risk > MAX_R * sc) continue;
      const d = side === "MUA" ? 1 : -1;
      sig[i] = { side, entry: c, sl: c - d * risk, be: c + d * RR.BE * risk, tp: c + d * RR.TP * risk, risk, liq: d > 0 ? liqLo[i] : liqHi[i], t: m.t[i] };
    }
    // Quản lý lệnh y như backtest của engine: SL trước, rồi mục tiêu, tới 1:1 dời SL về giá vào, tín hiệu ngược thì đóng
    const trades = []; let pos = null;
    for (let i = Math.min(200, n - 1); i < n; i++) {
      if (pos) {
        const d = pos.side === "MUA" ? 1 : -1, hi = m.h[i], lo = m.l[i];
        const hitSl = d > 0 ? lo <= pos.slNow : hi >= pos.slNow, hitTp = d > 0 ? hi >= pos.tp : lo <= pos.tp, hitBe = d > 0 ? hi >= pos.be : lo <= pos.be;
        const opp = sig[i] && sig[i].side !== pos.side;
        let res = null;
        if (hitSl) res = [pos.t1 ? 0 : -1];
        else if (hitTp) res = [RR.TP];
        else { if (hitBe && !pos.t1) { pos.t1 = true; pos.slNow = pos.entry; } if (opp) res = [d * (m.c[i] - pos.entry) / pos.risk]; }
        if (res) { trades.push(pos.t); pos = null; if (!opp) continue; }
      }
      if (!pos && sig[i]) pos = { ...sig[i], slNow: sig[i].sl, t1: false };
    }
    const out = s => ({ side: s.side, entry: r2j(s.entry), sl: r2j(s.sl), be: r2j(s.be), tp: r2j(s.tp), liq: r2j(s.liq), t_in: isoVN(s.t) });
    const last = n - 1, taken = new Set([...trades, ...(pos ? [pos.t] : [])]);
    let fresh = null;
    for (let i = last; i > last - 4 && i >= 0; i--) if (sig[i] && taken.has(m.t[i])) { fresh = { ...out(sig[i]), id: `${sig[i].side}-${m.t[i]}` }; break; }
    const t4 = tr4[h4.c.length - 1], z1 = zone[h1.c.length - 1];
    const m15 = m.c[last] > m20[last] && m20[last] > m50[last] ? "Tăng" : m.c[last] < m20[last] && m20[last] < m50[last] ? "Giảm" : "Đi ngang";
    let status;
    if (t4 === "Đi ngang") status = "H4 đi ngang: đứng ngoài, chờ xu hướng rõ.";
    else if (z1 !== (t4 === "Tăng" ? "MUA" : "BÁN")) status = `H4 ${t4.toLowerCase()}: chờ giá H1 hồi về EMA20 để vào vùng ${t4 === "Tăng" ? "MUA" : "BÁN"}.`;
    else status = `H4 ${t4.toLowerCase()}, H1 đang ở vùng ${z1}: chờ M15 quét ${z1 === "MUA" ? "đáy" : "đỉnh"} ${(z1 === "MUA" ? liqLo[last] : liqHi[last]).toFixed(2)} rồi đóng cửa quay lại để vào lệnh.`;
    return {
      tf: { H4: t4, H1: z1 || "Chưa có vùng", M15: m15 }, status, fresh,
      open: pos ? { ...out(pos), be_hit: pos.t1, sl_now: r2j(pos.slNow) } : null,
      rsi_m15: r2j(rsm[last]), rsi_h1: r2j(rs1[h1.c.length - 1]), bar: isoVN(m.t[last] + 900),
      sigs: sig.filter(Boolean).map(x => x.t), trades,
    };
  }
  function applyRT() {
    if (!RT || !G || G.demo) return false;
    const before = JSON.stringify([G.tf, G.status, G.fresh, G.open]);
    Object.assign(G, { tf: RT.tf, status: RT.status, fresh: RT.fresh, open: RT.open, rsi_m15: RT.rsi_m15, rsi_h1: RT.rsi_h1, rt_bar: RT.bar });
    return before !== JSON.stringify([G.tf, G.status, G.fresh, G.open]);
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
    const o = G.open, f = G.fresh, p = live ?? G.price, el = $("#gSignal");
    const t = o || f;
    if (!t) {
      el.innerHTML = `<div class="label">Trạng thái</div><div class="side" style="color:var(--muted)">Chờ tín hiệu</div>
        <p class="sub">Chưa có lệnh mở. Hệ thống chỉ vào lệnh khi H4 có xu hướng rõ, H1 hồi về EMA20 và giá M15 quét thanh khoản (chọc thủng đáy/đỉnh 20 nến gần nhất) rồi đóng cửa quay lại.</p>
        <p><b>${G.status}</b></p>
        ${lastTrade()}`;
      return;
    }
    const d = t.side === "MUA" ? 1 : -1, risk = Math.abs(t.entry - t.sl), rNow = d * (p - t.entry) / risk;
    const sl = o ? o.sl_now : t.sl;
    el.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center">
        <div><div class="label">${o ? "Lệnh đang mở" : "Tín hiệu mới"}</div><div class="side ${d > 0 ? "up" : "down"}">${t.side === "MUA" ? "MUA (Buy)" : "BÁN (Sell)"}</div></div>
        <div style="text-align:right"><div class="label">Lãi/lỗ hiện tại</div><div class="num ${rNow >= 0 ? "up" : "down"}" style="font-size:18px;font-weight:700">${rNow >= 0 ? "+" : ""}${fmt(rNow)}R</div></div></div>
      <div class="lv">
        ${t.liq != null ? row("Thanh khoản bị quét", t.liq, "") : ""}
        ${row("Giá vào", t.entry, "")}
        ${row(o && o.be_hit ? "Dừng lỗ (đã về giá vào)" : "Dừng lỗ", sl, `−${fmt(risk)}`, "down")}
        ${row(`Dời SL hoà vốn${o && o.be_hit ? " ✓" : ""}`, t.be, "1:1", "")}
        ${row("Chốt lời", t.tp, "R:R 1:3", "up")}
      </div>
      ${ladder(t, p)}
      <p class="sig-meta">Vào lúc ${t.t_in.replace("T", " ")} (giờ VN, nến M15). Dừng lỗ đặt sau râu nến quét. Giá đi được 1:1 thì dời dừng lỗ về giá vào, chốt toàn bộ ở 1:3.</p>
      ${lastTrade()}`;
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
    $("#gStatSub").textContent = s.n ? `Chạy quy tắc trên nến M15 từ ${s.from.slice(0, 10)} (nguồn miễn phí chỉ có 60 ngày M15), một lệnh mỗi lúc, tính theo R (1R = khoảng cách giá vào tới dừng lỗ). Kiểm định dài hơn trên 2 năm M15 của PAXG/USDT: 197 lệnh, +0,21R mỗi lệnh, hệ số lợi nhuận 1,48, sụt giảm lớn nhất 9R. Kết quả quá khứ không bảo đảm tương lai.` : "Chưa đủ dữ liệu.";
    const card = (l, v, sub = "") => `<div class="stat"><div class="label">${l}</div><div class="v">${v}</div>${sub ? `<div class="sub">${sub}</div>` : ""}</div>`;
    $("#gStats").innerHTML = s.n ? [
      card("Số lệnh", s.n),
      card("Thắng/hoà/thua", `${fmt(s.win, 0)}/${fmt(s.be_pct, 0)}/${fmt(s.loss_pct, 0)}%`, "thắng = chạm 1:3, hoà = về giá vào"),
      card("Lợi nhuận TB", (s.avg_r >= 0 ? "+" : "") + fmt(s.avg_r) + "R", "mỗi lệnh"),
      card("Tổng", (s.total_r >= 0 ? "+" : "") + fmt(s.total_r, 1) + "R"),
      card("Hệ số lợi nhuận", s.pf == null ? "–" : fmt(s.pf), "tổng lãi / tổng lỗ"),
      card("Sụt giảm lớn nhất", "−" + fmt(s.max_dd_r, 1) + "R"),
    ].join("") : "";
    $("#gTrades").innerHTML = `<thead><tr><th>Vào lúc</th><th>Lệnh</th><th class="n">Giá vào</th><th class="n">Dừng lỗ</th><th class="n">Chốt lời 1:3</th><th>Ra lúc</th><th class="n">Giá ra</th><th>Lý do</th><th class="n">Kết quả</th></tr></thead><tbody>${
      G.trades.map(x => `<tr><td class="mono">${x.t_in.replace("T", " ")}</td><td>${sidePill(x.side)}</td><td class="n">${fmt(x.entry)}</td><td class="n down">${fmt(x.sl)}</td><td class="n up">${fmt(x.tp)}</td><td class="mono">${x.t_out.replace("T", " ")}</td><td class="n">${fmt(x.exit)}</td><td>${x.reason}</td><td class="n ${x.r >= 0 ? "up" : "down"}">${x.r > 0 ? "+" : ""}${fmt(x.r)}R</td></tr>`).join("")
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
    const t = G.open || G.fresh;
    if (t) [[G.open ? G.open.sl_now : t.sl, down, "Dừng lỗ"], [t.entry, cssVar("--muted"), "Vào"], [t.be, cssVar("--muted"), "Hoà vốn 1:1"], [t.tp, up, "Chốt lời 1:3"]]
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
    paintMeta(); paintHead(); paintSignal(); paintStats();
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
