/* Streaks page: is any player "due"? Next-visit results by streak against shuffled order, half-against-half luck,
   cumulative position, swing size and the house edge, return visits after bad luck, and the tests behind it. */
(function () {
  "use strict";
  const C = window.Core, $ = C.$;

  C.registerPage("streaks.html", async () => {
    let D;
    try { D = await C.load("streaks"); } catch (e) { return C.fail($("#main"), e); }
    if (!C.pageActive()) return;
    const draw = () => { streakChart(D); halvesChart(D); swingChart(D); edgeChart(D); };
    stats(D); draw(); tables(D); why(D); tests(D);
    C.listen(window, "resize", draw); C.listen(window, "themechange", draw);
  });

  const pt = (v, d = 1) => `${C.num(v * 100, d, true)} pts`;
  const line = (pts) => pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join("");
  const yAxis = (ticks, y, x0, x1, fmt, zero) => ticks.map((t) =>
    `<line x1="${x0}" x2="${x1}" y1="${y(t)}" y2="${y(t)}" stroke="${zero != null && Math.abs(t - zero) < 1e-9 ? "var(--ink-3)" : "var(--grid)"}"/>` +
    `<text x="${x0 - 8}" y="${y(t) + 4}" text-anchor="end">${fmt(t)}</text>`).join("");
  const dot = (cx, cy, lo, hi, cls = "var(--accent)") =>
    `<line x1="${cx}" x2="${cx}" y1="${lo}" y2="${hi}" stroke="${cls}" stroke-width="1.5"/>` +
    `<circle cx="${cx}" cy="${cy}" r="4" fill="${cls}" stroke="var(--card)" stroke-width="1.5"/>`;
  const hover = (svg, rows, html) => {
    svg.onmousemove = (e) => { const t = e.target.closest("[data-k]"); if (!t) return C.tip(null); C.tip(html(rows[+t.dataset.k]), e); };
    svg.onmouseleave = () => C.tip(null);
  };

  function stats(D) {
    const n = D.next, h = D.halves, s = D.swing;
    $("#stats").innerHTML = [
      ["Next visit ended ahead, after a losing visit", C.pct(n.after_loss, 1), `${C.pct(n.after_win, 1)} after a winning one`],
      ["Jan–Mar luck against Apr–Jun luck", `ρ ${C.num(h.rho, 2, true)}`, `${C.int(h.players)} players in both halves; 0 means no link`],
      ["Visits tested", C.int(D.visits), `${C.int(D.players)} carded players, Jan–Jun 2025`],
      ["Swing size, Jan–Mar to Apr–Jun", `ρ ${C.num(s.rho_size, 2)}`, "how hard they play predicts how big the result is, not its sign"],
    ].map(([l, v, f], i) => `<div class="stat"><div class="label">${l}</div><div class="value${i === 0 ? " accent" : ""}">${v}</div><div class="foot">${f}</div></div>`).join("");
  }

  function streakChart(D) {
    const svg = $("#st"), rows = D.streaks, W = svg.clientWidth || 900, H = 300, P = { l: 48, r: 16, t: 16, b: 52 };
    const pos = rows.map((r, i) => i + (r.streak > 0 ? 0.7 : 0));
    const x = C.scale(-0.6, pos[pos.length - 1] + 0.6, P.l, W - P.r), unit = x(1) - x(0);
    const lo = Math.min(...rows.flatMap((r) => [r.lo, r.shuf_lo])), hi = Math.max(...rows.flatMap((r) => [r.hi, r.shuf_hi]));
    const y0 = Math.floor(lo * 100 - 0.5) / 100, y1 = Math.ceil(hi * 100 + 0.5) / 100;
    const y = C.scale(y0, y1, H - P.b, P.t);
    let g = yAxis(C.ticks(y0, y1, 4), y, P.l, W - P.r, (t) => C.pct(t, 0));
    g += `<line x1="${P.l}" x2="${W - P.r}" y1="${y(D.ahead_rate)}" y2="${y(D.ahead_rate)}" stroke="var(--ink-3)" stroke-dasharray="3 3"/>`;
    $("#st-all").textContent = `All visits, ${C.pct(D.ahead_rate, 1)}`;
    rows.forEach((r, i) => {
      const cx = x(pos[i]), bw = Math.min(36, unit * 0.55);
      g += `<rect x="${cx - bw / 2}" y="${y(r.shuf_hi)}" width="${bw}" height="${Math.max(1, y(r.shuf_lo) - y(r.shuf_hi))}" rx="3" fill="var(--band)" stroke="var(--line-2)"/>`;
      g += `<line x1="${cx - bw / 2}" x2="${cx + bw / 2}" y1="${y(r.shuf)}" y2="${y(r.shuf)}" stroke="var(--series-base)"/>`;
      g += dot(cx, y(r.ahead), y(r.lo), y(r.hi));
      const k = Math.abs(r.streak), last = r.streak === -6 || r.streak === 3;
      g += `<text x="${cx}" y="${H - P.b + 18}" text-anchor="middle">${k}${last ? "+" : ""}</text>`;
      g += `<rect x="${cx - unit / 2}" y="${P.t}" width="${unit}" height="${H - P.b - P.t}" fill="transparent" data-k="${i}"/>`;
    });
    const nl = rows.filter((r) => r.streak < 0).length;
    const mid = (a, b) => (x(pos[a]) + x(pos[b])) / 2;
    g += `<text x="${mid(0, nl - 1)}" y="${H - 10}" text-anchor="middle" style="fill:var(--ink-2)">Losing visits in a row going in</text>`;
    g += `<text x="${mid(nl, rows.length - 1)}" y="${H - 10}" text-anchor="middle" style="fill:var(--ink-2)">Winning visits in a row</text>`;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.innerHTML = g;
    hover(svg, rows, (r) => C.tipRows(`${Math.abs(r.streak)}${r.streak === -6 || r.streak === 3 ? " or more" : ""} ${r.streak < 0 ? "losing" : "winning"} visit${Math.abs(r.streak) === 1 ? "" : "s"} in a row`, [
      ["Next visit ended ahead", C.pct(r.ahead, 1)], ["95% interval", `${C.pct(r.lo, 1)} to ${C.pct(r.hi, 1)}`],
      ["Random order", `${C.pct(r.shuf, 1)} (${C.pct(r.shuf_lo, 1)} to ${C.pct(r.shuf_hi, 1)})`], ["Visits", C.int(r.n)]]));
    C.dataTable(svg, "st-table", "Next-visit outcomes by preceding streak, with shuffled comparison", ["Prior streak", "Ahead next visit", "95% low", "95% high",
      "Shuffled", "Shuffled 95% low", "Shuffled 95% high", "Visit pairs"],
      rows.map((r) => [`${Math.abs(r.streak)}${r.streak === -6 || r.streak === 3 ? "+" : ""} ${r.streak < 0 ? "losses" : "wins"}`,
        C.pct(r.ahead, 1), C.pct(r.lo, 1), C.pct(r.hi, 1), C.pct(r.shuf, 1), C.pct(r.shuf_lo, 1), C.pct(r.shuf_hi, 1), C.int(r.n)])
        .concat([["All visits", C.pct(D.ahead_rate, 1), "—", "—", "—", "—", "—", C.int(D.visits)]]));
    const n = D.next;
    $("#st-note").innerHTML = `After a losing visit, <span class="mono">${C.pct(n.after_loss, 1)}</span> of next visits ended ahead; after a winning one,
      <span class="mono">${C.pct(n.after_win, 1)}</span>. With the same visits in random order that gap stays between
      <span class="mono">${pt(n.shuf_lo)}</span> and <span class="mono">${pt(n.shuf_hi)}</span>. The real <span class="mono">${pt(n.after_loss_minus_after_win)}</span>
      is just outside, but it's small and points the wrong way for "due": losing is followed by slightly more losing, probably because a player's
      own play changes from trip to trip. ${C.int(n.pairs)} pairs of consecutive visits; ${D.n_shuffles} shuffles.`;
  }

  function halvesChart(D) {
    const svg = $("#hv"), h = D.halves, rows = h.deciles, W = svg.clientWidth || 600, H = 300, P = { l: 44, r: 12, t: 12, b: 40 };
    const xs = rows.map((r) => r.z1), x0 = Math.floor(Math.min(...xs) * 2 - 0.5) / 2, x1 = Math.ceil(Math.max(...xs) * 2 + 0.5) / 2;
    const yv = rows.flatMap((r) => [r.z2_lo, r.z2_hi]), y0 = Math.min(-1, Math.floor(Math.min(...yv) * 2) / 2), y1 = Math.max(1, Math.ceil(Math.max(...yv) * 2) / 2);
    const x = C.scale(x0, x1, P.l, W - P.r), y = C.scale(y0, y1, H - P.b, P.t);
    let g = yAxis(C.ticks(y0, y1, 4), y, P.l, W - P.r, (t) => C.num(t, 1, true));
    C.ticks(x0, x1, 5).forEach((t) => { g += `<text x="${x(t)}" y="${H - P.b + 16}" text-anchor="middle">${C.num(t, 1, true)}</text>`; });
    g += `<text x="${(P.l + W - P.r) / 2}" y="${H - 6}" text-anchor="middle" style="fill:var(--ink-2)">Jan–Mar luck, standard deviations</text>`;
    // evening out: Apr–Jun luck the mirror of Jan–Mar, clipped to the plot
    const a = Math.max(x0, -y1), b = Math.min(x1, -y0);
    g += `<path d="${line([[x(a), y(-a)], [x(b), y(-b)]])}" stroke="var(--series-base)" stroke-width="1.5" stroke-dasharray="5 4" fill="none"/>`;
    const N = rows.reduce((t, r) => t + r.n, 0), avg = rows.reduce((t, r) => t + r.n * r.z2, 0) / N;
    g += `<line x1="${P.l}" x2="${W - P.r}" y1="${y(avg)}" y2="${y(avg)}" stroke="var(--ink-3)" stroke-width="1.5"/>`;
    rows.forEach((r, i) => {
      g += dot(x(r.z1), y(r.z2), y(Math.min(y1, r.z2_lo)), y(Math.min(y1, r.z2_hi)));
      g += `<circle cx="${x(r.z1)}" cy="${y(r.z2)}" r="12" fill="transparent" data-k="${i}"/>`;
    });
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.innerHTML = g;
    hover(svg, rows, (r) => C.tipRows(`Tenth ${r.decile} by Jan–Mar luck`, [
      ["Jan–Mar luck (average)", C.num(r.z1, 2, true)], ["Apr–Jun luck (average)", C.num(r.z2, 2, true)],
      ["95% interval", `${C.num(r.z2_lo, 2, true)} to ${C.num(r.z2_hi, 2, true)}`], ["Apr–Jun luck (median)", C.num(r.z2_median, 2, true)],
      ["Ended Apr–Jun ahead", C.pct(r.ahead2, 1)], ["Players", C.int(r.n)]]));
    C.dataTable(svg, "hv-table", "Average and median luck by Jan–Mar luck tenth", ["Tenth", "Jan–Mar average z", "Apr–Jun average z",
      "95% low", "95% high", "Apr–Jun median z", "Ended ahead", "Players"],
      rows.map((r) => [r.decile, C.num(r.z1, 2, true), C.num(r.z2, 2, true), C.num(r.z2_lo, 2, true), C.num(r.z2_hi, 2, true),
        C.num(r.z2_median, 2, true), C.pct(r.ahead2, 1), C.int(r.n)]));
    const meds = rows.map((r) => r.z2_median);
    $("#hv-note").innerHTML = `Slope <span class="mono">${C.num(h.slope, 3, true)}</span> (95% CI <span class="mono">${C.num(h.slope_lo, 3, true)}</span> to
      <span class="mono">${C.num(h.slope_hi, 3, true)}</span>); evening out would be <span class="mono">−1</span>. The unluckiest tenth's high average
      comes from a few jackpots: its median was <span class="mono">${C.num(rows[0].z2_median, 2, true)}</span>, and every tenth's median sat between
      <span class="mono">${C.num(Math.min(...meds), 2, true)}</span> and <span class="mono">${C.num(Math.max(...meds), 2, true)}</span>. The flat line is the
      average of all ${C.int(h.players)} players, a little above zero across the whole floor.`;
  }

  function swingChart(D) {
    const svg = $("#sw"), rows = D.swing.deciles, W = svg.clientWidth || 600, H = 280, P = { l: 52, r: 12, t: 12, b: 40 };
    const x = C.scale(0.5, rows.length + 0.5, P.l, W - P.r), unit = x(1) - x(0);
    const top = C.niceMax(Math.max(...rows.map((r) => r.abs_luck2_p90)));
    const y = C.scale(0, top, H - P.b, P.t);
    let g = yAxis(C.ticks(0, top, 4), y, P.l, W - P.r, (t) => C.usd(t), 0);
    rows.forEach((r, i) => {
      const cx = x(r.decile), bw = unit * 0.6;
      g += `<rect x="${cx - bw / 2}" y="${y(r.abs_luck2_med)}" width="${bw}" height="${y(0) - y(r.abs_luck2_med)}" rx="2" fill="var(--series-base)"/>`;
      g += `<line x1="${cx - bw / 2}" x2="${cx + bw / 2}" y1="${y(r.abs_luck2_p90)}" y2="${y(r.abs_luck2_p90)}" stroke="var(--ink)" stroke-width="2"/>`;
      g += `<line x1="${cx}" x2="${cx}" y1="${y(r.abs_luck2_med)}" y2="${y(r.abs_luck2_p90)}" stroke="var(--ink-3)"/>`;
      g += `<text x="${cx}" y="${H - P.b + 16}" text-anchor="middle">${r.decile}</text>`;
      g += `<rect x="${cx - unit / 2}" y="${P.t}" width="${unit}" height="${H - P.b - P.t}" fill="transparent" data-k="${i}"/>`;
    });
    g += `<text x="${(P.l + W - P.r) / 2}" y="${H - 6}" text-anchor="middle" style="fill:var(--ink-2)">Tenth by Jan–Mar swing size (1 = lightest play)</text>`;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.innerHTML = g;
    hover(svg, rows, (r) => C.tipRows(`Tenth ${r.decile} by swing size`, [
      ["Jan–Mar swing (1 sd, median)", C.usd(r.sd1)], ["Apr–Jun luck size, median", C.usd(r.abs_luck2_med)],
      ["Apr–Jun luck size, 90th percentile", C.usd(r.abs_luck2_p90)], ["Players", C.int(r.n)]]));
    C.dataTable(svg, "sw-table", "Luck swing size by Jan–Mar swing-size tenth", ["Tenth", "Jan–Mar swing, median SD", "Apr–Jun absolute luck, median",
      "Apr–Jun absolute luck, 90th percentile", "Players"],
      rows.map((r) => [r.decile, C.num(r.sd1, 2), C.usd(r.abs_luck2_med), C.usd(r.abs_luck2_p90), C.int(r.n)]));
    const a = rows[0], b = rows[rows.length - 1];
    $("#sw-note").innerHTML = `Rank correlation <span class="mono">${C.num(D.swing.rho_size, 2)}</span> between Jan–Mar swing size and the size of Apr–Jun luck,
      out of sample. The heaviest tenth's typical swing was <span class="mono">${C.usd(b.abs_luck2_med)}</span> against <span class="mono">${C.usd(a.abs_luck2_med)}</span>
      for the lightest, and one in ten of them swung more than <span class="mono">${C.usd(b.abs_luck2_p90)}</span>. Swing size comes from bet size, time on device and
      game volatility, all visible before the visit.`;
  }

  function edgeChart(D) {
    const svg = $("#he"), rows = D.swing.deciles, W = svg.clientWidth || 600, H = 280, P = { l: 44, r: 12, t: 12, b: 40 };
    const x = C.scale(0.5, rows.length + 0.5, P.l, W - P.r), unit = x(1) - x(0);
    const top = Math.max(0.25, Math.ceil(Math.max(...rows.map((r) => r.ahead2)) * 20) / 20);
    const y = C.scale(0, top, H - P.b, P.t);
    let g = yAxis(C.ticks(0, top, 5), y, P.l, W - P.r, (t) => C.pct(t, 0), 0);
    g += `<path d="${line(rows.map((r) => [x(r.decile), y(r.ahead2)]))}" fill="none" stroke="var(--accent)" stroke-width="2" stroke-linejoin="round"/>`;
    rows.forEach((r, i) => {
      g += `<circle cx="${x(r.decile)}" cy="${y(r.ahead2)}" r="3.5" fill="var(--accent)" stroke="var(--card)" stroke-width="1.5"/>`;
      g += `<text x="${x(r.decile)}" y="${H - P.b + 16}" text-anchor="middle">${r.decile}</text>`;
      g += `<rect x="${x(r.decile) - unit / 2}" y="${P.t}" width="${unit}" height="${H - P.b - P.t}" fill="transparent" data-k="${i}"/>`;
    });
    g += `<text x="${(P.l + W - P.r) / 2}" y="${H - 6}" text-anchor="middle" style="fill:var(--ink-2)">Tenth by Jan–Mar swing size (1 = lightest play)</text>`;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.innerHTML = g;
    hover(svg, rows, (r) => C.tipRows(`Tenth ${r.decile} by swing size`, [
      ["Ended Apr–Jun ahead", C.pct(r.ahead2, 1)], ["Median Apr–Jun result", C.usd(r.net2_med, { plus: true })], ["Players", C.int(r.n)]]));
    C.dataTable(svg, "he-table", "Share ending ahead and median result by swing-size tenth", ["Tenth", "Ended Apr–Jun ahead", "Median Apr–Jun result", "Players"],
      rows.map((r) => [r.decile, C.pct(r.ahead2, 1), C.usd(r.net2_med, { plus: true }), C.int(r.n)]));
    const a = rows[0], b = rows[rows.length - 1];
    $("#he-note").innerHTML = `<span class="mono">${C.pct(a.ahead2, 1)}</span> of the lightest tenth ended Apr–Jun ahead, against
      <span class="mono">${C.pct(b.ahead2, 1)}</span> of the heaviest. Their median results were <span class="mono">${C.usd(a.net2_med, { plus: true })}</span> and
      <span class="mono">${C.usd(b.net2_med, { plus: true })}</span>. This is the only signal about direction in the data, and it is the house edge, not a streak.`;
  }

  function tables(D) {
    const B = D.behind, K = D.comeback;
    $("#bh").innerHTML = `<thead><tr><th>Going in</th><th class="num">Median position<span class="sub">luck so far</span></th>
      <th class="num">Next visit ended ahead<span class="sub">95% interval</span></th><th class="num">Next visit luck<span class="sub">sd, 95% interval</span></th></tr></thead><tbody>
      ${B.bands.map((r) => `<tr><td>${r.band}</td><td class="num">${C.usd(r.cum_med, { plus: true })}</td>
        <td class="num">${C.pct(r.ahead, 1)}<span class="sub">${C.pct(r.lo, 1)} to ${C.pct(r.hi, 1)}</span></td>
        <td class="num">${C.num(r.mean_z, 2, true)}<span class="sub">${C.num(r.mean_z_lo, 2, true)} to ${C.num(r.mean_z_hi, 2, true)}</span></td></tr>`).join("")}</tbody>`;
    $("#bh-note").innerHTML = `The intervals overlap for every fifth. Rank correlation between position going in and the next visit's luck:
      <span class="mono">ρ ${C.num(B.rho, 3, true)}</span> (p ${C.pfmt(B.p)}), over ${C.int(B.visits)} visits by ${C.int(B.players)} players.`;
    $("#cb").innerHTML = `<thead><tr><th>Visit's luck</th><th class="num">Median result</th><th class="num">Back within 30 days<span class="sub">95% interval</span></th><th class="num">Visits</th></tr></thead><tbody>
      ${K.bands.map((r) => `<tr><td>${r.band}</td><td class="num">${C.usd(r.net_med, { plus: true })}</td>
        <td class="num">${C.pct(r.back, 1)}<span class="sub">${C.pct(r.lo, 1)} to ${C.pct(r.hi, 1)}</span></td><td class="num">${C.int(r.n)}</td></tr>`).join("")}</tbody>`;
    const gw = K.gap_within_spend;
    $("#cb-note").innerHTML = `No clear effect. Players return about as often after their unluckiest visits as after their luckiest, and the small gap flips with spend:
      in the lightest-spending fifth of visits, an unlucky visit is followed by a return <span class="mono">${pt(gw[0])}</span> more often than a lucky one;
      in the heaviest, <span class="mono">${pt(-gw[gw.length - 1])}</span> less often. This is an association, not a measured effect of losing.
      A comp aimed at "players who just lost" would need a pilot with a control group to show it does anything.`;
  }

  function why(D) {
    const six = D.streaks.find((r) => r.streak === -6);
    const items = [
      ["Every spin is independent.", "Each game draws its outcome from a random number generator. It has no memory of the player, the session or the streak, so nothing builds up."],
      ["Theo is already the expected result.", "Luck is what's left after the house edge. It shrinks relative to play as a player plays more, by dilution, never by being paid back."],
      ["Down $800 or up $800, the next dollar is the same.", "Both players are expected to lose the house edge on their next bet. Where they stand doesn't change the odds."],
      ["Long losing streaks are normal.", `Only ${C.pct(D.ahead_rate, 0)} of visits end ahead, so runs of losing visits happen on their own: ${C.int(six.n)} visits came after six or more losses in a row.`],
      ["Use swing size, not 'due'.", "To see who could have a big night, rank by bet size, time on device and game volatility. To see who will end behind, look at volume. Neither tells you a winner is coming."],
    ];
    $("#why").innerHTML = items.map(([h, t]) => `<li><span><strong>${h}</strong> ${t}</span></li>`).join("");
  }

  function tests(D) {
    const n = D.next, h = D.halves, B = D.behind, s = D.swing;
    const rows = [
      ["Does a losing visit make the next one more likely to end ahead?", `Next-visit win share after a loss minus after a win, against ${D.n_shuffles} within-player shuffles`,
        `${pt(n.after_loss_minus_after_win, 2)}; random ${pt(n.shuf_lo, 2)} to ${pt(n.shuf_hi, 2)}`, null, "No. Slightly the reverse, and small"],
      ["Does Jan–Mar luck predict Apr–Jun luck?", `Spearman, ${C.int(h.players)} players in both halves`, `ρ = ${C.num(h.rho, 3, true)}`, h.p, "No"],
      ["Does bad luck even out?", "Least squares, Apr–Jun luck on Jan–Mar luck (sd units)", `slope ${C.num(h.slope, 3, true)} (${C.num(h.slope_lo, 3, true)} to ${C.num(h.slope_hi, 3, true)})`, null, "No. Evening out would be −1"],
      ["Does being behind predict the next visit?", `Spearman, cumulative luck going in against next visit's luck, ${C.int(B.visits)} visits`, `ρ = ${C.num(B.rho, 3, true)}`, B.p, "No"],
      ["Can swing size be predicted?", "Spearman, Jan–Mar sd against size of Apr–Jun luck", `ρ = ${C.num(s.rho_size, 2)}`, 0, "Yes"],
    ];
    $("#tests").innerHTML = `<thead><tr><th>Question</th><th>Test</th><th>Statistic</th><th class="num">p</th><th>Answer</th></tr></thead><tbody>
      ${rows.map(([q, t, st, p, v]) => `<tr><td>${q}</td><td class="muted">${t}</td><td class="mono">${st}</td><td class="num">${p == null ? "–" : C.pfmt(p)}</td><td class="verdict">${v}</td></tr>`).join("")}</tbody>`;
  }
})();
