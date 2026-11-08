/* Actions page: budget builder over action_catalog, draft plan with evidence,
   effect sizes computed from the same data the other pages show. */
(function () {
  "use strict";
  const C = window.Core, $ = C.$;
  const HORIZON = 30, MAX_TYPES = 3;
  // Draft: the optimizer's machine moves (added at load), new signs for Back Forty, and M-1158's inspection.
  const DRAFT = { "A-INSPECT": 1, "A-WAYFINDING": 1 }, DRAFT_VERSION = 2;
  // The assumptions the data can't settle. Central values are what the cards use; low/high bound the
  // sensitivity table. Each slider moves the central value.
  const ASM = {
    inspect: { label: "Chance M-1158's inspection finds a fixable paytable fault", lo: 0, mid: 0.5, hi: 1, max: 1, step: 0.05 },
    prevent: { label: "Cut in Ridgeline faults from the maintenance sweep", lo: 0.1, mid: 0.4, hi: 0.6, max: 0.8, step: 0.05 },
    signs: { label: "Lift in Back Forty play from new signs", lo: 0, mid: 0.05, hi: 0.1, max: 0.15, step: 0.005 },
  };
  const ASM_OF = { "A-INSPECT": "inspect", "A-PREVENTIVE": "prevent", "A-WAYFINDING": "signs" };
  const dec = (s) => (s.step < 0.01 ? 1 : 0);
  const DEF = Object.fromEntries(Object.entries(ASM).map(([k, s]) => [k, s.mid]));
  let CAT, M, F, Mo, plan, qty, facts;

  document.addEventListener("DOMContentLoaded", async () => {
    try { [Mo, M, F] = await Promise.all([C.load("models"), C.load("machines"), C.load("floor")]); }
    catch (e) { return C.fail($("#main"), e); }
    CAT = Mo.catalog.filter((a) => a.action_type_id !== "A-HOLD");
    plan = C.plan();
    // The draft puts the optimizer's best moves on the floor, so the plan starts from them without a visit
    // to the floor page. A plan saved under an older draft is replaced once; after that, the visitor's edits stand.
    const useDraft = () => {
      const [a, b] = C.getPeriod(), best = C.bestMovePlan(F, M, a, b);
      plan = C.plan(); plan.moves = best.moves; plan.moveSummary = best.summary; plan.actions = { ...DRAFT }; plan.draft = DRAFT_VERSION;
      C.savePlan(plan);
    };
    if (plan.draft !== DRAFT_VERSION) useDraft();
    qty = plan.actions || { ...DRAFT };
    const syncMoves = () => { const n = plan.moveSummary?.n || 0; if (n) qty["A-MOVE-MACHINE"] = n; else delete qty["A-MOVE-MACHINE"]; };
    syncMoves();
    facts = computeFacts();
    try { const s = JSON.parse(localStorage.getItem("ga-asm")); if (s) for (const k in ASM) if (s[k] != null) ASM[k].mid = s[k]; } catch { /* */ }
    $("#reset").onclick = () => { useDraft(); qty = { ...DRAFT }; syncMoves(); save(); render(); };
    recommended();
    $("#sens-ctl").oninput = (e) => {
      const k = e.target.dataset.k; if (!k) return;
      ASM[k].mid = +e.target.value; $(`#asm-${k}-o`).textContent = C.pct(ASM[k].mid, dec(ASM[k]));
      try { localStorage.setItem("ga-asm", JSON.stringify(Object.fromEntries(Object.entries(ASM).map(([j, s]) => [j, s.mid])))); } catch { /* */ }
      render();
    };
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
  // July theo effect of an action at assumption value x (null = not a revenue action)
  function effectAt(id, x) {
    const a = act(id), days = Math.max(0, HORIZON - a.lead_days), f = facts;
    if (id === "A-INSPECT") return x * f.deficitDay * days;
    if (id === "A-PREVENTIVE") return x * f.ridge.theo_plus_repair_per_30d * days / 30;
    if (id === "A-WAYFINDING") return x * f.b40day * days;
    return null;
  }
  // the assumption value at which one unit of the action pays for itself
  const breakEven = (id) => { const e1 = effectAt(id, 1); return e1 ? cost(act(id), 1) / e1 : null; };

  function brief(id, n) {
    const a = act(id), days = Math.max(0, HORIZON - a.lead_days), f = facts;
    switch (id) {
      case "A-INSPECT": return {
        target: n > 1 ? `M-1158 first, then ${n - 1} more` : "M-1158, Back Forty, Desert Gold",
        effect: effectAt(id, ASM.inspect.mid), effectText: `If the paytable is wrong and gets fixed, the machine stops giving back ${C.usd(f.deficitDay)} a day more than configured: ${C.usd(f.deficitDay * days)} over ${days} days. At a ${C.pct(ASM.inspect.mid, 0)} chance the fault is fixable, ${C.usd(effectAt(id, ASM.inspect.mid))}. Break-even is a ${C.pct(breakEven(id), 0)} chance.`,
        unc: `Its hit rate is z +124 from configuration and hold ${C.pct(f.s1158.hold)} against ${C.pct(f.s1158.theoHold)}, the only flag after correction. The cause could be a paytable, a meter or a coin-in error, or nothing; an inspection buys the answer, not the fix.`,
        meas: "Hold and hit rate for the 30 days after inspection against the machine's 99% band; hit-rate z should fall toward 0.",
        ev: [["Luck ranking", "machines.html#M-1158"]] };
      case "A-PREVENTIVE": {
        const per30 = f.ridge.theo_plus_repair_per_30d, be = a.unit_cost_cents / 100 / (per30 * days / 30);
        return {
          target: "Ridgeline machines (94), the 4.2× fault-rate maker", effect: effectAt(id, ASM.prevent.mid),
          effectText: `Ridgeline faults cost ${C.usd(per30)} per 30 days in lost theo and repairs. At a ${C.pct(ASM.prevent.mid, 0)} cut that's ${C.usd(effectAt(id, ASM.prevent.mid))} over the ${days} days after the lead. Break-even is a ${C.pct(be, 0)} cut within July, ${C.pct(f.ridge.breakeven_fault_reduction, 0)} over a full 30 days.`,
          unc: `The data has no record of what a sweep does to fault rates, so the ${C.pct(ASM.prevent.mid, 0)} is an assumption; the sensitivity table runs 10% to 60%. Ridgeline faults 4.2× as often as Halcyon (95% CI 3.5–5.1).`,
          meas: "Ridgeline fault rate vs its Jan–Jun rate, Poisson test; a 25% cut is detectable in 30 days, which covers the break-even.",
          ev: [["Downtime by maker and shift", "downtime.html#mk-h"], ["Fault model", "models.html"]] };
      }
      case "A-WAYFINDING": {
        const be = (a.unit_cost_cents / 100) / (f.b40day * days);
        return {
          target: `Back Forty, ${f.nB40} machines, 9 of the GM's bottom 10`, effect: effectAt(id, ASM.signs.mid),
          effectText: `Back Forty earns ${C.usd(f.b40day)} theo a day. Each 1% lift is ${C.usd(f.b40day * days / 100)} over ${days} days; break-even is ${C.pct(be, 1)}. At ${C.pct(ASM.signs.mid, 1)}, about ${C.usd(effectAt(id, ASM.signs.mid))}.`,
          unc: `Closing its main walkway cut Back Forty's play 31%, so access matters; how much signs recover is unknown. The ${C.pct(ASM.signs.mid, 1)} is an assumption, shown with its break-even.`,
          meas: "Back Forty vs the five control zones, coin-in per hour, 30 days; a 3.6% gap is detectable.",
          ev: [["Walkway closure", "context.html"], ["Floor plan", "floor.html"]] };
      }
      case "A-MOVE-MACHINE": {
        const s = plan.moveSummary;
        if (!s || !s.n) return { target: "None placed yet", effect: 0, effectText: "Drag machines on the floor plan to price moves.", unc: "", meas: "", ev: [["Floor plan", "floor.html"]] };
        return {
          target: `${s.n} machines, the optimizer's best plan into stronger banks (see the floor plan for each move)`, effect: s.day * s.days,
          effectText: `${C.usd(s.day, { plus: true })} theo a day, ${C.usd(s.day * s.days, { plus: true })} over ${s.days} days (model range ${C.usd(s.lo * s.days, { plus: true })} to ${C.usd(s.hi * s.days, { plus: true })}).`,
          unc: "Bank effects come from the location model. The one real move in the data matched its projection (+$303 predicted, +$342 a day measured), but the range shown is model-only.",
          meas: "Moved machines vs untouched machines in the same banks, weekly diff-in-diff with placebo intervals. A single machine needs a large change to show, so judge the moves together.",
          ev: [["Floor plan", "floor.html"]] };
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
    ["Preventive sweep, Ridgeline ($9,000)", "Nets only about $240 in July at a 40% fault cut, and needs a 39% cut to break even. Moves earn far more for the third action slot.", "downtime.html#mk-h"],
    ["Comp pilot ($4,000)", "The right next step for comps, but only three action types are allowed and moves, signs and the inspection each earn more in July. First in line for August.", "comps.html"],
    ["Change the comp rate floor-wide", "Can't be combined with the pilot, and a second untested price change would leave the May 1 cut unmeasured.", "comps.html"],
    ["Guest survey", "Not analysed on this site.", null],
  ];

  // Our plan in one table: what, why, cost, July net (pessimistic to optimistic) and how we'd know.
  // Uses the draft and the default assumptions, so it doesn't move when a visitor edits the builder.
  function recommended() {
    const [a, b] = C.getPeriod(), mv = C.bestMovePlan(F, M, a, b).summary;
    const rows = [
      { name: `Move ${mv.n} machines to better spots`, why: "Location sets how much a machine plays: Back Forty lost 31% while its walkway was closed.",
        c: mv.cost, v: [mv.lo, mv.day, mv.hi].map((x) => x * mv.days - mv.cost),
        how: "Moved machines against unmoved ones in the same banks, week by week.", href: "floor.html" },
      { name: "New signs for Back Forty", why: "It's the hardest zone to reach, and 9 of the GM's bottom 10 are there.",
        c: cost(act("A-WAYFINDING"), 1), v: [ASM.signs.lo, DEF.signs, ASM.signs.hi].map((x) => effectAt("A-WAYFINDING", x) - cost(act("A-WAYFINDING"), 1)),
        how: "Back Forty against the other zones; a 3.6% gap shows within 30 days.", href: "context.html#cl-h" },
      { name: "Inspect M-1158", why: "It pays out far more often than its settings allow.",
        c: cost(act("A-INSPECT"), 1), v: [ASM.inspect.lo, DEF.inspect, ASM.inspect.hi].map((x) => effectAt("A-INSPECT", x) - cost(act("A-INSPECT"), 1)),
        how: "Its win rate returns to the normal range after the check.", href: "machines.html#M-1158" },
    ];
    const total = rows.reduce((t, r) => t + r.c, 0), tot = [0, 1, 2].map((i) => rows.reduce((t, r) => t + r.v[i], 0));
    $("#rec-total").textContent = C.usd(total);
    $("#rec").innerHTML = `<thead><tr><th>Action</th><th>Why</th><th class="num">Cost</th><th class="num">July net<span class="sub">low – high</span></th><th>How we'll know it worked</th></tr></thead><tbody>
      ${rows.map((r) => `<tr><td class="rec-name"><a href="${r.href}">${C.esc(r.name)}</a></td><td>${C.esc(r.why)}</td><td class="num">${C.usd(r.c)}</td>
        <td class="num"><strong>${C.usd(r.v[1], { plus: true })}</strong><span class="sub">${C.usd(r.v[0], { plus: true })} – ${C.usd(r.v[2], { plus: true })}</span></td><td>${C.esc(r.how)}</td></tr>`).join("")}
      <tr class="hl"><td class="rec-name">Total</td><td>Keep ${C.usd(C.BUDGET - total)}</td><td class="num">${C.usd(total)}</td>
        <td class="num"><strong>${C.usd(tot[1], { plus: true })}</strong><span class="sub">${C.usd(tot[0], { plus: true })} – ${C.usd(tot[2], { plus: true })}</span></td><td></td></tr></tbody>`;
    $("#rec-note").textContent = `Net is July theo (expected house win) gained, minus cost. We keep ${C.usd(C.BUDGET - total)} because nothing else pays in July: moves stop at the catalogue's limit of 24, and only three action types are allowed.`;
  }

  let sliderKeys = "";
  function sliders(types) {
    const keys = types.map((k) => ASM_OF[k]).filter(Boolean);
    if (keys.join() === sliderKeys) return;          // rebuild only when the funded set changes, so a drag isn't interrupted
    sliderKeys = keys.join();
    if (!keys.length) { $("#sens-ctl").innerHTML = ""; return; }
    $("#sens-ctl").innerHTML = keys.map((k) => [k, ASM[k]]).map(([k, s]) => `<label for="asm-${k}">${s.label}
      <input type="range" id="asm-${k}" data-k="${k}" min="0" max="${s.max}" step="${s.step}" value="${s.mid}">
      <output id="asm-${k}-o">${C.pct(s.mid, dec(s))}</output></label>`).join("");
  }
  // pessimistic / your assumption / optimistic, net of cost, for each funded action and the plan as a whole
  function sensitivity(types) {
    sliders(types);
    const rows = types.map((k) => {
      const a = act(k), c = cost(a, qty[k]), key = ASM_OF[k];
      if (key) {
        const s = ASM[key];
        return { name: a.name, c, assume: `${C.pct(s.lo, dec(s))} / ${C.pct(s.mid, dec(s))} / ${C.pct(s.hi, dec(s))}`,
          v: [s.lo, s.mid, s.hi].map((x) => effectAt(k, x) - c), be: C.pct(breakEven(k), 1) };
      }
      if (k === "A-MOVE-MACHINE" && plan.moveSummary?.n) {
        const m = plan.moveSummary;
        return { name: a.name, c, assume: "Location model, 90% range", v: [m.lo * m.days - c, m.day * m.days - c, m.hi * m.days - c], be: "–" };
      }
      return { name: a.name, c, assume: "Buys information, not revenue", v: [-c, -c, -c], be: "–" };
    });
    const tot = [0, 1, 2].map((i) => rows.reduce((t, r) => t + r.v[i], 0));
    const cell = (v) => `<td class="num ${v < 0 ? "neg" : "pos"}">${C.usd(v, { plus: true })}</td>`;
    $("#sens").innerHTML = rows.length ? `<thead><tr><th>Action</th><th class="num">Cost</th><th>Assumption: low / yours / high</th><th class="num">Break-even</th>
        <th class="num">Net, pessimistic</th><th class="num">Net, your assumption</th><th class="num">Net, optimistic</th></tr></thead><tbody>
      ${rows.map((r) => `<tr><td>${C.esc(r.name)}</td><td class="num">${C.usd(r.c)}</td><td>${r.assume}</td><td class="num">${r.be}</td>${r.v.map(cell).join("")}</tr>`).join("")}
      <tr class="hl"><td>The plan</td><td class="num">${C.usd(rows.reduce((t, r) => t + r.c, 0))}</td><td></td><td></td>${tot.map(cell).join("")}</tr></tbody>`
      : '<tbody><tr><td class="empty">Nothing funded: no downside and no upside.</td></tr></tbody>';
    $("#sens-note").innerHTML = !rows.length ? "" : tot[0] >= 0
      ? `Even with every assumption at its low end, the plan nets ${C.usd(tot[0], { plus: true })}.`
      : `With every assumption at its low end, the plan loses ${C.usd(-tot[0])}: never more than it spends.`;
  }

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
      ["Net theo, July", C.usd(effects.reduce((t, v) => t + v, 0) - total, { plus: true }),
        `${C.usd(effects.reduce((t, v) => t + v, 0), { plus: true })} expected, less everything committed`],
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
        ${floor ? `<a class="btn" href="floor.html" aria-label="Place moves on the floor plan">${n}</a>` : `<div class="stepper" role="group" aria-label="${C.esc(a.name)} quantity">
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
      return `<details class="card plan-card"><summary><span><span class="pc-name">${C.esc(a.name)} × ${qty[k]}</span>
        <span class="pc-target">${C.esc(b.target)}</span></span><span class="num">${C.usd(cost(a, qty[k]))}</span></summary>
        <dl><dt>Expected effect</dt><dd>${b.effectText}</dd>
        ${b.unc ? `<dt>Uncertainty</dt><dd>${b.unc}</dd>` : ""}${b.meas ? `<dt>How we'd measure it</dt><dd>${b.meas}</dd>` : ""}
        ${b.ev.length ? `<dt>Evidence</dt><dd>${b.ev.map(([t, h]) => `<a href="${h}">${t}</a>`).join(", ")}</dd>` : ""}</dl></details>`;
    }).join("") : '<p class="empty">Nothing funded: the whole budget is kept.</p>';

    sensitivity(types);
    $("#no").innerHTML = `<thead><tr><th>Action</th><th>Why not</th><th>Evidence</th></tr></thead><tbody>${NOT.map(([a, w, h]) =>
      `<tr><td>${a}</td><td style="color:var(--ink-2)">${w}</td><td>${h ? `<a href="${h}">Open</a>` : "–"}</td></tr>`).join("")}</tbody>`;
  }
})();
