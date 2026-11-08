/* Shared helpers for every page: data loading, formatting, period, stats,
   the hold-band signature, tooltips, and the saved plan (moves + actions). */
(function () {
  "use strict";
  const C = (window.Core = {});
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"];
  C.MONTHS = MONTHS;
  C.BUDGET = 100000;

  // ------------------------------------------------------------- data
  const cache = {};
  // Data ships as data/<name>.js (window.__DATA[name] = {...}) so pages work from file:// too.
  C.load = (name) => (cache[name] ||= new Promise((resolve, reject) => {
    const D = (window.__DATA ||= {});
    if (D[name]) return resolve(D[name]);
    const s = document.createElement("script");
    s.src = `data/${name}.js`;
    s.onload = () => (D[name] ? resolve(D[name]) : reject(new Error(`data/${name}.js loaded but set no data`)));
    s.onerror = () => reject(new Error(`data/${name}.js is missing`));
    document.head.append(s);
  }));
  C.$ = (sel, root = document) => root.querySelector(sel);
  C.$$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  C.esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  // ------------------------------------------------------------- format
  const nf0 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
  C.usd = (v, opt = {}) => {
    if (v == null || !isFinite(v)) return "–";
    const sign = v < 0 ? "−" : opt.plus && v > 0 ? "+" : "";
    const a = Math.abs(v);
    if (opt.short && a >= 1e6) return `${sign}$${(a / 1e6).toFixed(2)}M`;
    if (opt.short && a >= 1e4) return `${sign}$${(a / 1e3).toFixed(1)}K`;
    if (opt.d) return `${sign}$${a.toLocaleString("en-US", { minimumFractionDigits: opt.d, maximumFractionDigits: opt.d })}`;
    return `${sign}$${nf0.format(a)}`;
  };
  C.int = (v) => (v == null || !isFinite(v) ? "–" : nf0.format(v));
  C.pct = (v, d = 1, plus = false) => {
    if (v == null || !isFinite(v)) return "–";
    const s = (Math.abs(v) * 100).toFixed(d);
    return (v < 0 ? "−" : plus && v > 0 ? "+" : "") + s + "%";
  };
  C.num = (v, d = 1, plus = false) => {
    if (v == null || !isFinite(v)) return "–";
    return (v < 0 ? "−" : plus && v > 0 ? "+" : "") + Math.abs(v).toFixed(d);
  };
  C.date = (iso, opt = { month: "short", day: "numeric" }) => new Date(iso + "T12:00:00").toLocaleDateString("en-US", opt);

  // ------------------------------------------------------------- stats
  // Abramowitz–Stegun erf, |err| < 1.5e-7
  const erf = (x) => {
    const t = 1 / (1 + 0.3275911 * Math.abs(x));
    const y = 1 - ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x);
    return x >= 0 ? y : -y;
  };
  C.phi = (z) => 0.5 * (1 + erf(z / Math.SQRT2));
  C.p2 = (z) => 2 * (1 - C.phi(Math.abs(z)));
  /** Benjamini–Hochberg q-values, same order as input. */
  C.bh = (ps) => {
    const n = ps.length, idx = ps.map((p, i) => [p, i]).sort((a, b) => a[0] - b[0]);
    const q = new Array(n);
    let min = 1;
    for (let k = n - 1; k >= 0; k--) {
      min = Math.min(min, (idx[k][0] * n) / (k + 1));
      q[idx[k][1]] = min;
    }
    return q;
  };

  /** Aggregate one machine's monthly meters over months [a, b] (inclusive). */
  C.agg = (m, a, b) => {
    const s = { ci: 0, theo: 0, win: 0, ah: 0, dh: 0, var: 0, n: 0, pos: 0, days: 0 };
    for (let i = a; i <= b; i++) for (const k in s) s[k] += m[k][i] || 0;
    s.luck = s.win - s.theo;
    s.sd = Math.sqrt(s.var);
    s.z = s.sd > 0 ? s.luck / s.sd : 0;
    s.p = C.p2(s.z);
    s.hold = s.ci > 0 ? s.win / s.ci : null;
    s.theoHold = s.ci > 0 ? s.theo / s.ci : null;
    s.half99 = s.ci > 0 ? (2.576 * s.sd) / s.ci : null;
    s.hitZ = s.n > 0 ? (s.pos - s.n * m.hitp) / Math.sqrt(s.n * m.hitp * (1 - m.hitp)) : 0;
    s.theoHr = s.ah > 0 ? s.theo / s.ah : null;
    s.ciHr = s.ah > 0 ? s.ci / s.ah : null;
    s.avail = s.ah + s.dh > 0 ? s.ah / (s.ah + s.dh) : null;
    s.loc = null;
    for (let i = b; i >= a; i--) if (m.loc[i]) { s.loc = m.loc[i]; break; }
    return s;
  };

  // ------------------------------------------------------------- machine flags (shared by Floor and Machines)
  // Flagged: payout rate off configuration, or luck beyond chance, after Benjamini–Hochberg over all machines.
  // Watch: luck outside the 99% range without surviving correction, a CUSUM alarm in the period,
  // or win-rate-flagged players who played mostly on this machine.
  C.machineFlags = (M, a, b, playerFlags) => {
    const rows = M.map((m) => ({ m, s: C.agg(m, a, b) })).filter((r) => r.s.n > 0);
    const q = C.bh(rows.map((r) => r.s.p)), qh = C.bh(rows.map((r) => C.p2(r.s.hitZ)));
    const pf = (playerFlags && playerFlags[`${a}-${b}`]) || {};
    const inPeriod = (ym) => { if (!ym) return false; const i = +ym.slice(5, 7) - 1; return i >= a && i <= b; };
    const out = {};
    rows.forEach((r, i) => {
      const red = [], watch = [];
      if (qh[i] < 0.05) red.push(`Payout rate off configuration: hit-rate z ${C.num(r.s.hitZ, 0, true)}, q ${qh[i] < 0.001 ? "< 0.001" : qh[i].toFixed(3)}`);
      if (q[i] < 0.05) red.push(`Luck beyond chance: z ${C.num(r.s.z, 1, true)}, q ${q[i].toFixed(3)}`);
      else if (Math.abs(r.s.z) > 2.576) watch.push(`Luck outside the 99% range (z ${C.num(r.s.z, 1, true)}) but not after correction`);
      const cu = r.m.cusum || [];
      if (inPeriod(cu[1])) watch.push(`Payout-rate drift alarm (CUSUM) in ${MONTHS[+cu[1].slice(5, 7) - 1]}`);
      if (inPeriod(cu[0])) watch.push(`Luck drift alarm (CUSUM) in ${MONTHS[+cu[0].slice(5, 7) - 1]}`);
      if (pf[r.m.id]) (red.length ? red : watch).push(`${pf[r.m.id]} carded ${pf[r.m.id] === 1 ? "player" : "players"} flagged for win rate played mostly here`);
      if (red.length || watch.length) out[r.m.id] = { level: red.length ? "flag" : "watch", reasons: red.concat(watch), q: q[i], qh: qh[i] };
    });
    return out;
  };
  C.flagTag = (f) => !f ? '<span class="tag muted">–</span>'
    : `<span class="tag" title="${C.esc(f.reasons.join("; "))}"><span class="dot ${f.level === "flag" ? "lead" : "watch"}"></span>${f.level === "flag" ? "Flagged" : "Watch"}</span>`;

  // ------------------------------------------------------------- period (shared across pages)
  const PKEY = "ga-period";
  C.getPeriod = () => {
    const q = new URLSearchParams(location.search);
    let a = MONTHS.indexOf(q.get("from")), b = MONTHS.indexOf(q.get("to"));
    if (a < 0 || b < 0) {
      try { [a, b] = JSON.parse(localStorage.getItem(PKEY)) || [0, 5]; } catch { a = 0; b = 5; }
    }
    if (!(a >= 0 && b <= 5 && a <= b)) [a, b] = [0, 5];
    return [a, b];
  };
  C.setPeriod = (a, b) => {
    try { localStorage.setItem(PKEY, JSON.stringify([a, b])); } catch { /* storage off */ }
    const u = new URL(location.href);
    u.searchParams.set("from", MONTHS[a]); u.searchParams.set("to", MONTHS[b]);
    history.replaceState(null, "", u);
    C.$$(".nav a").forEach((el) => { const h = new URL(el.href); h.search = u.search; el.href = h; });
  };
  C.periodLabel = (a, b) => (a === b ? `${MONTHS[a]} 2025` : `${MONTHS[a]}–${MONTHS[b]} 2025`);
  /** Renders From/To selects into `el`; calls onChange(a, b). */
  C.periodControl = (el, onChange) => {
    const [a, b] = C.getPeriod();
    const opts = (sel) => MONTHS.map((m, i) => `<option value="${i}" ${i === sel ? "selected" : ""}>${m} 2025</option>`).join("");
    el.innerHTML = `<label class="field">From <select id="p-from" aria-label="Period start">${opts(a)}</select></label>
      <label class="field">To <select id="p-to" aria-label="Period end">${opts(b)}</select></label>`;
    const f = C.$("#p-from", el), t = C.$("#p-to", el);
    const go = (changed) => {
      let x = +f.value, y = +t.value;
      if (x > y) { if (changed === f) y = x; else x = y; f.value = x; t.value = y; }
      C.setPeriod(x, y); onChange(x, y);
    };
    f.onchange = () => go(f); t.onchange = () => go(t);
    C.setPeriod(a, b);
    return [a, b];
  };

  // ------------------------------------------------------------- signature: hold band
  // Grey band = where a fair machine's hold lands 99% of the time; tick = configured (theo) hold;
  // dot = observed hold. Shared domain so rows compare.
  const HB = { w: 104, h: 14, lo: -0.01, hi: 0.17 };
  C.holdBand = (s, opt = {}) => {
    if (s.theoHold == null) return "";
    const w = opt.w || HB.w, h = HB.h, x = (v) => Math.max(2, Math.min(w - 2, ((v - HB.lo) / (HB.hi - HB.lo)) * w));
    const lo = s.theoHold - s.half99, hi = s.theoHold + s.half99;
    const out = s.hold < lo || s.hold > hi;
    const label = `Observed hold ${C.pct(s.hold)}; a fair machine lands between ${C.pct(lo)} and ${C.pct(hi)} 99% of the time`;
    return `<svg class="hb" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" aria-label="${label}"><title>${label}</title>
      <rect class="track" x="0" y="${h / 2 - 0.5}" width="${w}" height="1" rx=".5"/>
      <rect class="band" x="${x(lo)}" y="${h / 2 - 3}" width="${Math.max(2, x(hi) - x(lo))}" height="6" rx="3"/>
      <line class="theo" x1="${x(s.theoHold)}" x2="${x(s.theoHold)}" y1="${h / 2 - 5}" y2="${h / 2 + 5}"/>
      <circle class="obs ${out ? "out" : ""}" cx="${x(s.hold)}" cy="${h / 2}" r="3.5"/></svg>`;
  };

  // ------------------------------------------------------------- tooltip
  let tipEl;
  C.tip = (html, e) => {
    tipEl ||= Object.assign(document.body.appendChild(document.createElement("div")), { className: "tip", role: "tooltip" });
    if (html == null) { tipEl.classList.remove("show"); return; }
    tipEl.innerHTML = html;
    const r = tipEl.getBoundingClientRect();
    let x = e.clientX + 14, y = e.clientY + 14;
    if (x + r.width > innerWidth - 8) x = e.clientX - r.width - 14;
    if (y + r.height > innerHeight - 8) y = e.clientY - r.height - 14;
    tipEl.style.left = x + "px"; tipEl.style.top = y + "px";
    tipEl.classList.add("show");
  };
  C.tipRows = (head, rows) => `<div class="head">${head}</div>` +
    rows.map(([k, v]) => `<div class="row"><span>${k}</span><span>${v}</span></div>`).join("");

  // ------------------------------------------------------------- saved plan
  const PLAN = "ga-plan-v1";
  C.plan = () => {
    try { return Object.assign({ moves: [], actions: null }, JSON.parse(localStorage.getItem(PLAN)) || {}); }
    catch { return { moves: [], actions: null }; }
  };
  C.savePlan = (p) => { try { localStorage.setItem(PLAN, JSON.stringify(p)); } catch { /* storage off */ } };

  // ------------------------------------------------------------- shell
  const PAGES = [
    ["index.html", "Floor"], ["machines.html", "Machines"], ["players.html", "Players"], ["comps.html", "Comps"], ["forecast.html", "Forecast"],
    ["models.html", "Models"], ["context.html", "Context"], ["actions.html", "Actions"],
  ];
  const ICON = {
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    moon: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    x: '<path d="M18 6 6 18M6 6l12 12"/>',
    undo: '<path d="M3 7v6h6"/><path d="M21 17a9 9 0 0 0-15-6.7L3 13"/>',
    arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  };
  C.icon = (n, s = 16) => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICON[n]}</svg>`;

  C.shell = () => {
    const here = location.pathname.split("/").pop() || "index.html";
    const bar = document.createElement("header");
    bar.className = "topbar";
    bar.innerHTML = `<div class="topbar-in">
      <a class="brand" href="index.html${location.search}" aria-label="Gilded Ace floor review, home">
        <svg class="brand-mark" viewBox="0 0 20 20" aria-hidden="true"><rect x="1" y="9" width="18" height="2" rx="1" fill="currentColor" opacity=".35"/><rect x="6" y="7" width="7" height="6" rx="3" fill="currentColor" opacity=".45"/><circle cx="12" cy="10" r="3" fill="currentColor"/></svg>
        Gilded Ace <small>floor review</small></a>
      <nav class="nav" aria-label="Pages">${PAGES.map(([h, t]) =>
        `<a href="${h}${location.search}" ${h === here ? 'aria-current="page"' : ""}>${t}</a>`).join("")}</nav>
      <button class="theme-btn" id="theme" type="button" aria-label="Switch colour theme"></button></div>`;
    document.body.prepend(bar);
    const foot = document.createElement("footer");
    foot.className = "footer";
    foot.innerHTML = `<span>The Gilded Ace is fictional and its data synthetic. Weather, LVCVA and Missouri benchmarks are real public data.</span>
      <span>Code: <span class="mono">analysis/</span>, <span class="mono">scripts/build_site_data.py</span></span>`;
    document.body.append(foot);
    const btn = C.$("#theme");
    const dark = () => document.documentElement.dataset.theme === "dark" ||
      (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
    const paint = () => { btn.innerHTML = C.icon(dark() ? "sun" : "moon"); };
    try { const t = localStorage.getItem("ga-theme"); if (t) document.documentElement.dataset.theme = t; } catch { /* */ }
    paint();
    btn.onclick = () => {
      const t = dark() ? "light" : "dark";
      document.documentElement.dataset.theme = t;
      try { localStorage.setItem("ga-theme", t); } catch { /* */ }
      paint(); window.dispatchEvent(new Event("themechange"));
    };
  };

  C.fail = (el, err) => {
    el.innerHTML = `<div class="card"><p>The data files didn't load (${C.esc(err.message)}).</p>
      <p class="muted">The <span class="mono">data/</span> folder should sit next to this page. Rebuild it with <span class="mono">python scripts/build_site_data.py</span>.</p></div>`;
  };

  // read a CSS variable (charts use these so dark mode follows the theme)
  C.css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

  /** Linear scale helper. */
  C.scale = (d0, d1, r0, r1) => (v) => r0 + ((v - d0) / (d1 - d0 || 1)) * (r1 - r0);
  C.niceMax = (v) => { const p = Math.pow(10, Math.floor(Math.log10(v))); return Math.ceil(v / p) * p; };

  document.addEventListener("DOMContentLoaded", C.shell);
})();
