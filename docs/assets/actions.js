/* Actions page: budget builder over action_catalog, draft plan with evidence,
   effect sizes computed from the same data the other pages show. */
(function () {
  "use strict";
  const C = window.Core, $ = C.$;
  const HORIZON = 30, MAX_TYPES = 3;
  const DRAFT = { "A-INSPECT": 1, "A-PREVENTIVE": 1, "A-WAYFINDING": 1 };
  let CAT, M, F, Mo, plan, qty, facts;

  document.addEventListener("DOMContentLoaded", async () => {
    try { [Mo, M, F] = await Promise.all([C.load("models"), C.load("machines"), C.load("floor")]); }
    catch (e) { return C.fail($("#main"), e); }
    CAT = Mo.catalog.filter((a) => a.action_type_id !== "A-HOLD");
    plan = C.plan();
    qty = plan.actions || { ...DRAFT };
    const moves = plan.moveSummary?.n || 0;
    if (moves) qty["A-MOVE-MACHINE"] = moves; else delete qty["A-MOVE-MACHINE"];
    facts = computeFacts();
    $("#reset").onclick = () => { qty = { ...DRAFT }; if (moves) qty["A-MOVE-MACHINE"] = moves; save(); render(); };
    render();
  });

  const cost = (a, n) => (n * (a.unit_cost_cents + a.recurring_cost_cents_per_day * Math.max(0, HORIZON - a.lead_days))) / 100;
  const act = (id) => CAT.find((a) => a.action_type_id === id);
  const save = () => { plan = C.plan(); plan.actions = qty; C.savePlan(plan); };

  function computeFacts() {
    const slot = Object.fromEntries(F.slots.map((s) => [s.id, s]));
    const m1158 = M.find((m) => m.id === "M-1158"), s1158 = C.agg(m1158, 0, 5);
    const b40 = M.filter((m) => m.loc[5] && slot[m.loc[5]].zone === "Z-B40").map((m) => C.agg(m, 4, 5));
    const b40day = b40.reduce((t, s) => t + s.theo, 0) / 61;
    const ridge = Mo.preventive.find((r) => r.manufacturer === "Ridgeline");
    return { s1158, deficitDay: -s1158.luck / s1158.days, b40day, ridge, nB40: b40.length };
  }

  // per-action write-up: target, effect (point, $ over effective days), uncertainty, measurement, evidence
  function brief(id, n) {
    const a = act(id), days = Math.max(0, HORIZON - a.lead_days), f = facts;
    switch (id) {
      case "A-INSPECT": return {
        target: n > 1 ? `M-1158 first, then ${n - 1} more` : "M-1158, Back Forty, Desert Gold",
        effect: f.deficitDay * days, effectText: `If the paytable is wrong and gets fixed, the machine stops giving back ${C.usd(f.deficitDay)} a day more than configured: about ${C.usd(f.deficitDay * days)} over ${days} days.`,
        unc: `Its hit rate is z +124 from configuration and hold ${C.pct(f.s1158.hold)} against ${C.pct(f.s1158.theoHold)}, the only flag after correction. The cause could be a paytable, a meter or a coin-in error, or nothing; an inspection buys the answer, not the fix.`,
        meas: "Hold and hit rate for the 30 days after inspection against the machine's 99% band; hit-rate z should fall toward 0.",
        ev: [["Luck ranking", "machines.html#M-1158"]] };
      case "A-PREVENTIVE": {
        const per30 = f.ridge.theo_plus_repair_per_30d, be = a.unit_cost_cents / 100 / (per30 * days / 30);
        return {
          target: "Ridgeline machines (94), the 4.2× fault-rate maker", effect: 0.4 * per30 * days / 30,
          effectText: `Ridgeline faults cost ${C.usd(per30)} per 30 days in lost theo and repairs. At a 40% cut that's ${C.usd(0.4 * per30 * days / 30)} over the ${days} days after the lead. Break-even is a ${C.pct(be, 0)} cut within July, ${C.pct(f.ridge.breakeven_fault_reduction, 0)} over a full 30 days.`,
          unc: "The data has no record of what a sweep does to fault rates, so the 40% is an assumption. Ridgeline faults 4.2× as often as Halcyon (95% CI 3.5–5.1).",
          meas: "Ridgeline fault rate vs its Jan–Jun rate, Poisson test; a 25% cut is detectable in 30 days, which covers the break-even.",
          ev: [["Fault model", "models.html"], ["Downtime by zone", "index.html"]] };
      }
      case "A-WAYFINDING": {
        const be = (a.unit_cost_cents / 100) / (f.b40day * days);
        return {
          target: `Back Forty, ${f.nB40} machines, 9 of the GM's bottom 10`, effect: 0.05 * f.b40day * days,
          effectText: `Back Forty earns ${C.usd(f.b40day)} theo a day. Each 1% lift is ${C.usd(f.b40day * days / 100)} over ${days} days; break-even is ${C.pct(be, 1)}. At 5%, about ${C.usd(0.05 * f.b40day * days)}.`,
          unc: "Closing its main walkway cut Back Forty's play 31%, so access matters; how much signs recover is unknown. The 5% is an assumption, shown with its break-even.",
          meas: "Back Forty vs the five control zones, coin-in per hour, 30 days; a 3.6% gap is detectable.",
          ev: [["Walkway closure", "context.html"], ["Floor plan", "index.html"]] };
      }
      case "A-MOVE-MACHINE": {
        const s = plan.moveSummary;
        if (!s || !s.n) return { target: "None placed yet", effect: 0, effectText: "Drag machines on the floor plan to price moves.", unc: "", meas: "", ev: [["Floor plan", "index.html"]] };
        return {
          target: s.rows.map((r) => `${r.m} ${r.from} → ${r.to}`).join(", "), effect: s.day * s.days,
          effectText: `${C.usd(s.day, { plus: true })} theo a day, ${C.usd(s.day * s.days, { plus: true })} over ${s.days} days (model range ${C.usd(s.lo * s.days, { plus: true })} to ${C.usd(s.hi * s.days, { plus: true })}).`,
          unc: "Bank effects come from the location model. The one real move in the data matched its projection (+$303 predicted, +$342 a day measured), but the range shown is model-only.",
          meas: "Moved machines vs untouched machines in the same banks, weekly diff-in-diff with placebo intervals. A single machine needs a large change to show, so judge the moves together.",
          ev: [["Floor plan", "index.html"]] };
      }
      case "A-COMP-PILOT": return {
        target: "Half of active card holders, picked at random within tier and home region, back on pre-May comp prices",
        effect: null, effectText: "Not a revenue action: it buys the answer to whether the May 1 price cut (−53% points per comp) brought in play worth its cost. Today's comp cost runs about $33K a month, 1.3% of tracked theo.",
        unc: "The price cut has no comparison group and overlaps the June visitor slowdown, so nothing in the data can say what it did. Effects on play may be small and take longer than 30 days to show.",
        meas: "Theo and visits per card holder, test vs control, over 25 days after the 5-day lead; comp cost per dollar of theo in each group. Decide on a rule written before the start.",
        ev: [["Comps", "comps.html"], ["Players", "players.html"]] };
      default: return { target: "–", effect: null, effectText: "Not estimated from this data.", unc: "", meas: "", ev: [] };
    }
  }

  const NOT = [
    ["Replace the bottom 10 (lease or buy)", "The like-for-like replacement already tried at a bottom-10 slot moved theo by +$4 a day (−$17 to +$23). A lease costs $3,380 in July; a purchase $22,000.", "context.html"],
    ["Add a technician", "Recovers $1.8–2.8K of theo per 30 days against an $11,520 cost. Most downtime is fix time (2.9 h), not waiting (1.1 h).", "models.html"],
    ["Promotion weekend", "Promotions lifted floor theo $8–26K a day, but theo is what guests are expected to lose and prize costs beyond the $15,000 aren't in the data. A separate decision.", "context.html"],
    ["Swap Back Forty games to high-hold titles", "The model's gains come almost entirely from a 12% vs 5% hold: more player loss, not more play.", "models.html"],
    ["Change the comp rate floor-wide", "Can't be combined with the pilot, and a second untested price change would leave the May 1 cut unmeasured.", "comps.html"],
    ["Guest survey", "Not analysed on this site.", null],
  ];

  function render() {
    const types = Object.keys(qty).filter((k) => qty[k] > 0);
    const total = types.reduce((t, k) => t + cost(act(k), qty[k]), 0);
    const effects = types.map((k) => brief(k, qty[k]).effect).filter((v) => v != null);
    const over = total > C.BUDGET, tooMany = types.length > MAX_TYPES;
    const comp = qty["A-COMP-PILOT"] > 0 && qty["A-COMP-CHANGE"] > 0;
    $("#stats").innerHTML = [
      ["Committed", C.usd(total), over ? "Over the $100,000 budget" : `of ${C.usd(C.BUDGET)}`],
      ["Kept", C.usd(Math.max(0, C.BUDGET - total)), "Preserved, a valid choice"],
      ["Action types", `${types.length} of ${MAX_TYPES}`, tooMany ? "Too many: drop one" : comp ? "Comp pilot and comp change can't be combined" : "Within the limit"],
      ["Expected theo, July", C.usd(effects.reduce((t, v) => t + v, 0), { plus: true }), "Sum of the point estimates below"],
    ].map(([l, v, f], i) => `<div class="stat"><div class="label">${l}</div><div class="value${i === 0 ? " accent" : ""}">${v}</div><div class="foot" ${(i === 0 && over) || (i === 2 && (tooMany || comp)) ? 'style="color:var(--neg)"' : ""}>${f}</div></div>`).join("");

    // budget bar: one brass step per funded action (largest first), the kept money hatched
    const parts = types.map((k) => ({ a: act(k), c: cost(act(k), qty[k]) })).sort((p, q) => q.c - p.c);
    const scaleTo = Math.max(C.BUDGET, total);
    const kept = Math.max(0, C.BUDGET - total);
    $("#budget").innerHTML = `<div class="budget-bar" role="img" aria-label="${C.esc(parts.map((p) => `${p.a.name} ${C.usd(p.c)}`).concat(`kept ${C.usd(kept)}`).join(", "))}">
        ${parts.map((p, i) => `<span class="${over ? "over" : "b" + Math.min(i, 3)}" style="flex:0 0 ${(p.c / scaleTo) * 100}%" title="${C.esc(p.a.name)}: ${C.usd(p.c)}"></span>`).join("")}
        ${kept ? '<span class="kept" title="Kept"></span>' : ""}</div>
      <div class="budget-key">${parts.map((p, i) => `<span><i class="${over ? "over" : "b" + Math.min(i, 3)}" style="background:${over ? "var(--neg)" : ["var(--accent)", "color-mix(in srgb, var(--accent) 70%, var(--card))", "color-mix(in srgb, var(--accent) 45%, var(--card))", "color-mix(in srgb, var(--accent) 28%, var(--card))"][Math.min(i, 3)]}"></i>${C.esc(p.a.name)} <span class="num">${C.usd(p.c)}</span></span>`).join("")}
        ${kept ? `<span><i style="background:var(--raised);box-shadow:inset 0 0 0 1px var(--line-2)"></i>Kept <span class="num">${C.usd(kept)}</span></span>` : ""}</div>`;

    $("#catalog").innerHTML = CAT.map((a) => {
      const n = qty[a.action_type_id] || 0, floor = a.action_type_id === "A-MOVE-MACHINE";
      return `<div class="act ${n ? "on" : ""}" style="grid-template-columns:1fr auto"><div><div class="name">${C.esc(a.name)}</div>
        <div class="meta">${C.usd(a.unit_cost_cents / 100)}${a.recurring_cost_cents_per_day ? ` + ${C.usd(a.recurring_cost_cents_per_day / 100)}/day` : ""}, lead ${a.lead_days} d, up to ${a.quantity_limit}${floor ? ", set on the floor plan" : ""}</div></div>
        ${floor ? `<a class="btn" href="index.html" aria-label="Place moves on the floor plan">${n}</a>` : `<div class="stepper" role="group" aria-label="${C.esc(a.name)} quantity">
          <button type="button" data-d="-1" data-id="${a.action_type_id}" ${n ? "" : "disabled"} aria-label="Fewer">−</button><output>${n}</output>
          <button type="button" data-d="1" data-id="${a.action_type_id}" ${n >= a.quantity_limit ? "disabled" : ""} aria-label="More">+</button></div>`}</div>`;
    }).join("");
    $("#catalog").onclick = (e) => {
      const b = e.target.closest("button[data-id]"); if (!b) return;
      const id = b.dataset.id, a = act(id);
      qty[id] = Math.max(0, Math.min(a.quantity_limit, (qty[id] || 0) + +b.dataset.d));
      if (!qty[id]) delete qty[id];
      save(); render();
    };

    $("#cards").innerHTML = types.length ? types.map((k) => {
      const a = act(k), b = brief(k, qty[k]);
      return `<article class="card plan-card"><div class="card-head" style="margin-bottom:0"><div><h3>${C.esc(a.name)}</h3>
        <p class="mono small" style="color:var(--ink-3)">${a.action_type_id} × ${qty[k]}</p></div><div class="num" style="font-size:18px">${C.usd(cost(a, qty[k]))}</div></div>
        <dl><dt>Target</dt><dd>${C.esc(b.target)}</dd><dt>Expected effect</dt><dd>${b.effectText}</dd>
        ${b.unc ? `<dt>Uncertainty</dt><dd>${b.unc}</dd>` : ""}${b.meas ? `<dt>How we'd measure it</dt><dd>${b.meas}</dd>` : ""}
        ${b.ev.length ? `<dt>Evidence</dt><dd>${b.ev.map(([t, h]) => `<a href="${h}">${t}</a>`).join(", ")}</dd>` : ""}</dl></article>`;
    }).join("") : '<p class="empty">Nothing funded: the whole budget is kept.</p>';

    $("#no").innerHTML = `<thead><tr><th>Action</th><th>Why not</th><th>Evidence</th></tr></thead><tbody>${NOT.map(([a, w, h]) =>
      `<tr><td>${a}</td><td style="color:var(--ink-2)">${w}</td><td>${h ? `<a href="${h}">Open</a>` : "–"}</td></tr>`).join("")}</tbody>`;
  }
})();
