/* Forecast page: Jan–Jun daily theo, May–Jun holdout forecasts with our model's 90% band,
   the July no-action yardstick, the locals/visitors split and the measurement plan. */
(function () {
  "use strict";
  const C = window.Core, $ = C.$;
  const SERIES = [
    { k: "EL", label: "Our model", name: "Our model", note: "picked in advance", color: "--series-model", on: true },
    { k: "B1", label: "Weekday baseline", name: "Weekday baseline", note: "B1", color: "--series-base", dash: true, on: true },
    { k: "EL2A", label: "Weekly refit", name: "Weekly refit", note: "iteration 3", color: "--div-pos", on: false },
    { k: "SEG", label: "Locals + visitors", name: "Locals + visitors", note: "iteration 5", color: "--seq-3", on: false },
  ];
  const S = { a: 0, b: 5 };
  let D, Mo;

  C.registerPage("forecast.html", async () => {
    try { [D, Mo] = await Promise.all([C.load("forecast"), C.load("models")]); }
    catch (e) { return C.fail($("#main"), e); }
    if (!C.pageActive()) return;
    try { const on = JSON.parse(localStorage.getItem("ga-fc-series")); if (on) SERIES.forEach((s) => { s.on = on.includes(s.k); }); } catch { /* */ }
    [S.a, S.b] = C.periodControl($("#period"), (a, b) => { S.a = a; S.b = b; render(); });
    $("#series").onclick = (e) => {
      const b = e.target.closest("[data-k]"); if (!b) return;
      const s = SERIES.find((x) => x.k === b.dataset.k); s.on = !s.on;
      try { localStorage.setItem("ga-fc-series", JSON.stringify(SERIES.filter((x) => x.on).map((x) => x.k))); } catch { /* */ }
      render();
    };
    render(); tables();
    C.listen(window, "themechange", render);
    C.listen(window, "resize", drawChart);
  });

  const mae = (k) => D.holdout.reduce((t, r) => t + Math.abs(r[k] - r.actual), 0) / D.holdout.length;
  function render() {
    $("#title").textContent = `Demand · ${C.periodLabel(S.a, S.b)}`;
    $("#series").innerHTML = SERIES.map((s) => `<button type="button" class="chip" data-k="${s.k}" aria-pressed="${s.on}">
      <i style="background:${s.dash ? "repeating-linear-gradient(90deg,var(--series-base) 0 4px,transparent 4px 7px)" : `var(${s.color})`}"></i>${s.label}</button>`).join("");
    const vs = Mo.vsB1.find((r) => r.model === "EL event-type lift");
    const cover = D.holdout.filter((r) => r.actual >= r.EL * Math.exp(D.bands.EL[0]) && r.actual <= r.EL * Math.exp(D.bands.EL[1])).length / D.holdout.length;
    $("#stats").innerHTML = [
      ["Our model average daily miss", C.usd(mae("EL")), `May–Jun, ${C.pct(mae("EL") / avg("actual"), 1)} of daily theo`],
      ["B1 baseline average miss", C.usd(mae("B1")), "Weekday means of Jan–Apr, nothing else"],
      ["RMSE vs B1", C.pct(vs.dRMSE_vs_B1, 0, true), `95% CI ${C.pct(vs.dRMSE_lo, 0, true)} to ${C.pct(vs.dRMSE_hi, 0, true)}, block bootstrap`],
      ["90% band caught", C.pct(cover, 0), "of holdout days; the band is too narrow"],
    ].map(([l, v, f], i) => `<div class="stat"><div class="label">${l}</div><div class="value${i === 0 ? " accent" : ""}">${v}</div><div class="foot">${f}</div></div>`).join("");
    drawChart();
  }
  const avg = (k) => D.holdout.reduce((t, r) => t + r[k], 0) / D.holdout.length;

  function drawChart() {
    const svg = $("#fc"); if (!D) return;
    const W = svg.clientWidth || 900, H = 340, P = { l: 56, r: 16, t: 20, b: 28 };
    const months = ["2025-01", "2025-02", "2025-03", "2025-04", "2025-05", "2025-06"];
    const days = D.daily.filter((r) => { const m = months.indexOf(r.d.slice(0, 7)); return m >= S.a && m <= S.b; });
    const ho = Object.fromEntries(D.holdout.map((r) => [r.d, r]));
    const on = SERIES.filter((s) => s.on);
    const vals = days.flatMap((r) => [r.theo, ...(ho[r.d] ? [ho[r.d].EL * Math.exp(D.bands.EL[1]), ...on.map((s) => ho[r.d][s.k])] : [])]);
    const lo = Math.floor(Math.min(...vals, ...days.map((r) => ho[r.d] ? ho[r.d].EL * Math.exp(D.bands.EL[0]) : r.theo)) / 20000) * 20000;
    const hi = Math.ceil(Math.max(...vals) / 20000) * 20000;
    const x = C.scale(0, days.length - 1, P.l, W - P.r), y = C.scale(lo, hi, H - P.b, P.t);
    const idx = Object.fromEntries(days.map((r, i) => [r.d, i]));
    let g = "";
    // events
    for (const ev of D.events) {
      const a = days.findIndex((r) => r.d >= ev.start_date), b = days.map((r) => r.d <= ev.end_date).lastIndexOf(true);
      if (a < 0 || b < a || days[a].d > ev.end_date) continue;
      const step = (x(1) - x(0)) / 2;
      g += `<rect x="${x(a) - step}" y="${P.t}" width="${x(b) - x(a) + 2 * step}" height="${H - P.b - P.t}" fill="var(--event)"><title>${C.esc(ev.name)}, ${C.date(ev.start_date)}–${C.date(ev.end_date)}</title></rect>`;
    }
    for (let v = lo; v <= hi; v += 20000) {
      g += `<line x1="${P.l}" x2="${W - P.r}" y1="${y(v)}" y2="${y(v)}" stroke="var(--grid)"/><text x="${P.l - 8}" y="${y(v) + 4}" text-anchor="end">$${v / 1000}K</text>`;
    }
    days.forEach((r, i) => { if (r.d.endsWith("-01")) g += `<text x="${x(i)}" y="${H - 8}">${C.date(r.d, { month: "short" })}</text>`; });
    // holdout split
    if (idx["2025-05-01"] != null) {
      const sx = x(idx["2025-05-01"]) - (x(1) - x(0)) / 2;
      g += `<line x1="${sx}" x2="${sx}" y1="${P.t - 8}" y2="${H - P.b}" stroke="var(--ink-3)" stroke-dasharray="3 3"/>
        <text x="${sx - 8}" y="${P.t - 8}" text-anchor="end">Training</text><text x="${sx + 8}" y="${P.t - 8}">${W < 640 ? "Holdout" : "Holdout, frozen Apr 30"}</text>`;
    }
    const hd = days.filter((r) => ho[r.d]);
    const line = (pts) => pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join("");
    if (hd.length && SERIES[0].on) {
      const up = hd.map((r) => [x(idx[r.d]), y(ho[r.d].EL * Math.exp(D.bands.EL[1]))]);
      const dn = hd.map((r) => [x(idx[r.d]), y(ho[r.d].EL * Math.exp(D.bands.EL[0]))]).reverse();
      g += `<path d="${line(up.concat(dn))}Z" fill="var(--accent-soft)"/>`;
    }
    g += `<path d="${line(days.map((r, i) => [x(i), y(r.theo)]))}" fill="none" stroke="var(--series-actual)" stroke-width="1.5" stroke-linejoin="round"/>`;
    for (const s of on.slice().reverse()) {
      if (!hd.length) break;
      g += `<path d="${line(hd.map((r) => [x(idx[r.d]), y(ho[r.d][s.k])]))}" fill="none" stroke="var(${s.color})" stroke-width="2" stroke-linejoin="round" ${s.dash ? 'stroke-dasharray="4 3"' : ""}/>`;
    }
    g += `<line id="fc-x" y1="${P.t}" y2="${H - P.b}" stroke="var(--ink-3)" opacity="0"/><g id="fc-dots"></g>`;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.innerHTML = g;
    $("#fc-legend").innerHTML = `<span><i style="background:var(--series-actual)"></i>Actual</span>` +
      on.map((s) => `<span><i class="${s.dash ? "dash" : ""}" style="${s.dash ? "" : `background:var(${s.color})`}"></i>${s.name}, ${s.note}</span>`).join("") +
      (SERIES[0].on ? `<span><i class="box" style="background:var(--accent-soft)"></i>Our model 90% band</span>` : "") +
      `<span><i class="box" style="background:var(--event);box-shadow:inset 0 0 0 1px var(--line)"></i>Event days</span>`;

    C.dataTable($("#fc-legend"), "fc-table", "Daily floor theo with the forecasts shown", ["Gaming day", "Actual", ...on.map((s) => s.label)],
      days.map((r) => [C.date(r.d, { weekday: "short", month: "short", day: "numeric" }), C.usd(r.theo), ...on.map((s) => (ho[r.d] ? C.usd(ho[r.d][s.k]) : "–"))]));
    svg.onmousemove = (e) => {
      const rc = svg.getBoundingClientRect(), px = ((e.clientX - rc.left) / rc.width) * W;
      const i = Math.max(0, Math.min(days.length - 1, Math.round(((px - P.l) / (W - P.l - P.r)) * (days.length - 1))));
      const r = days[i], h = ho[r.d];
      const ln = $("#fc-x"); ln.setAttribute("x1", x(i)); ln.setAttribute("x2", x(i)); ln.setAttribute("opacity", 0.5);
      const ev = D.events.find((v) => r.d >= v.start_date && r.d <= v.end_date);
      $("#fc-dots").innerHTML = `<circle cx="${x(i)}" cy="${y(r.theo)}" r="4" fill="var(--series-actual)" stroke="var(--card)" stroke-width="2"/>` +
        (h ? on.map((s) => `<circle cx="${x(i)}" cy="${y(h[s.k])}" r="4" fill="var(${s.color})" stroke="var(--card)" stroke-width="2"/>`).join("") : "");
      C.tip(C.tipRows(C.date(r.d, { weekday: "short", month: "short", day: "numeric" }) + (ev ? `, ${C.esc(ev.name)}` : ""),
        [["Actual", C.usd(r.theo)], ...(h ? on.map((s) => [s.label, `${C.usd(h[s.k])} (${C.pct(h[s.k] / r.theo - 1, 1, true)})`]) : [])]), e);
    };
    svg.onmouseleave = () => { C.tip(null); $("#fc-x")?.setAttribute("opacity", 0); $("#fc-dots") && ($("#fc-dots").innerHTML = ""); };
  }

  // The two decisions our model changes relative to the weekday baseline, computed from the frozen holdout forecasts.
  function decisions() {
    const isEv = (d) => D.events.some((e) => d >= e.start_date && d <= e.end_date);
    const sum = (rows, k) => rows.reduce((t, r) => t + r[k], 0);
    const mde = Math.abs(Mo.measurement[0].mde);
    const jun = D.holdout.filter((r) => r.d.startsWith("2025-06") && !isEv(r.d));
    const b1Bias = sum(jun, "B1") / sum(jun, "actual") - 1, elBias = sum(jun, "EL") / sum(jun, "actual") - 1;
    const wd = (iso) => (new Date(iso + "T12:00:00").getDay() + 6) % 7;            // Mon = 0, as b1Weekday
    const julB1 = D.july.reduce((t, r) => t + D.b1Weekday[wd(r.gaming_date)], 0);
    const julCf = D.july.reduce((t, r) => t + r.forecast_level_adj, 0);
    const row = (l, b, e, hl) => `<tr class="${hl ? "hl" : ""}"><td>${l}</td><td class="num">${b}</td><td class="num">${e}</td></tr>`;
    $("#dec1").innerHTML = `<thead><tr><th></th><th class="num">Weekday baseline</th><th class="num">Our model; July re-anchored to June</th></tr></thead><tbody>
      ${row("Over-forecast on June's ordinary days", C.pct(b1Bias, 1, true), C.pct(elBias, 1, true))}
      ${row("A 30-day test can detect", C.pct(mde, 1), C.pct(mde, 1))}
      ${row("Expected July theo with no action", C.usd(julB1, { short: true }), C.usd(julCf, { short: true }), true)}</tbody>`;
    $("#dec1-p").innerHTML = `Weekday norms put July ${C.pct(julB1 / julCf - 1, 1)} too high, more than the ${C.pct(mde, 1)} a test can detect, so doing nothing would look like failure.
      <strong>Measure July against the June-anchored forecast.</strong>`;
    const edc = D.holdout.filter((r) => r.d >= "2025-05-16" && r.d <= "2025-05-18");
    const a = sum(edc, "actual"), b = sum(edc, "B1"), e = sum(edc, "EL");
    $("#dec2").innerHTML = `<thead><tr><th>EDC weekend, May 16–18</th><th class="num">Weekday baseline</th><th class="num">Our model</th></tr></thead><tbody>
      ${row("Planned theo", C.usd(b, { short: true }), C.usd(e, { short: true }))}
      ${row("Actual theo", C.usd(a, { short: true }), C.usd(a, { short: true }))}
      ${row("Miss", C.pct(b / a - 1, 1, true), C.pct(e / a - 1, 1, true), true)}</tbody>`;
    $("#dec2-p").innerHTML = `Festivals and sports lift play 17–20%; conventions barely 3%.
      <strong>Use our model to plan for event weekends, and schedule maintenance away from them.</strong>`;
  }

  function tables() {
    decisions();
    $("#lvl").textContent = D.julyLevelAdj.toFixed(3);
    // July by week
    const weeks = [];
    D.july.forEach((r, i) => {
      const w = Math.floor(i / 7); weeks[w] ||= { from: r.gaming_date, to: r.gaming_date, f: 0, lo: 0, hi: 0, n: 0 };
      const W = weeks[w]; W.to = r.gaming_date; W.f += r.forecast_level_adj; W.n++;
      W.lo += r.lo90 * D.julyLevelAdj; W.hi += r.hi90 * D.julyLevelAdj;
    });
    const tot = D.july.reduce((t, r) => t + r.forecast_level_adj, 0);
    $("#jul").innerHTML = `<thead><tr><th>Days</th><th class="num">Expected theo</th><th class="num">Per day</th><th class="num">Daily 90% range</th></tr></thead><tbody>
      ${weeks.map((w) => `<tr><td>${C.date(w.from)} – ${C.date(w.to)}</td><td class="num">${C.usd(w.f)}</td><td class="num">${C.usd(w.f / w.n)}</td>
        <td class="num">${C.usd(w.lo / w.n)} – ${C.usd(w.hi / w.n)}</td></tr>`).join("")}
      <tr><td><strong style="font-weight:500">Jul 1 – 30</strong></td><td class="num"><strong style="font-weight:500">${C.usd(tot, { short: true })}</strong></td><td class="num">${C.usd(tot / D.july.length)}</td><td></td></tr></tbody>`;
    // segments
    const base = (k) => (D.segments[2][k] + D.segments[3][k]) / 2;
    $("#seg").innerHTML = `<thead><tr><th>Month</th><th class="num">Locals</th><th class="num">Visitors</th><th class="num">Floor</th><th class="num">Avg high</th></tr></thead><tbody>
      ${D.segments.map((r, i) => `<tr><td>${C.MONTHS[i]}</td>
        <td class="num">${C.usd(r.locals_usd_day, { short: true })}${i >= 4 ? `<span class="sub">${C.pct(r.locals_usd_day / base("locals_usd_day") - 1, 0, true)} vs Mar–Apr</span>` : ""}</td>
        <td class="num">${C.usd(r.visitors_usd_day, { short: true })}${i >= 4 ? `<span class="sub">${C.pct(r.visitors_usd_day / base("visitors_usd_day") - 1, 0, true)} vs Mar–Apr</span>` : ""}</td>
        <td class="num">${C.usd(r.total_usd_day, { short: true })}</td><td class="num">${C.num(r.avg_high_c, 0)}°C</td></tr>`).join("")}</tbody>`;
    // measurement
    $("#meas").innerHTML = `<thead><tr><th>Action</th><th>Compare</th><th class="num">Window</th><th class="num">Detectable effect</th><th>Note</th></tr></thead><tbody>
      ${Mo.measurement.map((r) => `<tr><td>${C.esc(r.action)}</td><td>${C.esc(r.metric)}</td><td class="num">${r.window_days} days</td>
        <td class="num">${C.pct(Math.abs(r.mde), 1)}${r.mde < 0 ? " fewer" : ""}</td><td class="small" style="color:var(--ink-2)">${C.esc(r.note)}</td></tr>`).join("")}</tbody>`;
  }
})();
