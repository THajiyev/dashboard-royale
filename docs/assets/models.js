/* Models page: B1 bars, forest plot of RMSE change vs B1, full table, iterations,
   noise floor, Phase 2 models, machine model and impact-estimator validation. */
(function () {
  "use strict";
  const C = window.Core, $ = C.$;
  const NAME = {
    "EL x CatBoost residual (best post hoc)": "EL × CatBoost residual",
    "EL + hol near1 lam=5": "EL + within-1-day-of-holiday flag",
    "EL + hol longwknd+day lam=2": "EL + long-weekend and holiday flags",
    "EL + hol kernel1 lam=20": "EL + holiday closeness kernel",
    "EL event-type lift": "EL event-type lift",
    "EL + hist season_yoy beta=0.5": "EL + city visitor trend",
    "B2 event-aware weekday": "B2 event-aware weekday",
    "EL2A segments: bottom_up beta=0.5": "Segments: locals + visitors",
    "EL2A segments: bottom_up beta=1.0": "Segments, bottom-up, full visitor trend",
    "EL2A segments: bottom_up beta=0.0": "Segments, bottom-up, no visitor trend",
    "EL2A segments: top_down beta=0.0": "Segments, top-down, no visitor trend",
    "EL2A segments: top_down beta=0.5": "Segments, top-down, half visitor trend",
    "EL2A segments: top_down beta=1.0": "Segments, top-down, full visitor trend",
    "EL + hist seasonal beta=0.5": "EL + 2023–24 seasonal pattern",
    "EL2A + hist seasonal beta=0.5": "EL2A + 2023–24 seasonal pattern",
    "EL2A + hol longwknd+day lam=2": "EL2A + long-weekend and holiday flags",
    "EL2A + hol near1 lam=5": "EL2A + within-1-day-of-holiday flag",
    "EL2 + 28d anchor": "EL2A, 28-day anchor, weekly refresh",
    "EL2A + hol kernel1 lam=20": "EL2A + holiday closeness kernel",
    "EL2A + hist season_yoy beta=0.5": "EL2A + city visitor trend",
    "EL + recent-level (28d) + payday": "EL + recent level + payday",
    "B1 weekday mean": "B1 weekday mean, baseline",
    "B0 constant mean": "B0 constant mean",
  };
  const ITERS = [
    ["Phase 0 and 2", "Baselines B0, B1, B2, then OLS, ETS, SARIMAX, structural, LightGBM, Bayesian ridge and an ensemble. B2, the event-aware weekday mean, was best; none of the others beat it."],
    ["Iteration 1", "EL: B2's weekday base with a separate lift per event type, shrunk toward its class. Sports and festivals about +17–20%, conventions about +3%. The current headline."],
    ["Iteration 2", "About 30 variants: AutoARIMA, AutoETS, Theta, MSTL, Prophet, XGBoost and CatBoost, bottom-up by zone, combinations. All three advance picks lost to EL."],
    ["Iteration 3", "EL2A: refit weekly, level anchored to the last 28 non-event days. Best on ordinary days, but it over-forecast Locals Week by about 10%."],
    ["Iteration 4", "Holiday flags, a payday term, 2023–24 seasonality and the latest published city visitor trend. Holiday flags moved error by ±2%; the seasonal pattern made it worse."],
    ["Iteration 5", "Separate weekly forecasts for locals and visitors, so a locals promotion lifts only locals. It removed part of the Locals Week overshoot. A July test with a written decision rule is planned."],
  ];

  document.addEventListener("DOMContentLoaded", async () => {
    let D, F;
    try { [D, F] = await Promise.all([C.load("models"), C.load("forecast")]); }
    catch (e) { return C.fail($("#main"), e); }
    const draw = () => { b1(F); forest(D); };
    draw(); tables(D);
    addEventListener("resize", draw);
    addEventListener("themechange", draw);
  });

  function b1(F) {
    const svg = $("#b1"), W = svg.clientWidth || 360, H = 200, P = { l: 44, r: 8, t: 12, b: 24 };
    const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], v = F.b1Weekday;
    const max = 180000, y = C.scale(0, max, H - P.b, P.t), bw = (W - P.l - P.r) / 7;
    let g = "";
    for (let t = 0; t <= max; t += 60000) g += `<line x1="${P.l}" x2="${W - P.r}" y1="${y(t)}" y2="${y(t)}" stroke="var(--grid)"/><text x="${P.l - 6}" y="${y(t) + 4}" text-anchor="end">$${t / 1000}K</text>`;
    v.forEach((val, i) => {
      const x0 = P.l + i * bw + 4, w = bw - 8, top = y(val), r = Math.min(4, w / 2);
      g += `<path d="M${x0} ${y(0)}V${top + r}Q${x0} ${top} ${x0 + r} ${top}H${x0 + w - r}Q${x0 + w} ${top} ${x0 + w} ${top + r}V${y(0)}Z" fill="${i >= 4 && i <= 5 ? "var(--accent)" : "var(--ink-3)"}" fill-opacity="${i >= 4 && i <= 5 ? 1 : 0.55}"><title>${days[i]}: ${C.usd(val)}</title></path>
        <text x="${x0 + w / 2}" y="${H - 6}" text-anchor="middle">${days[i]}</text>`;
    });
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.innerHTML = g;
  }

  function forest(D) {
    const svg = $("#forest"), rows = D.vsB1.slice().sort((a, b) => a.RMSE - b.RMSE);
    const W = svg.clientWidth || 1000, narrow = W < 700, row = 26;
    const P = { l: narrow ? 180 : 320, r: 96, t: 24, b: 28 }, H = P.t + rows.length * row + P.b;
    const lo = -0.6, hi = 0.2, x = C.scale(lo, hi, P.l, W - P.r);
    let g = "";
    for (let k = 0; k <= 4; k++) { const t = Math.round((lo + k * 0.2) * 10) / 10; g += `<line x1="${x(t)}" x2="${x(t)}" y1="${P.t - 8}" y2="${H - P.b}" stroke="${Math.abs(t) < 1e-9 ? "var(--ink-3)" : "var(--grid)"}"/>
      <text x="${x(t)}" y="${H - 8}" text-anchor="middle">${C.pct(t, 0, true)}</text>`; }
    g += `<text x="${x(0) + 6}" y="${P.t - 10}">B1</text><text x="${x(lo)}" y="${P.t - 10}">Better</text><text x="${W - P.r}" y="${P.t - 10}" text-anchor="end">Worse</text>`;
    rows.forEach((r, i) => {
      const cy = P.t + i * row + row / 2, name = NAME[r.model] || r.model, head = r.model === "EL event-type lift";
      const base = r.model === "B1 weekday mean";
      const clip = (v) => Math.max(lo, Math.min(hi, v));
      if (i % 2 === 0) g += `<rect x="0" y="${cy - row / 2}" width="${W}" height="${row}" fill="var(--raised)" opacity=".5"/>`;
      g += `<text x="8" y="${cy + 4}" style="font-family:var(--sans);font-size:12px;fill:${head ? "var(--ink)" : "var(--ink-2)"};font-weight:${head ? 500 : 400}">${C.esc(narrow ? name.slice(0, 26) + (name.length > 26 ? "…" : "") : name)}</text>`;
      if (!narrow) g += `<text x="${P.l - 12}" y="${cy + 4}" text-anchor="end">${r.protocol}</text>`;
      if (!base) {
        g += `<line x1="${x(clip(r.dRMSE_lo))}" x2="${x(clip(r.dRMSE_hi))}" y1="${cy}" y2="${cy}" stroke="${r.picked_in_advance ? "var(--accent)" : "var(--ink-3)"}" stroke-width="2" stroke-linecap="round"/>`;
        const off = r.dRMSE_vs_B1 > hi;
        g += off ? `<path d="M${x(hi) - 6} ${cy - 5}L${x(hi)} ${cy}L${x(hi) - 6} ${cy + 5}" fill="none" stroke="var(--ink-3)" stroke-width="1.5"/>`
          : `<circle cx="${x(r.dRMSE_vs_B1)}" cy="${cy}" r="${r.picked_in_advance ? 5 : 4.5}" fill="${r.picked_in_advance ? "var(--accent)" : "var(--card)"}" stroke="${r.picked_in_advance ? "var(--card)" : "var(--ink-3)"}" stroke-width="1.5"/>`;
      } else g += `<circle cx="${x(0)}" cy="${cy}" r="4" fill="var(--ink-2)"/>`;
      g += `<text x="${W - 8}" y="${cy + 4}" text-anchor="end" style="fill:var(--ink-2)">${base ? "baseline" : C.pct(r.dRMSE_vs_B1, 0, true)}</text>`;
      g += `<rect x="0" y="${cy - row / 2}" width="${W}" height="${row}" fill="transparent" data-i="${i}"/>`;
    });
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("height", H); svg.innerHTML = g;
    svg.onmousemove = (e) => {
      const t = e.target.closest("[data-i]"); if (!t) return C.tip(null);
      const r = rows[+t.dataset.i];
      C.tip(C.tipRows(C.esc(NAME[r.model] || r.model), [["Round", r.iteration], ["Protocol", r.protocol], ["Picked in advance", r.picked_in_advance ? "Yes" : "No"],
        ["RMSE", C.usd(r.RMSE)], ["MAE", C.usd(r.MAE)], ["Δ RMSE vs B1", r.model === "B1 weekday mean" ? "–" : `${C.pct(r.dRMSE_vs_B1, 0, true)} (${C.pct(r.dRMSE_lo, 0, true)} to ${C.pct(r.dRMSE_hi, 0, true)})`],
        ["90% band caught", C.pct(r.cover90, 0)]]), e);
    };
    svg.onmouseleave = () => C.tip(null);
  }

  function tables(D) {
    const rows = D.vsB1.slice().sort((a, b) => a.RMSE - b.RMSE);
    $("#tab").innerHTML = `<thead><tr><th class="num">#</th><th>Model</th><th>Round</th><th>Protocol</th><th>In advance</th><th class="num">RMSE</th><th class="num">MAE</th>
      <th class="num">Δ RMSE vs B1, 95% CI</th><th class="num">Ordinary days</th><th class="num">Event days</th><th class="num">Bias / day</th><th class="num">90% band caught</th></tr></thead><tbody>
      ${rows.map((r, i) => `<tr class="${r.model === "EL event-type lift" ? "hl" : ""}"><td class="num">${i + 1}</td><td>${C.esc(NAME[r.model] || r.model)}</td><td>${C.esc(r.iteration)}</td><td>${r.protocol}</td>
        <td>${r.picked_in_advance ? '<span class="tag"><span class="dot accent"></span>Yes</span>' : '<span class="tag muted">No</span>'}</td>
        <td class="num">${C.usd(r.RMSE)}</td><td class="num">${C.usd(r.MAE)}</td>
        <td class="num">${r.model === "B1 weekday mean" ? "–" : `${C.pct(r.dRMSE_vs_B1, 0, true)} <span class="muted">(${C.pct(r.dRMSE_lo, 0, true)} to ${C.pct(r.dRMSE_hi, 0, true)})</span>`}</td>
        <td class="num">${C.usd(r.ordinary_RMSE)}</td><td class="num">${C.usd(r.event_RMSE)}</td><td class="num">${C.usd(r.bias, { plus: true })}</td>
        <td class="num">${C.pct(r.cover90, 0)}</td></tr>`).join("")}</tbody>`;
    $("#iters").innerHTML = ITERS.map(([h, t]) => `<li><span><strong>${h}.</strong> ${t}</span></li>`).join("");
    $("#noise").innerHTML = `<thead><tr><th>Fit</th><th class="num">Ordinary-day RMSE, Jan–Jun</th><th class="num">May–Jun</th></tr></thead><tbody>
      <tr><td>EL, frozen Apr 30 (the real forecast)</td><td class="num">–</td><td class="num">${C.usd(D.vsB1.find((r) => r.model === "EL event-type lift").ordinary_RMSE)}</td></tr>
      ${D.noiseFloor.map((r) => `<tr><td>${C.esc(r.fit.replace("Jan-Jun", "Jan–Jun"))}</td><td class="num">${C.usd(r.ordinary_RMSE_janjun)}</td><td class="num">${C.usd(r.ordinary_RMSE_mayjun)}</td></tr>`).join("")}</tbody>`;
    const p2 = D.phase2.filter((r) => r.target === "theo_usd").sort((a, b) => a.MAE - b.MAE);
    $("#p2").innerHTML = `<thead><tr><th>Model</th><th>Kind</th><th class="num">CV MAE, Jan–Apr</th><th class="num">Holdout MAE</th><th class="num">Bias / day</th><th class="num">Skill vs B1</th><th class="num">90% band caught</th></tr></thead><tbody>
      ${p2.map((r) => `<tr class="${r.cv_choice ? "hl" : ""}"><td>${C.esc(r.model)}${r.cv_choice ? '<span class="sub">Cross-validation pick</span>' : ""}</td><td>${r.stack}</td>
        <td class="num">${C.usd(r.cv_mae_janapr)}</td><td class="num">${C.usd(r.MAE)}</td><td class="num">${C.usd(r.bias, { plus: true })}</td>
        <td class="num">${r.skill_vs_B1 == null ? (r.model.startsWith("B1") ? "–" : C.pct(1 - r.MAE / p2.find((x) => x.model.startsWith("B1")).MAE, 0, true)) : C.pct(r.skill_vs_B1, 0, true)}</td>
        <td class="num">${C.pct(r.coverage, 0)}</td></tr>`).join("")}</tbody>`;
    $("#mm").innerHTML = `<thead><tr><th>Model</th><th class="num">MAE, $ per hour</th></tr></thead><tbody>
      <tr><td>Zone average (Z0)</td><td class="num">$53.1</td></tr>
      <tr><td>Machine's own Jan–Apr average (M0)</td><td class="num">$46.7</td></tr>
      <tr class="hl"><td>GLM: bank + game + calendar + closure</td><td class="num">$38.2</td></tr>
      <tr><td>GLM + shrunk machine effect</td><td class="num">$38.2</td></tr>
      <tr><td>LightGBM: location, game, calendar</td><td class="num">$39.7</td></tr></tbody>`;
    $("#iv").innerHTML = `<thead><tr><th>Estimator</th><th class="num">Caught the truth (target 90%)</th><th class="num">False flags (target ≤ 10%)</th><th class="num">Detects −15% / +10%</th></tr></thead><tbody>
      <tr><td>Zone on–off, calibrated</td><td class="num">97%</td><td class="num">3%</td><td class="num">99% / 83%</td></tr>
      <tr><td>Machine diff-in-diff, calibrated</td><td class="num">95%</td><td class="num">5%</td><td class="num">66% / 33%</td></tr>
      <tr><td class="muted">Zone on–off, raw placebo</td><td class="num muted">83–86%</td><td class="num muted">14%</td><td class="num muted">–</td></tr>
      <tr><td class="muted">Machine diff-in-diff, raw placebo</td><td class="num muted">85%</td><td class="num muted">15%</td><td class="num muted">–</td></tr></tbody>`;
  }
})();
