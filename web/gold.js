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
  let G = null, live = null, prevLive = null, chart = null, tf = "h1", tvLoaded = false;

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
      autosize: true, symbol: "OANDA:XAUUSD", interval: "60", timezone: "Asia/Ho_Chi_Minh",
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
    if (G.fresh) once("sig:" + G.fresh.id, `Tín hiệu ${G.fresh.side} tại ${fmt(G.fresh.entry)}`, `Dừng lỗ ${fmt(G.fresh.sl)} · TP1 ${fmt(G.fresh.tp1)} · TP2 ${fmt(G.fresh.tp2)}`);
    const o = G.open;
    if (!o || live == null) return;
    const d = o.side === "MUA" ? 1 : -1, id = o.side + o.t_in, past = p => d * (live - p) >= 0;
    if (d * (live - o.sl_now) <= 0) once(id + ":sl", `${o.tp1_hit ? "Về giá vào (hoà vốn)" : "Chạm dừng lỗ"} ${fmt(o.sl_now)}`, `Lệnh ${o.side} từ ${fmt(o.entry)}`);
    else if (past(o.tp2)) once(id + ":tp2", `Đạt TP2 ${fmt(o.tp2)} (1:3)`, `Lệnh ${o.side} từ ${fmt(o.entry)}`);
    else if (!o.tp1_hit && past(o.tp1)) once(id + ":tp1", `Đạt TP1 ${fmt(o.tp1)} (1:2), dời dừng lỗ về giá vào`, `Lệnh ${o.side} từ ${fmt(o.entry)}`);
  }
  $("#goldNotify").addEventListener("click", async () => {
    try { const p = await Notification.requestPermission(); $("#goldNotify").textContent = p === "granted" ? "Đã bật thông báo" : "Trình duyệt chặn thông báo"; }
    catch { $("#goldNotify").textContent = "Trình duyệt không hỗ trợ"; }
  });

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
        <p class="sub">Chưa có lệnh mở. Hệ thống chỉ vào lệnh khi H4 có xu hướng rõ, giá H1 hồi về EMA20 rồi bật lại theo xu hướng.</p>
        <p class="sub">${G.trend.H4 === "Tăng" ? "H4 đang tăng: chờ nhịp hồi để MUA." : G.trend.H4 === "Giảm" ? "H4 đang giảm: chờ nhịp hồi để BÁN." : "H4 đi ngang: tạm đứng ngoài."}</p>
        ${lastTrade()}`;
      return;
    }
    const d = t.side === "MUA" ? 1 : -1, risk = Math.abs(t.entry - t.sl), rNow = d * (p - t.entry) / risk;
    const sl = o ? o.sl_now : t.sl;
    el.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center">
        <div><div class="label">${o ? "Lệnh đang mở" : "Tín hiệu mới"}</div><div class="side ${d > 0 ? "up" : "down"}">${t.side === "MUA" ? "MUA (Buy)" : "BÁN (Sell)"}</div></div>
        <div style="text-align:right"><div class="label">Lãi/lỗ hiện tại</div><div class="num ${rNow >= 0 ? "up" : "down"}" style="font-size:18px;font-weight:700">${rNow >= 0 ? "+" : ""}${fmt(rNow)}R</div></div></div>
      <div class="lv">
        ${row("Giá vào", t.entry, "")}
        ${row(o && o.tp1_hit ? "Dừng lỗ (đã dời)" : "Dừng lỗ", sl, `−${fmt(risk)}`, "down")}
        ${row(`TP1${o && o.tp1_hit ? " ✓" : ""}`, t.tp1, "R:R 1:2", "up")}
        ${row("TP2", t.tp2, "R:R 1:3", "up")}
      </div>
      ${ladder(t, p)}
      <p class="sig-meta">Vào lúc ${t.t_in.replace("T", " ")} (giờ VN, nến H1). Chạm TP1 chốt một nửa và dời dừng lỗ về giá vào.</p>
      ${lastTrade()}`;
  }
  function ladder(t, p) {
    const lo = Math.min(t.sl, t.tp2), hi = Math.max(t.sl, t.tp2), span = hi - lo || 1;
    const pos = v => Math.max(0, Math.min(100, (v - lo) / span * 100));
    const buy = t.side === "MUA", e = pos(t.entry);
    const bg = buy ? `linear-gradient(90deg, var(--down-soft) 0 ${e}%, var(--up-soft) ${e}% 100%)` : `linear-gradient(90deg, var(--up-soft) 0 ${e}%, var(--down-soft) ${e}% 100%)`;
    return `<div class="ladder" style="background:${bg}"><span class="tick" style="left:${pos(t.tp1)}%"></span><i style="left:calc(${pos(p)}% - 1px)" title="Giá hiện tại"></i></div>`;
  }
  function lastTrade() {
    const x = G.trades[0];
    return x ? `<div class="sig-meta" style="border-top:1px solid var(--line);padding-top:10px">Lệnh gần nhất: ${sidePill(x.side)} ${fmt(x.entry)} → ${fmt(x.exit)} · ${x.reason} · <b class="${x.r >= 0 ? "up" : "down"}">${x.r > 0 ? "+" : ""}${fmt(x.r)}R</b></div>` : "";
  }
  function paintStats() {
    const s = G.stats, s9 = G.stats_90d;
    $("#gStatSub").textContent = s.n ? `Chạy quy tắc trên nến H1 từ ${s.from.slice(0, 10)}, một lệnh mỗi lúc, tính theo R (1R = khoảng cách giá vào tới dừng lỗ). Kết quả quá khứ không bảo đảm tương lai.` : "Chưa đủ dữ liệu.";
    const card = (l, v, sub = "") => `<div class="stat"><div class="label">${l}</div><div class="v">${v}</div>${sub ? `<div class="sub">${sub}</div>` : ""}</div>`;
    $("#gStats").innerHTML = s.n ? [
      card("Số lệnh", s.n, s9.n ? `${s9.n} lệnh trong 90 ngày` : ""),
      card("Tỉ lệ thắng", fmt(s.win, 1) + "%", s9.n ? `90 ngày: ${fmt(s9.win, 1)}%` : ""),
      card("Lợi nhuận TB", (s.avg_r >= 0 ? "+" : "") + fmt(s.avg_r) + "R", "mỗi lệnh"),
      card("Tổng", (s.total_r >= 0 ? "+" : "") + fmt(s.total_r, 1) + "R", s9.n ? `90 ngày: ${s9.total_r >= 0 ? "+" : ""}${fmt(s9.total_r, 1)}R` : ""),
      card("Hệ số lợi nhuận", s.pf == null ? "–" : fmt(s.pf), "tổng lãi / tổng lỗ"),
      card("Sụt giảm lớn nhất", "−" + fmt(s.max_dd_r, 1) + "R"),
    ].join("") : "";
    $("#gTrades").innerHTML = `<thead><tr><th>Vào lúc</th><th>Lệnh</th><th class="n">Giá vào</th><th class="n">Dừng lỗ</th><th class="n">TP1</th><th class="n">TP2</th><th>Ra lúc</th><th class="n">Giá ra</th><th>Lý do</th><th class="n">Kết quả</th></tr></thead><tbody>${
      G.trades.map(x => `<tr><td class="mono">${x.t_in.replace("T", " ")}</td><td>${sidePill(x.side)}</td><td class="n">${fmt(x.entry)}</td><td class="n down">${fmt(x.sl)}</td><td class="n up">${fmt(x.tp1)}</td><td class="n up">${fmt(x.tp2)}</td><td class="mono">${x.t_out.replace("T", " ")}</td><td class="n">${fmt(x.exit)}</td><td>${x.reason}</td><td class="n ${x.r >= 0 ? "up" : "down"}">${x.r > 0 ? "+" : ""}${fmt(x.r)}R</td></tr>`).join("")
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
    const step = tf === "h1" ? 3600 : 14400, t0 = c.t[0];
    const snap = ts => c.t[0] + Math.floor((ts - t0) / step) * step;
    const all = [...G.trades, ...(G.open ? [G.open] : [])];
    const marks = all.map(x => ({ ts: snap(toTs(x.t_in)), x })).filter(m => m.ts >= t0).map(({ ts, x }) => x.side === "MUA"
      ? { time: ts + off, position: "belowBar", color: up, shape: "arrowUp", text: "Mua" }
      : { time: ts + off, position: "aboveBar", color: down, shape: "arrowDown", text: "Bán" });
    candles.setMarkers(marks.sort((a, b) => a.time - b.time));
    const t = G.open || G.fresh;
    if (t) [[G.open ? G.open.sl_now : t.sl, down, "Dừng lỗ"], [t.entry, cssVar("--muted"), "Vào"], [t.tp1, up, "TP1 1:2"], [t.tp2, up, "TP2 1:3"]]
      .forEach(([p, col, title]) => candles.createPriceLine({ price: p, color: col, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title }));
    chart.timeScale().setVisibleLogicalRange({ from: c.t.length - 140, to: c.t.length + 3 });
  }
  $$("#gTf button").forEach(b => b.addEventListener("click", () => {
    tf = b.dataset.tf; $$("#gTf button").forEach(x => x.setAttribute("aria-pressed", x === b)); if (G) paintChart();
  }));

  function render() {
    $("#gDemo").hidden = !G.demo;
    $("#gTrend").innerHTML = ["H1", "H4", "D1"].map(k => `<span class="sub">${k}</span>${pill(G.trend[k])}`).join(" ");
    $("#gInd").textContent = `${fmt(G.rsi_h1, 0)} · ${fmt(G.atr_h1)}`;
    $("#gAsof").textContent = `Tín hiệu tính lúc ${G.generated_at.slice(11)} ${G.generated_at.slice(8, 10)}/${G.generated_at.slice(5, 7)}`;
    paintHead(); paintSignal(); paintStats();
    if (visible()) paintChart();
  }
  const visible = () => !$('section[data-view="vang"]').hidden;
  let started = false;
  function onShow() {
    if (!visible()) return;
    loadTV();
    if (G && !chart) paintChart();
    if (!started && G) { started = true; if (!G.demo) liveTick(); }
  }
  new MutationObserver(onShow).observe($('section[data-view="vang"]'), { attributes: true, attributeFilter: ["hidden"] });

  async function load() {
    try {
      const r = await fetch("data/gold.json", { cache: "no-cache" });
      if (!r.ok) throw new Error(r.status);
      const nd = await r.json();
      const changed = !G || nd.generated_at !== G.generated_at;
      G = nd;
      if (changed) { render(); checkAlerts(); }
      onShow();
      // Cảnh báo tín hiệu mới vẫn chạy khi đang xem tab khác
      if (!started && !G.demo && window.Notification?.permission === "granted") { started = true; liveTick(); }
    } catch (e) {
      if (!G) $("#gSignal").innerHTML = `<div class="empty">Chưa có dữ liệu vàng (data/gold.json). Chạy <span class="mono">python engine/gold.py</span>.</div>`;
    }
    setTimeout(load, DATA_MS);
  }
  load();
  onShow();
})();
