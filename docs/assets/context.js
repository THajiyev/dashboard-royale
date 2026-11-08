/* Context page: walkway-closure event study, weather strip and effects,
   measured changes and events, LVCVA visitation, and data left out. */
(function () {
  "use strict";
  const C = window.Core, $ = C.$;
  const LEFT_OUT = [
    ["Actual weather as a forecast input", "Nobody knows the weather weeks ahead, and the source says not to use future actual weather as a feature. Tested as an upper bound only: a perfect weather forecast would have cut error by about 5%."],
    ["The revised LVCVA monthly series", "It is a retrospective, revised series, not knowable during 2025. Only the latest figure published by each forecast date was tested (iteration 4); it didn't help."],
    ["The 2023–24 seasonal pattern", "Tested in iteration 4 and made the forecast worse: June 2025's decline was a one-off tourism slowdown that earlier years didn't show."],
    ["LVCVA visitor survey", "It describes all Las Vegas visitors, not this casino's guests, so it can't stand in for them."],
    ["Missouri casino benchmarks", "A different market with different clientele. Useful as a sanity range for hold, not as an input."],
    ["Traffic counts as visitors", "Counters record entries, not unique guests, and seated players aren't counted. Offline hours are dropped, so traffic is shown per counted hour."],
    ["Player tables for machine verdicts", "Sessions only see carded play, so machine verdicts use the meters, which count everyone. Sessions split locals from visitors and give each player's luck and win-rate check."],
    ["Security incidents", "A report is a lead to inspect, not evidence. None of the machine verdicts rely on them."],
  ];
  const ZN = { "Z-B40": "Back Forty", "Z-ENT": "Main Entrance", "Z-PIT": "Center Pit", "Z-HTL": "Hotel Corridor", "Z-BAR": "Bar Row", "Z-GAR": "Garage Entrance", "Z-HL": "High-Limit Room" };
  const LABEL = (c) => c.replace(/^Citywide event: /, "").replace(/^Property promotion: /, "Promotion: ")
    .replace(/ \(([A-Z][a-z]{2}) (\d\d)–([A-Z][a-z]{2}) (\d\d)\)$/, "")
    .replace(/L-\d\d-\d \((Z-[A-Z0-9]+)\)/g, (_, z) => ZN[z] || z)
    .replace(/, (2025-\d\d-\d\d)$/, (_, d) => `, ${C.date(d)}`)
    .replace(/ \(G-[A-Z0-9]+\)/g, "");

  document.addEventListener("DOMContentLoaded", async () => {
    let X, Mo;
    try { [X, Mo] = await Promise.all([C.load("context"), C.load("models")]); }
    catch (e) { return C.fail($("#main"), e); }
    const draw = () => { closure(X); weather(X); };
    stats(X, Mo); draw(); tables(X, Mo);
    addEventListener("resize", draw); addEventListener("themechange", draw);
  });

  function stats(X, Mo) {
    const rain = X.weatherCheck.find((r) => r.series === "Locals");
    const sb = Mo.scorecard.find((r) => r.change.includes("Super Bowl"));
    const bank = Mo.scorecard.find((r) => r.change.startsWith("8 new machines"));
    const during = X.closureStudy.filter((r) => r.rel_week >= 0 && r.rel_week <= 4);
    const avgClosed = during.reduce((t, r) => t + r.effect_pct, 0) / during.length;
    $("#stats").innerHTML = [
      ["Back Forty while the walkway was shut", C.pct(avgClosed, 0, true), "coin-in per hour vs control zones, weeks 0–4"],
      ["Locals on a rain day", C.pct(rain.effect_rain, 0, true), `95% CI ${C.pct(rain.lo95_rain, 0, true)} to ${C.pct(rain.hi95_rain, 0, true)}, 4 rain days`],
      ["Super Bowl weekend", C.usd(sb.theo_usd_per_day, { short: true, plus: true }), "theo per day, the biggest event lift"],
      ["New Center Pit bank B-51", C.usd(bank.theo_usd_per_day, { short: true, plus: true }), "theo per day net of spillover, since Mar 24"],
    ].map(([l, v, f], i) => `<div class="stat"><div class="label">${l}</div><div class="value${i === 0 ? " accent" : ""}">${v}</div><div class="foot">${f}</div></div>`).join("");
  }

  function closure(X) {
    const svg = $("#closure"), rows = X.closureStudy, W = svg.clientWidth || 900, H = 300, P = { l: 48, r: 16, t: 16, b: 28 };
    const x = C.scale(rows[0].rel_week - 0.5, rows[rows.length - 1].rel_week + 0.5, P.l, W - P.r);
    const y = C.scale(-0.4, 0.1, H - P.b, P.t);
    let g = `<rect x="${x(-0.5)}" y="${P.t}" width="${x(4.5) - x(-0.5)}" height="${H - P.b - P.t}" fill="var(--event)"/>`;
    for (let k = 0; k <= 5; k++) { const v = Math.round((-0.4 + k * 0.1) * 10) / 10;
      g += `<line x1="${P.l}" x2="${W - P.r}" y1="${y(v)}" y2="${y(v)}" stroke="${v === 0 ? "var(--ink-3)" : "var(--grid)"}"/><text x="${P.l - 8}" y="${y(v) + 4}" text-anchor="end">${C.pct(v, 0, true)}</text>`; }
    const line = (pts) => pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join("");
    g += `<path d="${line(rows.map((r) => [x(r.rel_week), y(r.hi90_pct)]).concat(rows.slice().reverse().map((r) => [x(r.rel_week), y(r.lo90_pct)])))}Z" fill="var(--band)"/>`;
    g += `<path d="${line(rows.map((r) => [x(r.rel_week), y(r.effect_pct)]))}" fill="none" stroke="var(--accent)" stroke-width="2" stroke-linejoin="round"/>`;
    rows.forEach((r) => {
      g += `<circle cx="${x(r.rel_week)}" cy="${y(r.effect_pct)}" r="3.5" fill="var(--accent)" stroke="var(--card)" stroke-width="1.5"/>`;
      if (r.rel_week % 2 === 0) g += `<text x="${x(r.rel_week)}" y="${H - 8}" text-anchor="middle">${r.rel_week > 0 ? "+" + r.rel_week : r.rel_week < 0 ? "−" + -r.rel_week : 0}</text>`;
      g += `<rect x="${x(r.rel_week - 0.5)}" y="${P.t}" width="${x(1) - x(0)}" height="${H - P.b - P.t}" fill="transparent" data-w="${r.rel_week}"/>`;
    });
    g += `<text x="${x(2)}" y="${P.t + 14}" text-anchor="middle" style="fill:var(--ink-2)">Closed</text>`;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.innerHTML = g;
    svg.onmousemove = (e) => {
      const t = e.target.closest("[data-w]"); if (!t) return C.tip(null);
      const r = rows.find((q) => q.rel_week === +t.dataset.w);
      C.tip(C.tipRows(`Week ${r.rel_week > 0 ? "+" : ""}${r.rel_week}${r.rel_week >= 0 && r.rel_week <= 4 ? ", walkway closed" : ""}`,
        [["Back Forty vs controls", C.pct(r.effect_pct, 1, true)], ["90% interval", `${C.pct(r.lo90_pct, 1, true)} to ${C.pct(r.hi90_pct, 1, true)}`]]), e);
    };
    svg.onmouseleave = () => C.tip(null);
  }

  function weather(X) {
    const svg = $("#wx"), w = X.weather, W = svg.clientWidth || 600, H = 220, P = { l: 36, r: 36, t: 12, b: 24 };
    const x = C.scale(0, w.length - 1, P.l, W - P.r), y = C.scale(0, 45, H - P.b, P.t), yr = C.scale(0, 30, H - P.b, P.t + 60);
    let g = "";
    for (let t = 0; t <= 45; t += 15) g += `<line x1="${P.l}" x2="${W - P.r}" y1="${y(t)}" y2="${y(t)}" stroke="var(--grid)"/><text x="${P.l - 6}" y="${y(t) + 4}" text-anchor="end">${t}°</text>`;
    w.forEach((r, i) => {
      if (r.tmax_c >= 40) g += `<rect x="${x(i) - 1.5}" y="${P.t}" width="3" height="${H - P.b - P.t}" fill="var(--div-neg)" opacity=".18"/>`;
      if (r.prcp_mm > 0) g += `<rect x="${x(i) - 2}" y="${yr(r.prcp_mm)}" width="4" height="${yr(0) - yr(r.prcp_mm)}" rx="1" fill="var(--div-pos)" opacity="${r.prcp_mm > 1 ? 1 : 0.4}"><title>${C.date(r.source_date)}: ${r.prcp_mm} mm</title></rect>`;
      if (r.source_date.endsWith("-01")) g += `<text x="${x(i)}" y="${H - 6}">${C.date(r.source_date, { month: "short" })}</text>`;
    });
    g += `<path d="${w.map((r, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(r.tmax_c).toFixed(1)}`).join("")}" fill="none" stroke="var(--ink-3)" stroke-width="1.5"/>`;
    // one label per rain episode (consecutive days over 1 mm)
    let run = null;
    const flush = () => {
      if (!run) return;
      const top = Math.min(...run.map((i) => yr(w[i].prcp_mm)));
      const a = w[run[0]].source_date, b = w[run[run.length - 1]].source_date;
      const label = run.length > 1 ? `${C.date(a)}–${C.date(b, { day: "numeric" })}` : C.date(a);
      g += `<text x="${x(run[0]) - 4}" y="${top - 6}" text-anchor="end" style="fill:var(--ink-2)">${label}</text>`;
      run = null;
    };
    w.forEach((r, i) => { if (r.prcp_mm > 1) { (run ||= []).push(i); } else flush(); });
    flush();
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.innerHTML = g;
  }

  function tables(X, Mo) {
    const wc = X.weatherCheck;
    const heat = X.weatherRobust.find((r) => /40/.test(r.variant || "") && r.series === "total");
    const ci = (lo, hi) => `<span class="sub">${C.pct(lo, 1, true)} to ${C.pct(hi, 1, true)}</span>`;
    $("#weff").innerHTML = `<thead><tr><th>Series</th><th class="num">Day 10°C hotter than recent days</th><th class="num">Rain day</th></tr></thead><tbody>
      ${wc.map((r) => `<tr><td>${C.esc(r.series)}</td><td class="num">${C.pct(r.effect_plus10C, 1, true)}${ci(r.lo95_plus10C, r.hi95_plus10C)}</td>
        <td class="num">${C.pct(r.effect_rain, 1, true)}${ci(r.lo95_rain, r.hi95_rain)}</td></tr>`).join("")}
      ${heat ? `<tr><td>Floor, a day of 40°C or more</td><td class="num">${C.pct(heat.effect, 1, true)}${ci(heat.lo95, heat.hi95)}</td><td class="num muted">–</td></tr>` : ""}</tbody>`;
    const ev = Mo.scorecard;
    $("#ev").innerHTML = `<thead><tr><th>Change</th><th>Measured on</th><th class="num">Theo per day</th><th class="num">90% interval</th><th class="num">Days</th><th>Verdict</th></tr></thead><tbody>
      ${ev.map((r) => `<tr><td>${C.esc(LABEL(r.change))}</td><td class="small" style="color:var(--ink-2)">${C.esc(r.part)}</td>
        <td class="num">${C.usd(r.theo_usd_per_day, { plus: true })}</td>
        <td class="num">${r.lo90_usd_day == null ? "–" : `${C.usd(r.lo90_usd_day, { plus: true })} to ${C.usd(r.hi90_usd_day, { plus: true })}`}</td>
        <td class="num">${r.days ?? "–"}</td>
        <td><span class="tag"><span class="dot ${r.verdict === "Positive" ? "ok" : r.verdict === "Negative" ? "lead" : ""}"></span>${r.verdict}</span></td></tr>`).join("")}</tbody>`;
    $("#city").innerHTML = `<thead><tr><th>Month</th><th class="num">Visitors</th><th class="num">vs 2024</th><th class="num">Hotel occupancy</th><th class="num">Convention attendance</th></tr></thead><tbody>
      ${X.city.map((r) => `<tr><td>${C.date(r.month + "-15", { month: "short" })}</td><td class="num">${(r.visitor_volume / 1e6).toFixed(2)}M</td>
        <td class="num">${C.pct(r.visitor_yoy_ratio, 1, true)}</td><td class="num">${C.pct(r.hotel_occupancy_ratio, 0)}</td><td class="num">${C.int(r.convention_attendance)}</td></tr>`).join("")}</tbody>`;
    $("#out").innerHTML = LEFT_OUT.map(([h, t]) => `<li><span><strong>${h}.</strong> ${t}</span></li>`).join("");
  }
})();
