/* The floor optimizer as a pure function, so the Actions page can price machine moves without a visit to the
   floor plan. Same projection and greedy steps as assets/floor.js (Phase 3 location GLM, bank effects): a machine
   earns perDay × e^(fx_to − fx_home); each step takes the move into an empty slot or the swap that adds the most
   theo per machine moved. Keep the two in step if either changes.

   C.moveModel(F, M, a, b) → { steps: [{ n, moves, mid, lo, hi }], summarize(moves), bankSwaps }
     steps     every point on the optimizer's path, July theo over the 28 days after the lead (gross of move cost)
     summarize the same totals for any list of moves (e.g. ones dragged on the floor plan)
     bankSwaps every pair of banks, valued as swapping their positions whole (for A-MOVE-BANK) */
(function () {
  "use strict";
  const C = window.Core;
  const LEAD = 2, HORIZON = 30, CURVE_MAX = 24, DAYS = HORIZON - LEAD;


  C.moveModel = (F, M, a, b) => {
    const byId = Object.fromEntries(M.map((m) => [m.id, m]));
    const slotById = Object.fromEntries(F.slots.map((s) => [s.id, s]));
    const bankFx = Object.fromEntries(F.banks.map((x) => [x.id, x.fx]));
    const bankZone = Object.fromEntries(F.banks.map((x) => [x.id, x.zone]));
    const covIdx = Object.fromEntries(F.bankCov.order.map((x, i) => [x, i]));
    const cv = F.bankCov.cov;
    const agg = Object.fromEntries(M.map((m) => [m.id, C.agg(m, a, b)]));
    const base = {}; for (const m of M) if (m.loc[5]) base[m.loc[5]] = m.id;
    const perDay = (mid) => { const s = agg[mid]; return s.days > 0 ? (s.theoHr * s.ah) / s.days : 0; };
    const pairSd = (A, B) => { const i = covIdx[A], j = covIdx[B]; return Math.sqrt(Math.max(0, cv[i][i] + cv[j][j] - 2 * cv[i][j])); };

    const layoutOf = (moves) => {
      const p = { ...base }, at = {}; for (const s in p) at[p[s]] = s;
      for (const mv of moves) {
        const from = at[mv.m]; if (!from) continue;
        const other = p[mv.to];
        delete p[from];
        if (other) { p[from] = other; at[other] = from; }
        p[mv.to] = mv.m; at[mv.m] = mv.to;
      }
      return at;
    };
    const project = (mid, toSlot) => {
      const m = byId[mid], fromBank = slotById[m.loc[5]].bank, toBank = slotById[toSlot].bank;
      if (fromBank === toBank) return { day: 0, lo: 0, hi: 0, fromBank, toBank };
      const d = bankFx[toBank] - bankFx[fromBank], sd = pairSd(fromBank, toBank), pd = perDay(mid);
      return { fromBank, toBank, day: pd * (Math.exp(d) - 1), lo: pd * (Math.exp(d - 1.645 * sd) - 1), hi: pd * (Math.exp(d + 1.645 * sd) - 1) };
    };
    const summarize = (moves) => {
      const at = layoutOf(moves), rows = [];
      for (const mid in at) if (at[mid] !== byId[mid].loc[5]) rows.push({ mid, to: at[mid], ...project(mid, at[mid]) });
      const day = rows.reduce((t, r) => t + r.day, 0), half = Math.sqrt(rows.reduce((t, r) => t + ((r.hi - r.lo) / 2) ** 2, 0));
      return { n: rows.length, day, lo: day - half, hi: day + half, days: DAYS,
        rows: rows.map((r) => ({ m: r.mid, from: r.fromBank, to: r.toBank, day: r.day })) };
    };

    // greedy path, one step at a time (a move into an empty slot, or a swap of two machines)
    const E = {}; for (const k in bankFx) if (bankFx[k] != null) E[k] = Math.exp(bankFx[k]);
    // B-51 holds the 8 machines installed Mar 24: its "location" effect is mostly those machines being new, so moving
    // machines into or out of it would be valued at an effect that doesn't belong to the spot. Left out, like High-Limit.
    const okSlot = (s) => s && s.zone !== "Z-HL" && !C.NOT_A_SPOT.includes(s.bank) && E[s.bank] != null;
    const home = {}; for (const s in base) home[base[s]] = s;
    const free = new Map();
    for (const mid in home) { const s = slotById[home[mid]]; if (okSlot(s)) free.set(mid, { q: perDay(mid) / E[s.bank], bank: s.bank }); }
    let empty = F.slots.filter((s) => !base[s.id] && okSlot(s)).map((s) => s.id);
    const steps = [], moves = [];
    let n = 0;
    while (n < CURVE_MAX) {
      let best = null;
      const consider = (c) => { if (c.g > 1e-9 && (!best || c.g / c.k > best.g / best.k)) best = c; };
      for (const e of empty) { const Ee = E[slotById[e].bank]; for (const [mid, f] of free) consider({ kind: "move", a: mid, to: e, g: f.q * (Ee - E[f.bank]), k: 1 }); }
      if (n + 2 <= CURVE_MAX) {
        const hi = {}, lo = {};
        for (const [mid, f] of free) {
          if (!hi[f.bank] || f.q > free.get(hi[f.bank]).q) hi[f.bank] = mid;
          if (!lo[f.bank] || f.q < free.get(lo[f.bank]).q) lo[f.bank] = mid;
        }
        const banks = Object.keys(hi);
        for (const A of banks) for (const B of banks) {
          if (E[B] <= E[A]) continue;
          const i = hi[A], j = lo[B];
          consider({ kind: "swap", a: i, b: j, to: home[j], g: (free.get(i).q - free.get(j).q) * (E[B] - E[A]), k: 2 });
        }
      }
      if (!best) break;
      const from = home[best.a];
      moves.push({ m: best.a, to: best.to });
      free.delete(best.a);
      if (best.kind === "swap") free.delete(best.b);
      else { empty = empty.filter((e) => e !== best.to); if (okSlot(slotById[from])) empty.push(from); }
      n += best.k;
      const T = summarize(moves);
      steps.push({ n: T.n, moves: moves.map((x) => ({ ...x })), mid: T.day * DAYS, lo: T.lo * DAYS, hi: T.hi * DAYS });
    }

    // whole-bank swaps: every machine in bank A takes B's position and vice versa
    const members = {}; for (const s in base) { const bk = slotById[s].bank; if (okSlot(slotById[s])) (members[bk] ||= []).push(base[s]); }
    const bankSwaps = [];
    const ids = Object.keys(members);
    for (let i = 0; i < ids.length; i++) for (let j = i + 1; j < ids.length; j++) {
      const A = ids[i], B = ids[j], d = bankFx[B] - bankFx[A], sd = pairSd(A, B);
      const SA = members[A].reduce((t, m) => t + perDay(m), 0), SB = members[B].reduce((t, m) => t + perDay(m), 0);
      const g = (x) => SA * (Math.exp(x) - 1) + SB * (Math.exp(-x) - 1);
      const vals = [g(d - 1.645 * sd), g(d), g(d + 1.645 * sd)];
      bankSwaps.push({ A, B, zoneA: bankZone[A], zoneB: bankZone[B], machines: members[A].length + members[B].length,
        mid: vals[1], lo: Math.min(vals[0], vals[2]), hi: Math.max(vals[0], vals[2]) });
    }
    bankSwaps.sort((x, y) => y.mid - x.mid);
    return { steps, summarize, bankSwaps, days: DAYS };
  };

  // kept for callers that only want the best plan at a price
  C.bestMovePlan = (F, M, a, b, price = 1800) => {
    const mm = C.moveModel(F, M, a, b);
    let best = null, bestNet = 0;
    for (const s of mm.steps) { const net = s.mid - s.n * price; if (net > bestNet) { bestNet = net; best = s; } }
    const moves = best ? best.moves : [], sum = mm.summarize(moves);
    return { moves, summary: { ...sum, cost: sum.n * price } };
  };
})();
