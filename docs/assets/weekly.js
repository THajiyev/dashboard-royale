/* Weekly pattern page: calendar heatmap, stacked week profiles, weekday levels by half, autocorrelation,
   periodogram, Tukey pairwise matrix, month-profile correlations, locals vs visitors, week-total trend, test table. */
(function () {
  "use strict";
  const C = window.Core, $ = C.$;
  const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const FULL = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
  let calMode = "usd", acfMode = "raw";

  C.registerPage("weekly.html", async () => {
    let D;
    try { D = await C.load("weekly"); } catch (e) { return C.fail($("#main"), e); }
    if (!C.pageActive()) return;
    stats(D); table(D); tests(D);
    const draw = () => { cal(D); overlay(D); weekday(D); acf(D); spec(D); tukey(D); months(D); segments(D); trend(D); };
    draw();
    seg("#cal-mode", (m) => { calMode = m; cal(D); });
    seg("#acf-mode", (m) => { acfMode = m; acf(D); });
    C.listen(window, "resize", draw);
    C.listen(window, "themechange", draw);
  });

  function seg(sel, on) {
    $(sel).onclick = (e) => {
      const b = e.target.closest("button[data-m]"); if (!b) return;
      C.$$("button", $(sel)).forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      on(b.dataset.m);
    };
  }
  const size = (svg, W, H) => { svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("height", H); };
  const hover = (svg, fn) => {
    svg.onmousemove = (e) => { const t = e.target.closest("[data-k]"); C.tip(t ? fn(t.dataset.k) : null, e); };
    svg.onmouseleave = () => C.tip(null);
  };
  const grid = (P, W, y, ticks, fmt) => ticks.map((t) =>
    `<line x1="${P.l}" x2="${W - P.r}" y1="${y(t)}" y2="${y(t)}" stroke="var(--grid)"/><text x="${P.l - 6}" y="${y(t) + 4}" text-anchor="end">${fmt(t)}</text>`).join("");

  // ----------------------------------------------------------------- summary
  function stats(D) {
    const a = D.anova, s = D.spec, st = D.stable, w = D.weekCorr;
    $("#stats").innerHTML = [
      ["Variation explained by weekday", C.pct(a.R2, 0), `Ordinary days; month explains ${C.pct(a.R2_month, 0)}. F = ${a.F}, p ${C.peq(a.p)}`],
      ["Share of variation in the 7-day cycle", C.pct(s.share7, 0), `Periodogram peak at ${s.top[0].period} days; Fisher's g, p ${C.peq(s.fisher_p)}`],
      ["Typical week vs the average shape", `r = ${w.median.toFixed(3)}`, `Median over ${w.n} complete weeks; the worst is ${w.min.toFixed(3)}`],
      ["Shape changed after May 1?", st.p >= 0.05 ? "No" : "Yes", `Weekday × period interaction, F = ${st.F}, p ${C.peq(st.p)}`],
    ].map(([l, v, f], i) => `<div class="stat"><div class="label">${l}</div><div class="value${i === 0 ? " accent" : ""}">${v}</div><div class="foot">${f}</div></div>`).join("");
  }

  // ----------------------------------------------------------------- calendar heatmap
  function cal(D) {
    const svg = $("#cal"), W = svg.clientWidth || 1000, narrow = W < 640;
    const off = D.days[0].dow;
    const nW = Math.ceil((D.days.length + off) / 7);
    const P = { l: narrow ? 32 : 40, r: 4, t: 22, b: 30 };
    const cw = (W - P.l - P.r) / nW, ch = narrow ? 22 : 30, H = P.t + 7 * ch + P.b;
    const vals = D.days.map((d) => d.theo), lo = Math.min(...vals), hi = Math.max(...vals);
    const wkMean = {};
    D.days.forEach((d, i) => { const w = Math.floor((i + off) / 7); (wkMean[w] ||= []).push(d.theo); });
    Object.keys(wkMean).forEach((w) => { const a = wkMean[w]; wkMean[w] = a.reduce((s, v) => s + v, 0) / a.length; });
    let g = "";
    DAYS.forEach((d, k) => { g += `<text x="${P.l - 6}" y="${P.t + k * ch + ch / 2 + 4}" text-anchor="end">${d}</text>`; });
    D.days.forEach((d, i) => {
      const w = Math.floor((i + off) / 7), x = P.l + w * cw, y = P.t + d.dow * ch;
      const dt = new Date(d.d + "T12:00:00");
      if (dt.getDate() === 1) g += `<text x="${x + 1}" y="${P.t - 8}">${C.MONTHS[dt.getMonth()]}</text>`;
      const rel = d.theo / wkMean[w] - 1;
      const fill = calMode === "usd" ? C.rampAt(C.SEQ, (d.theo - lo) / (hi - lo)) : C.rampAt(C.DIV, 0.5 + rel / 0.8);
      g += `<rect class="cell" x="${x + 1}" y="${y + 1}" width="${Math.max(1, cw - 2)}" height="${ch - 2}" rx="${cw > 10 ? 3 : 1}" fill="${C.rgb(fill)}" data-k="${i}"/>`;
      if (d.ev) g += `<rect x="${x + 2}" y="${y + 2}" width="${Math.max(1, cw - 4)}" height="${ch - 4}" rx="2" fill="none" stroke="var(--accent)" stroke-width="2" pointer-events="none"/>`;
    });
    // walkway closure bar under the grid
    const ci = D.days.findIndex((d) => d.clo), cj = D.days.length - 1 - [...D.days].reverse().findIndex((d) => d.clo);
    if (ci >= 0) {
      const x1 = P.l + Math.floor((ci + off) / 7) * cw, x2 = P.l + (Math.floor((cj + off) / 7) + 1) * cw, y = P.t + 7 * ch + 8;
      g += `<line x1="${x1 + 2}" x2="${x2 - 2}" y1="${y}" y2="${y}" stroke="var(--ink-3)" stroke-width="2" stroke-linecap="round"/>
        <text x="${x1 + 2}" y="${y + 16}" style="font-family:var(--sans);font-size:12px;fill:var(--ink-2)">Walkway closure, Mar 3 – Apr 6</text>`;
    }
    size(svg, W, H); svg.innerHTML = g;
    hover(svg, (k) => {
      const d = D.days[+k], w = Math.floor((+k + off) / 7);
      return C.tipRows(C.date(d.d, { weekday: "short", month: "short", day: "numeric" }), [["Theo", C.usd(d.theo)],
        ["Against its week's average", C.pct(d.theo / wkMean[w] - 1, 1, true)], ...(d.ev ? [["Event", C.esc(d.ev)]] : []), ...(d.clo ? [["", "Walkway closed"]] : [])]);
    });
    C.dataTable(svg, "cal-table", "Daily theo and event context shown in the calendar", ["Date", "Weekday", "Theo", "Against week's average", "Event", "Walkway closed"],
      D.days.map((d, i) => {
        const w = Math.floor((i + off) / 7);
        return [C.date(d.d, { weekday: "short", month: "short", day: "numeric" }), FULL[d.dow], C.usd(d.theo),
          C.pct(d.theo / wkMean[w] - 1, 1, true), d.ev ? C.esc(d.ev) : "—", d.clo ? "Yes" : "No"];
      }));
    $("#cal-legend").innerHTML = calMode === "usd"
      ? `<span class="scale">${C.usd(lo, { short: true })}<span class="ramp" style="background:${C.gradient(C.SEQ)}"></span>${C.usd(hi, { short: true })}</span><span><i class="ring"></i>Event day</span>`
      : `<span class="scale">−40%<span class="ramp" style="background:${C.gradient(C.DIV)}"></span>+40% vs the week's average day</span><span><i class="ring"></i>Event day</span>`;
  }

  // ----------------------------------------------------------------- stacked week profiles
  function overlay(D) {
    const svg = $("#ov"), W = svg.clientWidth || 600, H = 300, P = { l: 44, r: 12, t: 12, b: 26 };
    const x = (k) => P.l + (k + 0.5) * ((W - P.l - P.r) / 7), y = C.scale(0.7, 1.45, H - P.b, P.t);
    let g = grid(P, W, y, [0.8, 1.0, 1.2, 1.4], (t) => t.toFixed(1));
    g += `<line x1="${P.l}" x2="${W - P.r}" y1="${y(1)}" y2="${y(1)}" stroke="var(--line-2)"/>`;
    DAYS.forEach((d, k) => { g += `<text x="${x(k)}" y="${H - 8}" text-anchor="middle">${d}</text>`; });
    const path = (a) => a.map((v, k) => `${k ? "L" : "M"}${x(k)} ${y(v)}`).join("");
    D.weeks.forEach((w, i) => {
      g += `<path d="${path(w.prof)}" fill="none" stroke="var(--series-base)" stroke-opacity=".45" stroke-width="1"/>
        <path d="${path(w.prof)}" fill="none" stroke="transparent" stroke-width="8" data-k="${i}"/>`;
    });
    const avg = (half) => DAYS.map((_, k) => D.weekday[k][half]);
    g += `<path d="${path(avg("idxA"))}" fill="none" stroke="var(--cat-1)" stroke-width="2" pointer-events="none"/>`;
    g += `<path d="${path(avg("idxB"))}" fill="none" stroke="var(--cat-2)" stroke-width="2" stroke-dasharray="5 3" pointer-events="none"/>`;
    size(svg, W, H); svg.innerHTML = g;
    hover(svg, (k) => {
      const w = D.weeks[+k];
      return C.tipRows(`Week of ${C.date(w.wk)}`, [["Total theo", C.usd(w.total)], ["Correlation with the average week", w.r.toFixed(3)],
        ["Saturday ÷ Tuesday", (w.prof[5] / w.prof[1]).toFixed(2)], ...(w.ev.length ? [["Events", C.esc(w.ev.join(", "))]] : []), ...(w.clo ? [["", "Walkway closed part of the week"]] : [])]);
    });
    C.dataTable(svg, "ov-table", "Daily profile indices for each complete week", ["Week of", ...FULL, "Total theo", "Correlation with average", "Events", "Walkway closed"],
      D.weeks.map((w) => [C.date(w.wk), ...w.prof.map((v) => C.num(v, 3)), C.usd(w.total), C.num(w.r, 3),
        w.ev.length ? C.esc(w.ev.join(", ")) : "—", w.clo ? "Yes" : "No"]));
  }

  // ----------------------------------------------------------------- weekday levels by half
  function weekday(D) {
    const svg = $("#wd"), W = svg.clientWidth || 600, H = 300, P = { l: 44, r: 12, t: 12, b: 26 };
    const bw = (W - P.l - P.r) / 7, y = C.scale(0.72, 1.38, H - P.b, P.t);
    let g = grid(P, W, y, [0.8, 0.9, 1.0, 1.1, 1.2, 1.3], (t) => t.toFixed(1));
    D.weekday.forEach((r, k) => {
      const cx = P.l + (k + 0.5) * bw;
      g += `<text x="${cx}" y="${H - 8}" text-anchor="middle">${DAYS[k]}</text>`;
      [["idxA", "var(--cat-1)", -7], ["idxB", "var(--cat-2)", 7]].forEach(([h, col, dx]) => {
        g += `<line x1="${cx + dx}" x2="${cx + dx}" y1="${y(r[h + "_lo"])}" y2="${y(r[h + "_hi"])}" stroke="${col}" stroke-width="2" stroke-linecap="round"/>
          <circle cx="${cx + dx}" cy="${y(r[h])}" r="4.5" fill="${col}" stroke="var(--card)" stroke-width="2"/>`;
      });
      g += `<rect x="${cx - bw / 2}" y="${P.t}" width="${bw}" height="${H - P.t - P.b}" fill="transparent" data-k="${k}"/>`;
    });
    size(svg, W, H); svg.innerHTML = g;
    hover(svg, (k) => {
      const r = D.weekday[+k];
      return C.tipRows(FULL[+k], [["Jan–Apr", `${r.idxA.toFixed(3)} (${r.idxA_lo.toFixed(3)}–${r.idxA_hi.toFixed(3)})`],
        ["May–Jun", `${r.idxB.toFixed(3)} (${r.idxB_lo.toFixed(3)}–${r.idxB_hi.toFixed(3)})`], ["Change p / q", `${C.pfmt(r.p)} / ${C.pfmt(r.q)}`]]);
    });
  }

  function table(D) {
    $("#wdt").innerHTML = `<thead><tr><th>Weekday</th><th class="num">Days</th><th class="num">Mean theo</th><th class="num">95% interval</th><th class="num">Index</th>
      <th class="num">Jan–Apr</th><th class="num">May–Jun</th><th class="num">Change p</th><th class="num">q</th></tr></thead><tbody>
      ${D.weekday.map((r, k) => `<tr><td>${FULL[k]}</td><td class="num">${r.n}</td><td class="num">${C.usd(r.mean)}</td>
        <td class="num">${C.usd(r.lo)} – ${C.usd(r.hi)}</td><td class="num">${r.idx.toFixed(3)}</td>
        <td class="num">${r.idxA.toFixed(3)}</td><td class="num">${r.idxB.toFixed(3)}</td><td class="num">${C.pfmt(r.p)}</td><td class="num">${C.pfmt(r.q)}</td></tr>`).join("")}</tbody>`;
  }

  // ----------------------------------------------------------------- autocorrelation
  function acf(D) {
    const svg = $("#acf"), W = svg.clientWidth || 600, H = 260, P = { l: 40, r: 8, t: 12, b: 26 };
    const a = D.acf[acfMode], n = a.length, bw = (W - P.l - P.r) / n;
    const lo = Math.min(-0.4, Math.floor(Math.min(...D.acf.raw, ...D.acf.resid) * 5) / 5), y = C.scale(lo, 1, H - P.b, P.t);
    let g = grid(P, W, y, C.ticks(lo, 1, 4), (t) => t.toFixed(1));
    g += `<rect x="${P.l}" y="${y(D.acf.band)}" width="${W - P.l - P.r}" height="${y(-D.acf.band) - y(D.acf.band)}" fill="var(--band)"/>`;
    g += `<line x1="${P.l}" x2="${W - P.r}" y1="${y(0)}" y2="${y(0)}" stroke="var(--line-2)"/>`;
    a.forEach((v, i) => {
      const lag = i + 1, x0 = P.l + i * bw + 2, w = Math.max(2, bw - 4), wk = lag % 7 === 0;
      const top = Math.min(y(v), y(0)), h = Math.abs(y(v) - y(0));
      g += `<rect x="${x0}" y="${top}" width="${w}" height="${Math.max(1, h)}" rx="${Math.min(2, w / 2)}" fill="${wk ? "var(--accent)" : "var(--ink-3)"}" fill-opacity="${wk ? 1 : 0.55}"/>`;
      if (lag % 7 === 0 || lag === 1) g += `<text x="${x0 + w / 2}" y="${H - 8}" text-anchor="middle">${lag}</text>`;
      g += `<rect x="${P.l + i * bw}" y="${P.t}" width="${bw}" height="${H - P.t - P.b}" fill="transparent" data-k="${i}"/>`;
    });
    size(svg, W, H); svg.innerHTML = g;
    hover(svg, (k) => C.tipRows(`Lag ${+k + 1} days`, [["Autocorrelation", a[+k].toFixed(3)], ["Noise band", `± ${D.acf.band.toFixed(3)}`]]));
    C.dataTable(svg, "acf-table", "Autocorrelation by lag for raw and weekday-adjusted theo", ["Lag, days", "Raw", "Weekday-adjusted", "Noise band"],
      D.acf.raw.map((v, i) => [i + 1, C.num(v, 3), C.num(D.acf.resid[i], 3), `± ${C.num(D.acf.band, 3)}`]));
    const L = D.acf.lb;
    $("#acf-note").innerHTML = acfMode === "raw"
      ? `Days 7, 14, 21 and 28 apart correlate at ${D.acf.weekly_raw.map((v) => v.toFixed(2)).join(", ")}. Ljung–Box test up to lag 7: Q = ${L.Q7}, p ${C.peq(L.raw7)}.`
      : `With each weekday's mean taken out, the weekly spikes are gone (lag 7: ${D.acf.weekly_res[0].toFixed(2)}, inside the noise band). What's left is lag-1 persistence (${D.acf.resid[0].toFixed(2)}): busy stretches last a few days. Ljung–Box still rejects white noise (p ${C.peq(L.res7)}) because of that persistence, not a weekly echo.`;
  }

  // ----------------------------------------------------------------- periodogram
  function spec(D) {
    const svg = $("#sp"), W = svg.clientWidth || 600, H = 260, P = { l: 40, r: 12, t: 16, b: 30 };
    const S = D.spec, tot = S.I.reduce((s, v) => s + v, 0), sh = S.I.map((v) => v / tot);
    const cpw = S.f.map((f) => f * 7), x = C.scale(0, 3.5, P.l, W - P.r), y = C.scale(0, Math.ceil(Math.max(...sh) * 10) / 10, H - P.b, P.t);
    let g = grid(P, W, y, C.ticks(0, Math.ceil(Math.max(...sh) * 10) / 10, 4), (t) => C.pct(t, 0));
    [1, 2, 3].forEach((c) => { g += `<line x1="${x(c)}" x2="${x(c)}" y1="${P.t}" y2="${H - P.b}" stroke="var(--grid)"/>`; });
    [[0.5, "2 weeks"], [1, "7 days"], [2, "3.5 days"], [3, "2.3 days"]].forEach(([c, t]) => { g += `<text x="${x(c)}" y="${H - 10}" text-anchor="middle">${t}</text>`; });
    const pts = cpw.map((c, i) => [x(c), y(sh[i])]);
    g += `<path d="M${x(0)} ${y(0)}${pts.map((p) => `L${p[0]} ${p[1]}`).join("")}L${x(cpw[cpw.length - 1])} ${y(0)}Z" fill="var(--accent-soft)"/>`;
    g += `<path d="${pts.map((p, i) => `${i ? "L" : "M"}${p[0]} ${p[1]}`).join("")}" fill="none" stroke="var(--accent)" stroke-width="2" stroke-linejoin="round"/>`;
    const top = sh.indexOf(Math.max(...sh));
    g += `<text x="${pts[top][0] + 8}" y="${pts[top][1] + 12}" style="font-family:var(--sans);font-size:12px;fill:var(--ink-2)">${C.pct(sh[top], 0)} of variation at ${(1 / S.f[top]).toFixed(1)} days</text>`;
    const bw = (W - P.l - P.r) / cpw.length;
    cpw.forEach((c, i) => { g += `<rect x="${x(c) - bw / 2}" y="${P.t}" width="${bw}" height="${H - P.t - P.b}" fill="transparent" data-k="${i}"/>`; });
    size(svg, W, H); svg.innerHTML = g;
    hover(svg, (k) => C.tipRows(`Cycle of ${(1 / S.f[+k]).toFixed(1)} days`, [["Share of variation", C.pct(sh[+k], 1)]]));
    C.dataTable(svg, "sp-table", "Periodogram power by cycle length", ["Cycle length, days", "Frequency", "Share of variation"],
      S.f.map((f, i) => [C.num(1 / f, 2), C.num(f, 5), C.pct(sh[i], 2)]));
    $("#sp-note").innerHTML = `Fisher's g test for a dominant cycle: g = ${S.fisher_g}, p ${C.peq(S.fisher_p)}. The 7-day cycle and its harmonics (3.5 and 2.3 days) together carry ${C.pct(S.share_weekly, 0)}.`;
  }

  // ----------------------------------------------------------------- matrices
  function tukey(D) {
    C.matrix($("#tk"), { vars: D.tukey.vars, p: D.tukey.p, diff: D.tukey.diff }, { kind: "p" });
    $("#tk-legend").innerHTML = `<span class="scale">p 0.05<span class="ramp" style="background:${C.gradient(C.SEQ.slice(1))}"></span>10<sup>−12</sup></span><span><i class="ns"></i>Not significant</span><span>${D.tukey.n_sig} of ${D.tukey.n_pairs} pairs differ (p &lt; 0.05)</span>`;
  }
  function months(D) {
    const M = D.monthProfiles;
    C.matrix($("#mp"), { vars: M.vars, r: M.r, p: M.p, q: M.p }, { kind: "r", digits: 3 });
    const off = []; for (let i = 0; i < 6; i++) for (let j = 0; j < i; j++) off.push(M.r[i][j]);
    $("#mp-note").innerHTML = `All 15 pairs: r from ${Math.min(...off).toFixed(3)} to ${Math.max(...off).toFixed(3)}, every p ≤ ${C.pfmt(Math.max(...M.p.flat().filter((p) => p < 1)))}. Diverging colour scale, −1 to +1; the cells are at the blue end.`;
  }

  // ----------------------------------------------------------------- locals vs visitors
  function segments(D) {
    const svg = $("#sg"), W = svg.clientWidth || 600, H = 280, P = { l: 44, r: 12, t: 12, b: 26 };
    const x = (k) => P.l + (k + 0.5) * ((W - P.l - P.r) / 7), y = C.scale(0.7, 1.45, H - P.b, P.t);
    let g = grid(P, W, y, [0.8, 1.0, 1.2, 1.4], (t) => t.toFixed(1));
    DAYS.forEach((d, k) => { g += `<text x="${x(k)}" y="${H - 8}" text-anchor="middle">${d}</text>`; });
    const S = D.segments;
    [["locals", "var(--cat-1)", ""], ["nonlocals", "var(--cat-2)", "5 3"]].forEach(([key, col, dash]) => {
      const s = S[key];
      g += `<path d="${s.hi.map((v, k) => `${k ? "L" : "M"}${x(k)} ${y(v)}`).join("")}${s.lo.map((v, k) => `L${x(6 - k)} ${y(s.lo[6 - k])}`).join("")}Z" fill="${col}" fill-opacity=".12"/>`;
      g += `<path d="${s.idx.map((v, k) => `${k ? "L" : "M"}${x(k)} ${y(v)}`).join("")}" fill="none" stroke="${col}" stroke-width="2" stroke-dasharray="${dash}"/>`;
      s.idx.forEach((v, k) => { g += `<circle cx="${x(k)}" cy="${y(v)}" r="4" fill="${col}" stroke="var(--card)" stroke-width="2"/>`; });
    });
    DAYS.forEach((_, k) => { g += `<rect x="${x(k) - (W - P.l - P.r) / 14}" y="${P.t}" width="${(W - P.l - P.r) / 7}" height="${H - P.t - P.b}" fill="transparent" data-k="${k}"/>`; });
    size(svg, W, H); svg.innerHTML = g;
    hover(svg, (k) => C.tipRows(FULL[+k], [["Locals", S.locals.idx[+k].toFixed(3)], ["Visitors and uncarded", S.nonlocals.idx[+k].toFixed(3)]]));
    C.dataTable(svg, "sg-table", "Weekday indices and intervals for locals and visitors", ["Weekday", "Locals", "Locals 95% low", "Locals 95% high",
      "Visitors and uncarded", "Visitors 95% low", "Visitors 95% high"],
      DAYS.map((d, k) => [d, C.num(S.locals.idx[k], 3), C.num(S.locals.lo[k], 3), C.num(S.locals.hi[k], 3),
        C.num(S.nonlocals.idx[k], 3), C.num(S.nonlocals.lo[k], 3), C.num(S.nonlocals.hi[k], 3)]));
    $("#sg-note").innerHTML = `Friday–Saturday over Monday–Thursday: locals ${C.pct(S.locals.weekend_uplift, 0, true)}, visitors ${C.pct(S.nonlocals.weekend_uplift, 0, true)}. Same shape for both? Segment × weekday interaction, F = ${S.test.F}, p ${C.peq(S.test.p)}: no. Locals are ${C.pct(S.locals.share, 0)} of ordinary-day theo.`;
  }

  // ----------------------------------------------------------------- week totals
  function trend(D) {
    const svg = $("#tr"), W = svg.clientWidth || 600, H = 280, P = { l: 52, r: 12, t: 12, b: 26 };
    const t0 = new Date(D.weeks[0].wk + "T12:00:00"), t1 = new Date(D.weeks[D.weeks.length - 1].wk + "T12:00:00");
    const x = (iso) => C.scale(+t0, +t1, P.l + 8, W - P.r - 8)(+new Date(iso + "T12:00:00"));
    const tots = D.weeks.map((w) => w.total), lo = Math.floor(Math.min(...tots) / 5e4) * 5e4, hi = Math.ceil(Math.max(...tots) / 5e4) * 5e4;
    const y = C.scale(lo, hi, H - P.b, P.t);
    let g = grid(P, W, y, C.ticks(lo, hi, 4), (t) => C.usd(t, { short: true }));
    for (let m = 0; m < 6; m++) { const iso = `2025-0${m + 1}-01`; g += `<text x="${x(iso)}" y="${H - 8}" text-anchor="middle">${C.MONTHS[m]}</text>`; }
    g += `<path d="${D.weeks.map((w, i) => `${i ? "L" : "M"}${x(w.wk)} ${y(w.total)}`).join("")}" fill="none" stroke="var(--line-2)" stroke-width="1.5"/>`;
    [["JanApr", "var(--cat-1)"], ["MayJun", "var(--cat-2)"]].forEach(([k, col]) => {
      const T = D.trend[k], s = new Date(T.start + "T12:00:00"), e = new Date(T.end + "T12:00:00");
      const f = (d) => Math.exp(T.a + T.b * ((d - s) / 864e5 / 7));
      g += `<line x1="${x(T.start)}" x2="${x(T.end)}" y1="${y(f(s))}" y2="${y(f(e))}" stroke="${col}" stroke-width="2" stroke-dasharray="${k === "MayJun" ? "5 3" : ""}"/>`;
    });
    D.weeks.forEach((w, i) => {
      const ev = w.ev.length > 0;
      g += `<circle cx="${x(w.wk)}" cy="${y(w.total)}" r="4.5" fill="${ev ? "var(--card)" : "var(--ink-2)"}" stroke="${ev ? "var(--accent)" : "var(--card)"}" stroke-width="${ev ? 2 : 1.5}"/>
        <circle cx="${x(w.wk)}" cy="${y(w.total)}" r="10" fill="transparent" data-k="${i}"/>`;
    });
    size(svg, W, H); svg.innerHTML = g;
    hover(svg, (k) => { const w = D.weeks[+k]; return C.tipRows(`Week of ${C.date(w.wk)}`, [["Total theo", C.usd(w.total)], ...(w.ev.length ? [["Events", C.esc(w.ev.join(", "))]] : [])]); });
    const A = D.trend.JanApr, B = D.trend.MayJun;
    const fit = (T, wk) => {
      if (wk < T.start || wk > T.end) return "—";
      const start = new Date(T.start + "T12:00:00");
      const date = new Date(wk + "T12:00:00");
      return C.usd(Math.exp(T.a + T.b * ((date - start) / 864e5 / 7)));
    };
    C.dataTable(svg, "tr-table", "Weekly theo totals and fitted trends", ["Week of", "Theo", "Jan–Apr fitted", "May–Jun fitted", "Events", "Walkway closed"],
      D.weeks.map((w) => [C.date(w.wk), C.usd(w.total), fit(A, w.wk), fit(B, w.wk),
        w.ev.length ? C.esc(w.ev.join(", ")) : "—", w.clo ? "Yes" : "No"]));
    $("#tr-note").innerHTML = `Jan–Apr: ${C.pct(A.slope, 2, true)} a week (95% CI ${C.pct(A.lo, 2, true)} to ${C.pct(A.hi, 2, true)}, p ${C.peq(A.p)}). May–Jun: ${C.pct(B.slope, 2, true)} a week (${C.pct(B.lo, 2, true)} to ${C.pct(B.hi, 2, true)}, p ${C.peq(B.p)}). Log-linear fit with Newey–West errors; ${A.n} and ${B.n} ordinary weeks.`;
  }

  // ----------------------------------------------------------------- test table
  function tests(D) {
    const a = D.anova, L = D.acf.lb, S = D.spec, st = D.stable, T = D.trend, sg = D.segments.test, w = D.weekCorr;
    const off = []; const M = D.monthProfiles; for (let i = 0; i < 6; i++) for (let j = 0; j < i; j++) off.push(M.r[i][j]);
    const rows = [
      ["Does theo differ by weekday?", "One-way ANOVA, log theo", `F(${a.df1}, ${a.df2}) = ${a.F}`, a.p, `Yes. Weekday explains ${C.pct(a.R2, 0)} of the variation.`],
      ["…without assuming normal errors?", "Kruskal–Wallis", `H = ${a.kw_H}`, a.kw_p, "Yes"],
      ["…once the month's level is accounted for?", "Partial R², weekday given month", C.pct(a.partialR2, 1), a.p, `Yes. Weekday explains ${C.pct(a.partialR2, 0)} of what month leaves.`],
      ["Does every weekday differ from every other?", "Tukey HSD, 21 pairs", `${D.tukey.n_sig} of 21 significant`, Math.max(...D.tukey.p.flat().filter((p) => p != null)), "Yes, every pair"],
      ["Does the series repeat every 7 days?", "Ljung–Box, lags 1–7", `Q = ${L.Q7}`, L.raw7, `Yes. Lag-7 autocorrelation ${D.acf.raw[6].toFixed(2)}.`],
      ["Is 7 days the dominant cycle?", "Fisher's g on the periodogram", `g = ${S.fisher_g}`, S.fisher_p, `Yes. ${C.pct(S.share7, 0)} of variation sits at ${S.top[0].period} days.`],
      ["Is a weekly echo left after the weekday means?", "Autocorrelation at lag 7, residuals", `r = ${D.acf.resid[6].toFixed(2)}`, null, `No: inside the ± ${D.acf.band.toFixed(2)} noise band`],
      ["Did the shape change after May 1?", "Weekday × period interaction F-test", `F(${st.df}, ·) = ${st.F}`, st.p, "No"],
      ["Does each month have the same shape?", "Correlation of month profiles, 15 pairs", `r ${Math.min(...off).toFixed(3)}–${Math.max(...off).toFixed(3)}`, Math.max(...M.p.flat().filter((p) => p < 1)), "Yes"],
      ["Does each week have the same shape?", "Correlation with the average week", `median r = ${w.median.toFixed(3)}`, null, `Yes. All ${w.n} complete weeks have r ≥ ${w.min.toFixed(2)}.`],
      ["Do locals and visitors share the shape?", "Segment × weekday interaction F-test", `F(${sg.df}, ·) = ${sg.F}`, sg.p, "No. Visitors are more weekend-heavy."],
      ["Was the level rising in Jan–Apr?", "Log-linear trend, week totals, HAC", C.pct(T.JanApr.slope, 2, true) + " / week", T.JanApr.p, "Weakly (p ≈ 0.07)"],
      ["Was the level falling in May–Jun?", "Log-linear trend, week totals, HAC", C.pct(T.MayJun.slope, 2, true) + " / week", T.MayJun.p, "Yes"],
    ];
    $("#tests").innerHTML = `<thead><tr><th>Question</th><th>Test</th><th>Statistic</th><th class="num">p</th><th>Answer</th></tr></thead><tbody>
      ${rows.map(([q, t, s, p, v]) => `<tr><td>${q}</td><td class="muted">${t}</td><td class="mono">${s}</td><td class="num">${p == null ? "–" : (q.startsWith("Does every") || q.startsWith("Does each month") ? "≤ " : "") + C.pfmt(p)}</td><td class="verdict">${v}</td></tr>`).join("")}</tbody>`;
  }
})();
