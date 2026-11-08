/* What each catalogue action can bring in July, and the plans that make the most of the budget.

   C.actionModels(ctx) → one model per action type:
     { id, name, unit, max, lead, days, cost(q), opts: [q], val(q) → [pessimistic, central, optimistic],
       basis, why, how, whyNot, target(q), href }
   val is July theo gained over the days left after the lead time, less the theo lost while the action itself
   takes machines off the floor (catalogue downtime × the floor's theo per machine-hour). Net = val − cost.
   Inputs: data/benefits.js (scripts/build_site_benefits.py), the location model (assets/moves.js) and the
   assumption values in ctx.asm, each { lo, mid, hi } = its value in the pessimistic, central, optimistic case.

   C.planOptions(models, s) → per action, the quantities worth considering in scenario s
   C.bestPlan(models, s, budget) and C.frontier(models, s) search every plan of up to three action types
   (the GUIDE's limit), without the comp pilot and the comp change together, and without whole-bank moves
   alongside single-machine moves (both move machines; the model can't value the two on the same machines). */
(function () {
  "use strict";
  const C = window.Core;
  const HORIZON = 30, MAX_TYPES = 3;
  C.DEFAULT_ASSUMPTIONS = {
    signs: { lo: 0, mid: 0.05, hi: 0.1 },
    inspect: { lo: 0, mid: 0.5, hi: 1 },
    prevent: { lo: 0.1, mid: 0.4, hi: 0.6 },
    compLoss: { lo: 0.01, mid: 0, hi: 0 },
  };

  C.actionModels = ({ B, F, M, cat, a, b, asm, mm }) => {
    const act = Object.fromEntries(cat.map((x) => [x.action_type_id, x]));
    const days = (id) => Math.max(0, HORIZON - act[id].lead_days);
    const cost = (id) => (q) => (q * (act[id].unit_cost_cents + act[id].recurring_cost_cents_per_day * days(id))) / 100;
    const down = (id, machines = 1) => (act[id].downtime_minutes / 60) * machines * B.hourTheo;   // theo lost per unit
    const S3 = (k) => [asm[k].lo, asm[k].mid, asm[k].hi];
    const zone = Object.fromEntries(B.zones.map((z) => [z.id, z]));
    const range = (n) => Array.from({ length: n + 1 }, (_, i) => i);
    const base = (id, extra) => ({ id, name: act[id].name, max: act[id].quantity_limit, lead: act[id].lead_days, days: days(id),
      unitCost: act[id].unit_cost_cents / 100, recurringCostPerDay: act[id].recurring_cost_cents_per_day / 100, cost: cost(id), ...extra });

    // machine moves: the optimizer's path, valued over the 28 days after the lead
    const stepAt = (q) => mm.steps.filter((s) => s.n <= q).pop();
    const moveVal = (q) => { const s = stepAt(q); return s ? [s.lo, s.mid, s.hi].map((v) => v - s.n * down("A-MOVE-MACHINE")) : [0, 0, 0]; };
    // whole banks: the best swap of two banks' positions (two units), over the 25 days after the lead
    const bs = mm.bankSwaps[0], bankDays = days("A-MOVE-BANK");
    const promo = B.promos, tour = promo.find((p) => p.days <= 3), weekLong = promo.find((p) => p.days > 3);
    const weekend = [weekLong.lo * 3, ((tour.day + weekLong.day) / 2) * 3, tour.hi * 3];
    const like = B.replace.like;
    const others = B.zones.filter((z) => z.id !== "Z-B40" && z.id !== "Z-HL").sort((x, y) => x.theoDay - y.theoDay);
    const secondZone = others[0];

    return [
      base("A-MOVE-MACHINE", {
        opts: [0, ...mm.steps.map((s) => s.n)].filter((q, i, arr) => arr.indexOf(q) === i), val: moveVal, basis: "Location model",
        why: "Location affects how much a machine plays: Back Forty play fell during the walkway closure.",
        how: "Moved machines against unmoved ones in the same banks, week by week.",
        whyNot: "", target: (q) => `${stepAt(q)?.n || 0} machines into stronger banks, best first (each move on the floor plan)`, href: "floor.html",
        note: "Bank effects from the location model, fit on Jan–Apr. The one real move in the data matched its projection; the range is the model's own." }),
      base("A-MOVE-BANK", {
        opts: [0, 2], val: (q) => (q >= 2 && bs ? [bs.lo, bs.mid, bs.hi].map((v) => v * bankDays - 2 * down("A-MOVE-BANK", bs.machines / 2)) : [0, 0, 0]),
        basis: "Location model", why: bs ? `Swapping banks ${bs.A.slice(2)} and ${bs.B.slice(2)} puts the stronger machines in the better spot.` : "",
        how: "Both banks' theo against the rest of their zones, week by week.",
        whyNot: "Moving machines one at a time reaches the same spots for less.", target: () => (bs ? `Swap bank ${bs.A.slice(2)} with bank ${bs.B.slice(2)} (two units)` : "–"), href: "floor.html",
        note: "The same location model as machine moves, applied to two whole banks trading places. A whole bank can only swap with another, so it takes two units." }),
      base("A-REPLACE-LEASE", {
        opts: range(act["A-REPLACE-LEASE"].quantity_limit), val: (q) => like.map((d) => q * (d * days("A-REPLACE-LEASE") - down("A-REPLACE-LEASE"))),
        basis: "Measured", why: "A new title in the same spot.", how: "The new machines' theo against the old ones' at the same slots.",
        whyNot: `The like-for-like replacement tried in May moved theo by ${C.usd(like[1], { plus: true })} a day (${C.usd(like[0])} to ${C.usd(like[2], { plus: true })}).`,
        target: (q) => `${q} machines`, href: "context.html#ev-h",
        note: "Measured at L-38-5, where M-1120 was replaced like-for-like in May (49 days, 90% interval)." }),
      base("A-REPLACE-BUY", {
        opts: range(act["A-REPLACE-BUY"].quantity_limit), val: (q) => like.map((d) => q * (d * days("A-REPLACE-BUY") - down("A-REPLACE-BUY"))),
        basis: "Measured", why: "A purchased new title in the same spot.", how: "As for leased machines.",
        whyNot: `Same measured effect as a lease; it costs ${C.usd(act["A-REPLACE-BUY"].unit_cost_cents / 100)} per machine with ${days("A-REPLACE-BUY")} days left in July.`,
        target: (q) => `${q} machines`, href: "context.html#ev-h",
        note: "As for leased replacements; the purchase price counts in full against July." }),
      base("A-TECH-SHIFT", {
        opts: range(3), val: (q) => [0.8, 1, 1.2].map((f) => f * B.tech.slice(0, q).reduce((t, x) => t + x.saved30, 0) * days("A-TECH-SHIFT") / 30),
        basis: "Model, replayed", why: "Faults wait less for a technician.", how: "Fault waits on the staffed shift against Jan–Jun.",
        whyNot: "Most downtime comes from repair time rather than waiting for a technician, so adding a technician recovers little play.",
        target: (q) => B.tech.slice(0, q).map((t) => t.shift).join(", ") + (q ? " shift" + (q > 1 ? "s" : "") : ""), href: "downtime.html#fix-h",
        note: "Every Jan–Jun fault replayed through the real roster with one more technician; ±20% for how a down hour is valued." }),
      base("A-PREVENTIVE", {
        opts: range(3), val: (q) => S3("prevent").map((cut) => B.preventive.slice(0, q).reduce((t, x) => t + x.per30 * cut * days("A-PREVENTIVE") / 30 - x.downtime, 0)),
        basis: "Assumption", why: "Ridgeline machines fault more often than Halcyon's.", how: "The maker's fault rate against its Jan–Jun rate (Poisson test).",
        whyNot: "Pays only if a sweep cuts faults enough within July; the data do not establish how much it would cut them.",
        target: (q) => B.preventive.slice(0, q).map((x) => x.maker).join(", "), href: "downtime.html#mk-h",
        note: "Lost theo and repair cost per 30 days come from the data; the cut a sweep achieves is an assumption (slider below)." }),
      base("A-INSPECT", {
        opts: range(act["A-INSPECT"].quantity_limit), val: (q) => S3("inspect").map((p) => (q ? p * B.m1158GapDay * days("A-INSPECT") : 0) - q * down("A-INSPECT")),
        basis: "Measured + assumption", why: "M-1158 pays out far more often than its settings allow.", how: "Its win rate returns to the normal range after the check.",
        whyNot: "No other machine's payouts are out of line, so extra inspections find nothing to fix.",
        target: (q) => (q > 1 ? `M-1158, then ${q - 1} more` : "M-1158"), href: "machines.html#M-1158",
        note: `M-1158 gives back ${C.usd(B.m1158GapDay)} a day more than its settings; whether the cause is fixable on the spot is an assumption (slider below).` }),
      base("A-WAYFINDING", {
        opts: range(2), val: (q) => [0, 1, 2].map((s) => (q >= 1 ? S3("signs")[s] * zone["Z-B40"].theoDay * days("A-WAYFINDING") : 0)
          + (q >= 2 ? [0, 0, 0.02][s] * secondZone.theoDay * days("A-WAYFINDING") : 0)),
        basis: "Assumption", why: "Back Forty is the hardest zone to reach, and the GM's lowest-performing machines cluster there.",
        how: "Back Forty against the other zones, measured week by week.",
        whyNot: `A second zone (${secondZone.name}) has no access problem to fix.`,
        target: (q) => (q > 1 ? `Back Forty and ${secondZone.name}` : "Back Forty"), href: "context.html#cl-h",
        note: "Closing Back Forty's walkway reduced its play, but how much signs win back is an assumption (slider below)." }),
      base("A-COMP-PILOT", {
        opts: [0, 1], val: (q) => S3("compLoss").map((loss) => q * 0.5 * (B.comps.extraPerMonth - loss * B.comps.usersTheoPerMonth) * days("A-COMP-PILOT") / 30),
        basis: "Measured + assumption", why: "Tests whether May's cheaper comps bought any play.", how: "Old-price half against new-price half: theo and visits per card holder.",
        whyNot: "Saves little in July; its value is learning whether the cheaper comps brought in play.",
        target: () => "A random half of card holders back on the old prices", href: "comps.html#test-h",
        note: "Half the extra comp cost since May 1 is saved while it runs; the downside is play lost if cheaper comps did help (slider below)." }),
      base("A-COMP-CHANGE", {
        opts: [0, 1], val: (q) => S3("compLoss").map((loss) => q * (B.comps.extraPerMonth - loss * B.comps.usersTheoPerMonth) * days("A-COMP-CHANGE") / 30),
        basis: "Measured + assumption", why: "May's cheaper comps increased cost, while the measured play response was inconclusive.", how: "Comp cost and comp users' theo against May–Jun.",
        whyNot: `At current assumptions, it saves ${C.usd((B.comps.extraPerMonth - asm.compLoss.mid * B.comps.usersTheoPerMonth) * days("A-COMP-CHANGE") / 30)} in July; restoring old prices could lose play if cheaper comps helped.`,
        target: () => "Back to 15 points per $1 for everyone", href: "comps.html",
        note: "Saves the extra comp cost since May 1; the downside is play lost if cheaper comps did help (slider below)." }),
      base("A-PROMO", {
        opts: range(act["A-PROMO"].quantity_limit), val: (q) => weekend.map((v) => q * v),
        basis: "Measured", why: `The two promotions in the data lifted floor theo $${(weekLong.day / 1000).toFixed(1)}K–$${(tour.day / 1000).toFixed(1)}K a day.`,
        how: "Floor theo on the promotion weekend against the July forecast.",
        whyNot: "", target: (q) => (q > 1 ? "Two weekends, from Jul 18" : "One weekend, from Jul 18"), href: "context.html#ev-h",
        note: `A weekend is three days. Pessimistic: Locals Week's low end (${C.usd(weekLong.lo, { short: true })} a day); central: the two promotions' average; optimistic: the tournament's high end (${C.usd(tour.hi, { short: true })} a day). The 14-day lead leaves two weekends.` }),
      base("A-SURVEY", {
        opts: [0, 1], val: () => [0, 0, 0], basis: "No revenue effect", why: "Better guest data.", how: "–",
        whyNot: "Buys information, not July revenue.", target: () => "One month", href: null, note: "Nothing in the data links a survey to play." }),
    ];
  };

  // quantities worth considering in scenario s: nets that are positive and rise with quantity
  C.planOptions = (models, s) => models.map((m) => {
    const out = []; let best = 0;
    for (const q of m.opts) {
      if (!q || q > m.max) continue;
      const net = m.val(q)[s] - m.cost(q);
      if (net > best + 1e-6) { best = net; out.push({ q, cost: m.cost(q), net }); }
    }
    return { m, out };
  }).filter((x) => x.out.length);

  const allowed = (ids) => !(ids.includes("A-COMP-PILOT") && ids.includes("A-COMP-CHANGE"))
    && !(ids.includes("A-MOVE-BANK") && ids.includes("A-MOVE-MACHINE"));

  // every plan of up to three action types, best net per $500 of spending, then the running best (the frontier)
  C.frontier = (models, s, budget = C.BUDGET, step = 500) => {
    const opts = C.planOptions(models, s), nb = Math.floor(budget / step) + 1;
    const best = Array.from({ length: nb }, () => ({ net: 0, cost: 0, qty: {} }));
    const visit = (i, ids, cost, net, qty) => {
      if (cost > budget) return;
      const k = Math.ceil(cost / step - 1e-9);
      if (k < nb && net > best[k].net + 1e-6) best[k] = { net, cost, qty: { ...qty } };
      if (ids.length === MAX_TYPES) return;
      for (let j = i; j < opts.length; j++) {
        const o = opts[j], id = o.m.id;
        if (!allowed([...ids, id])) continue;
        for (const x of o.out) { qty[id] = x.q; visit(j + 1, [...ids, id], cost + x.cost, net + x.net, qty); delete qty[id]; }
      }
    };
    visit(0, [], 0, 0, {});
    for (let k = 1; k < nb; k++) if (best[k - 1].net > best[k].net) best[k] = best[k - 1];
    return best.map((p, k) => ({ budget: k * step, ...p }));
  };
  C.bestPlan = (models, s, budget) => { const f = C.frontier(models, s, budget); return f[f.length - 1]; };

  // a plan's cost and net in all three scenarios
  C.planValue = (models, qty) => {
    let cost = 0; const net = [0, 0, 0];
    for (const id in qty) {
      const m = models.find((x) => x.id === id); if (!m || !qty[id]) continue;
      const c = m.cost(qty[id]), v = m.val(qty[id]);
      cost += c; for (let s = 0; s < 3; s++) net[s] += v[s] - c;
    }
    return { cost, net };
  };
})();
