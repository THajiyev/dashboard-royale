/* Comps page (Q5): cost and reinvestment, the May 1 points-price change by tier, tier growth,
   before/after redemption behaviour, unspent points, and the test that would settle it. */
(function () {
  "use strict";
  const C = window.Core, $ = C.$;
  const COL = { Base: "--div-pos", Gold: "--accent", Platinum: "--seq-3" };
  const S = { a: 0, b: 5 };
  let D;

  document.addEventListener("DOMContentLoaded", async () => {
    try { D = await C.load("comps"); } catch (e) { return C.fail($("#main"), e); }
    [S.a, S.b] = C.periodControl($("#period"), (a, b) => { S.a = a; S.b = b; render(); });
    render(); tables();
    addEventListener("resize", drawPrice); addEventListener("themechange", drawPrice);
  });

  const sum = (arr, k) => arr.reduce((t, x) => t + x[k], 0);
  function render() {
    $("#title").textContent = `Comps, ${C.periodLabel(S.a, S.b)}`;
    const M = D.months.slice(S.a, S.b + 1), first = D.months[S.a], last = D.months[S.b];
    const cost = sum(M, "cost"), face = sum(M, "face"), theo = sum(M, "theo");
    const pre = D.months.slice(0, 4), post = D.months.slice(4);
    const reinPre = sum(pre, "cost") / sum(pre, "theo"), reinPost = sum(post, "cost") / sum(post, "theo");
    const perMonth = (a, b) => D.months.slice(a, b + 1).reduce((t, m) => t + m.cost, 0) / (b - a + 1);
    const redPost = (D.may1.cohorts.redeemer.theo[4] + D.may1.cohorts.redeemer.theo[5]) / 2;
    $("#stats").innerHTML = [
      ["Comp cost", C.usd(cost, { short: true }), `${C.usd(face, { short: true })} at menu prices, ${C.int(sum(M, "redemptions"))} redemptions`],
      ["What changed on May 1", `${C.num(D.months[3].tiers.Base.ppd, 0)} → ${C.num(D.months[4].tiers.Base.ppd, 0)} points`, `per $1 of comps: every comp now costs about half the points, at every tier`],
      ["What the change cost", C.pct(perMonth(4, 5) / perMonth(0, 3) - 1, 0, true), `${C.usd(perMonth(4, 5) - perMonth(0, 3), { short: true })} a month more than Jan–Apr`],
      ["What it bought", "No extra play", `Comp users played ${C.pct(Math.abs(redPost - 1), 1)} less than in Mar–Apr`],
    ].map(([l, v, f], i) => `<div class="stat"><div class="label">${l}</div><div class="value${i === 1 ? " accent" : ""}">${v}</div><div class="foot">${f}</div></div>`).join("");
    drawPrice();
  }

  function drawPrice() {
    if (!D) return;
    const svg = $("#price"), W = svg.clientWidth || 900, H = 300, P = { l: 40, r: W >= 560 ? 80 : 12, t: 16, b: 28 };
    const ms = ["2025-01", "2025-02", "2025-03", "2025-04", "2025-05", "2025-06"];
    const days = D.daily.filter((r) => { const i = ms.indexOf(r.d.slice(0, 7)); return i >= S.a && i <= S.b; });
    const x = C.scale(0, Math.max(1, days.length - 1), P.l, W - P.r), y = C.scale(0, 16, H - P.b, P.t);
    let g = "";
    for (let t = 0; t <= 16; t += 4) g += `<line x1="${P.l}" x2="${W - P.r}" y1="${y(t)}" y2="${y(t)}" stroke="var(--grid)"/><text x="${P.l - 8}" y="${y(t) + 4}" text-anchor="end">${t}</text>`;
    days.forEach((r, i) => { if (r.d.endsWith("-01")) g += `<text x="${x(i)}" y="${H - 8}">${C.date(r.d, { month: "short" })}</text>`; });
    const ci = days.findIndex((r) => r.d === "2025-05-01");
    if (ci > 0) g += `<line x1="${x(ci) - (x(1) - x(0)) / 2}" x2="${x(ci) - (x(1) - x(0)) / 2}" y1="${P.t}" y2="${H - P.b}" stroke="var(--ink-3)" stroke-dasharray="3 3"/>
      <text x="${x(ci) + 6}" y="${P.t + 10}" style="fill:var(--ink-2)">${W < 560 ? "May 1: −53%" : "May 1: −53% at every tier"}</text>`;
    for (const tr of D.tiers) {
      const pts = days.map((r, i) => (r[tr] == null ? null : [x(i), y(r[tr])]));
      let d = "", pen = false;
      pts.forEach((p) => { if (!p) { pen = false; return; } d += `${pen ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`; pen = true; });
      g += `<path d="${d}" fill="none" stroke="var(${COL[tr]})" stroke-width="2" stroke-linejoin="round"/>`;
      const lastP = [...pts].reverse().find(Boolean);
      if (lastP && W >= 560) g += `<text x="${lastP[0] + 8}" y="${lastP[1] + 4}" style="fill:var(--ink)">${tr}</text>`;
    }
    g += `<line id="pr-x" y1="${P.t}" y2="${H - P.b}" stroke="var(--ink-3)" opacity="0"/>`;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.innerHTML = g;
    $("#price-legend").innerHTML = D.tiers.map((tr) => `<span><i style="background:var(${COL[tr]})"></i>${tr}</span>`).join("");
    svg.onmousemove = (e) => {
      const rc = svg.getBoundingClientRect(), px = ((e.clientX - rc.left) / rc.width) * W;
      const i = Math.max(0, Math.min(days.length - 1, Math.round(((px - P.l) / (W - P.l - P.r)) * (days.length - 1)))), r = days[i];
      const ln = $("#pr-x"); ln.setAttribute("x1", x(i)); ln.setAttribute("x2", x(i)); ln.setAttribute("opacity", 0.5);
      C.tip(C.tipRows(C.date(r.d, { weekday: "short", month: "short", day: "numeric" }),
        [...D.tiers.map((tr) => [`${tr}, points per $1`, r[tr] == null ? "–" : C.num(r[tr], 2)]), ["Redemptions", C.int(r.n)], ["Comp cost", C.usd(r.cost)]]), e);
    };
    svg.onmouseleave = () => { C.tip(null); $("#pr-x")?.setAttribute("opacity", 0); };
  }

  function tables() {
    const B = D.beforeAfter.before, A = D.beforeAfter.after;
    const row = (name, b, a, f) => `<tr><td>${name}</td><td class="num">${f(b)}</td><td class="num">${f(a)}</td><td class="num">${C.pct(a / b - 1, 0, true)}</td></tr>`;
    $("#ba").innerHTML = `<thead><tr><th></th><th class="num">Jan 1 – Apr 30</th><th class="num">May 1 – Jun 30</th><th class="num">Change</th></tr></thead><tbody>
      ${row("Redemptions per day", B.perDay, A.perDay, (v) => C.num(v, 0))}
      ${row("Menu value per redemption", B.face, A.face, (v) => C.usd(v, { d: 2 }))}
      ${row("Real cost per redemption", B.cost, A.cost, (v) => C.usd(v, { d: 2 }))}
      ${row("Points per redemption", B.pts, A.pts, (v) => C.int(v))}</tbody>`;

    const earned = sum(D.months, "ptsEarned"), spent = sum(D.months, "ptsRedeemed"), unspent = earned - spent;
    const pBefore = D.months[3].tiers.Base.ppd, pAfter = D.months[4].tiers.Base.ppd;
    $("#liab").innerHTML = `Card holders earned <span class="mono">${(earned / 1e6).toFixed(0)}M</span> points this half and spent
      <span class="mono">${(spent / 1e6).toFixed(1)}M</span>. The <span class="mono">${(unspent / 1e6).toFixed(0)}M</span> left over would buy
      <span class="mono">${C.usd(unspent / pBefore, { short: true })}</span> of comps at January's Base price and
      <span class="mono">${C.usd(unspent / pAfter, { short: true })}</span> at today's, about <span class="mono">${C.usd((unspent / pAfter) * D.costRatio, { short: true })}</span> in real cost.
      Balances start at 0 each year, so whatever isn't spent by Dec 31 expires; at today's 2.5% spend rate most of it will. The risk is a
      jump in redemptions before year end, not a bill that already exists.`;

    // ---- May 1 investigation
    const Y = D.may1, R = Y.rule, fb = Y.fnb, fpre = fb.slice(2, 4), fpost = fb.slice(4);
    const avg = (arr, k) => arr.reduce((t, x) => t + x[k], 0) / arr.length;
    const ev = [
      ["One rule explains every redemption.", `Points = menu price × base rate × tier multiplier, rounded up. All ${C.int(R.n)} redemptions match it: ${C.int(R.old)} at a base rate of 15, ${C.int(R.new)} at 7, ${R.neither} at anything else.`],
      ["Only the base rate moved.", "Gold still pays 80% of the Base price and Platinum 60%. Menu prices for all ten items are unchanged."],
      ["It switched at the gaming-day boundary.", `Last old-price redemption ${C.date(R.lastOld.slice(0, 10))} at ${R.lastOld.slice(11)}, first new one at ${R.firstNew.slice(11)}: a scheduled setting change, not drift.`],
      ["Earning didn't change.", `${Y.earnPerDollar.before.toFixed(2)} points per dollar wagered before, ${Y.earnPerDollar.after.toFixed(2)} after.`],
      ["Comps didn't replace cash sales.", `Card holders' paid food and drink transactions went from ${C.int(avg(fpre, "cardedPaidTx"))} to ${C.int(avg(fpost, "cardedPaidTx"))} a month (${C.pct(avg(fpost, "cardedPaidTx") / avg(fpre, "cardedPaidTx") - 1, 0, true)}, Mar–Apr to May–Jun), a smaller drop than uncarded guests' cash sales (${C.pct(avg(fpost, "uncardedCash") / avg(fpre, "uncardedCash") - 1, 0, true)}). Cheaper comps would have pushed card holders down further, not less.`],
      ["Nothing announced it.", "No promotion or event in the calendar starts on May 1."],
    ];
    $("#may-ev").innerHTML = ev.map(([h, t]) => `<li><span><strong>${h}</strong> ${t}</span></li>`).join("");
    const co = Y.cohorts;
    const coRow = (name, c) => `<tr><td>${name}<span class="sub">${C.int(c.players)} players</span></td>${c.theo.map((v, i) =>
      `<td class="num${i >= 4 ? "" : " muted"}">${C.num(v * 100, 0)}</td>`).join("")}<td class="num">${C.pct((c.theo[4] + c.theo[5]) / 2 - 1, 1, true)}</td></tr>`;
    $("#may-co").innerHTML = `<thead><tr><th>Locals</th>${C.MONTHS.map((m) => `<th class="num">${m}</th>`).join("")}<th class="num">May–Jun vs Mar–Apr</th></tr></thead><tbody>
      ${coRow("Used comps before May", co.redeemer)}${coRow("Didn't", co.other)}</tbody>`;
    $("#may-co-note").textContent = `The guests most exposed to cheaper comps played ${C.pct(Math.abs((co.redeemer.theo[4] + co.redeemer.theo[5]) / 2 - 1), 1)} less after the cut, not more. `
      + `The smaller group that never used comps rose, which points away from the cut. This isn't a controlled comparison: the groups differ, and only ${C.pct(Y.visitorsReturn, 1)} of visitors play in more than one month.`;

    const T0 = D.months[0].tiers, T5 = D.months[5].tiers, pre = D.months.slice(0, 4), post = D.months.slice(4);
    const rein = (arr, tr) => { const c = arr.reduce((t, m) => t + m.tiers[tr].cost, 0), th = arr.reduce((t, m) => t + m.tiers[tr].theo, 0); return c / th; };
    $("#tiers").innerHTML = `<thead><tr><th>Tier</th><th class="num">Members Jan</th><th class="num">Members Jun</th><th class="num">Points per $1<span class="sub">before → after</span></th><th class="num">Reinvestment<span class="sub">Jan–Apr → May–Jun</span></th></tr></thead><tbody>
      ${D.tiers.map((tr) => `<tr><td><span class="tag"><span class="dot" style="background:var(${COL[tr]})"></span>${tr}</span></td>
        <td class="num">${C.int(T0[tr].members)}</td><td class="num">${C.int(T5[tr].members)}</td>
        <td class="num">${C.num(D.months[3].tiers[tr].ppd, 1)} → ${C.num(D.months[4].tiers[tr].ppd, 1)}</td>
        <td class="num">${C.pct(rein(pre, tr), 2)} → ${C.pct(rein(post, tr), 2)}</td></tr>`).join("")}</tbody>`;

    $("#months").innerHTML = `<thead><tr><th>Month</th><th class="num">Redemptions</th><th class="num">Redeeming players</th><th class="num">Menu value</th><th class="num">Real cost</th>
      <th class="num">Reinvestment</th><th class="num">Points earned</th><th class="num">Points spent</th><th class="num">Spent ÷ earned</th></tr></thead><tbody>
      ${D.months.map((m) => `<tr class="${m.m === 4 ? "hl" : ""}"><td>${C.MONTHS[m.m]}${m.m === 4 ? '<span class="sub">new prices</span>' : ""}</td>
        <td class="num">${C.int(m.redemptions)}</td><td class="num">${C.int(m.redeemers)}</td><td class="num">${C.usd(m.face)}</td><td class="num">${C.usd(m.cost)}</td>
        <td class="num">${C.pct(m.cost / m.theo, 2)}</td><td class="num">${(m.ptsEarned / 1e6).toFixed(1)}M</td><td class="num">${(m.ptsRedeemed / 1e6).toFixed(2)}M</td>
        <td class="num">${C.pct(m.ptsRedeemed / m.ptsEarned, 1)}</td></tr>`).join("")}</tbody>`;

    const KNOW = [
      ["Cost.", `${C.usd(sum(D.months, "cost"), { short: true })} in real cost over six months, ${C.pct(sum(D.months, "cost") / sum(D.months, "theo"), 2)} of tracked theo. A comp costs the casino about ${C.pct(D.costRatio, 0)} of its menu price.`],
      ["What changed.", "On May 1 the points needed per comp dollar went from 15 to 7, at every tier. Menu prices and earning stayed the same."],
      ["What the change cost.", "About $2,900 a month more than Jan–Apr (+9%). Redemptions rose about 6%; the share of locals who redeem didn't move."],
      ["What it bought.", "Nothing visible. Locals who already used comps played 2.5% less in May–Jun than in Mar–Apr; locals overall, 1.2% less."],
      ["What to do about it.", "Run the $4,000 pilot in August: half of card holders back on the old prices. If play holds, restore the old rate and save about $35K a year."],
    ];
    $("#know").innerHTML = KNOW.map(([h, t]) => `<li><span><strong>${h}</strong> ${t}</span></li>`).join("");
  }
})();
