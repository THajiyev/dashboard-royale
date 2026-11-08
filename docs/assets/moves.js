/* The floor optimizer as a pure function, so the Actions page can start from the best move plan without a
   visit to the floor plan. Same projection and greedy steps as assets/floor.js (Phase 3 location GLM, bank
   effects): a machine earns perDay × e^(fx_to − fx_home); each step takes the move into an empty slot or the
   swap that adds the most theo per machine moved; stop at the step count with the best net, within the
   catalogue's 24 machine moves. Keep the two in step if either changes. */
(function () {
  "use strict";
  const C = window.Core;
  const LEAD = 2, HORIZON = 30, LIMIT = 24, CURVE_MAX = 48, DAYS = HORIZON - LEAD;

  C.bestMovePlan = (F, M, a, b, price = 1800) => {
    const byId = Object.fromEntries(M.map((m) => [m.id, m]));
    const slotById = Object.fromEntries(F.slots.map((s) => [s.id, s]));
    const bankFx = Object.fromEntries(F.banks.map((x) => [x.id, x.fx]));
    const covIdx = Object.fromEntries(F.bankCov.order.map((x, i) => [x, i]));
    const agg = Object.fromEntries(M.map((m) => [m.id, C.agg(m, a, b)]));
    const base = {}; for (const m of M) if (m.loc[5]) base[m.loc[5]] = m.id;
    const perDay = (mid) => { const s = agg[mid]; return s.days > 0 ? (s.theoHr * s.ah) / s.days : 0; };

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
      const d = bankFx[toBank] - bankFx[fromBank], i = covIdx[fromBank], j = covIdx[toBank], cv = F.bankCov.cov;
      const sd = Math.sqrt(Math.max(0, cv[i][i] + cv[j][j] - 2 * cv[i][j])), pd = perDay(mid);
      return { fromBank, toBank, day: pd * (Math.exp(d) - 1), lo: pd * (Math.exp(d - 1.645 * sd) - 1), hi: pd * (Math.exp(d + 1.645 * sd) - 1) };
    };
    const totals = (at) => {
      const rows = [];
      for (const mid in at) if (at[mid] !== byId[mid].loc[5]) rows.push({ mid, to: at[mid], ...project(mid, at[mid]) });
      const day = rows.reduce((t, r) => t + r.day, 0), half = Math.sqrt(rows.reduce((t, r) => t + ((r.hi - r.lo) / 2) ** 2, 0));
      return { rows, day, lo: day - half, hi: day + half };
    };

    const E = {}; for (const k in bankFx) if (bankFx[k] != null) E[k] = Math.exp(bankFx[k]);
    const okSlot = (s) => s && s.zone !== "Z-HL" && E[s.bank] != null;
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
      steps.push({ n, cum: totals(layoutOf(moves)).day * DAYS, moves: moves.map((x) => ({ ...x })) });
    }
    let k = 0, bestNet = 0;
    steps.forEach((s, i) => { const net = s.cum - s.n * price; if (s.n <= LIMIT && net > bestNet + 1e-6) { bestNet = net; k = i + 1; } });
    const chosen = k ? steps[k - 1].moves : [];
    const T = totals(layoutOf(chosen));
    return {
      moves: chosen,
      summary: { n: T.rows.length, cost: T.rows.length * price, day: T.day, lo: T.lo, hi: T.hi, days: DAYS,
        rows: T.rows.map((r) => ({ m: r.mid, from: r.fromBank, to: r.toBank, day: r.day })) },
    };
  };
})();
