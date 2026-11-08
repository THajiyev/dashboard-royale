/* Floor page: plan drawn from floor_locations x/y, shaded by the chosen measure,
   with drag-to-move projections from the Phase 3 location GLM (bank effects, Jan–Apr fit). */
(function () {
  "use strict";
  const C = window.Core, $ = C.$;
  const LEAD = 2, HORIZON = 30, MOVE_COST = 1800, MOVE_LIMIT = 24, CURVE_MAX = 48; // curve runs past the catalogue cap so the drop-off shows
  const DAYS = HORIZON - LEAD;
  const Y0 = 118; // flip: svg y = Y0 - y_m
  const CELL_W = 1.3, CELL_H = 2.4;
  const DESC = {
    play: "Coin-in per available hour: how much is wagered while the machine can be played",
    rev: "Theo per available hour: expected house win, so luck is taken out",
    luck: "Luck z: house win minus theo, in standard deviations. Beyond ±1.96 happens to 5% of fair machines",
    traffic: "Entries per counted hour at each zone's door sensor. Counters see entries, not unique guests",
  };

  // past/future: snapshots of the move list for undo and redo, each with a label for what the change was
  const S = { metric: "play", a: 0, b: 5, sel: null, zone: null, moves: [], price: MOVE_COST, past: [], future: [] };
  let lines = [];
  let F, M, PF, flags = {}, byId, slotById, bankFx, covIdx, agg, pos, base, opt = { key: null };

  document.addEventListener("DOMContentLoaded", async () => {
    try {
      [F, M, PF] = await Promise.all([C.load("floor"), C.load("machines"), C.load("player_flags")]);
    } catch (e) { return C.fail($("#main"), e); }
    byId = Object.fromEntries(M.map((m) => [m.id, m]));
    slotById = Object.fromEntries(F.slots.map((s) => [s.id, s]));
    bankFx = Object.fromEntries(F.banks.map((b) => [b.id, b.fx]));
    covIdx = Object.fromEntries(F.bankCov.order.map((b, i) => [b, i]));
    base = {}; // June 30 layout: slot -> machine
    for (const m of M) if (m.loc[5]) base[m.loc[5]] = m.id;
    S.moves = C.plan().moves.filter((mv) => byId[mv.m] && slotById[mv.to]);

    [S.a, S.b] = C.periodControl($("#period"), (a, b) => { S.a = a; S.b = b; render(); persist(); });
    try { S.metric = localStorage.getItem("ga-floor-metric") || "play"; } catch { /* */ }
    $("#metric").onclick = (e) => {
      const b = e.target.closest("button"); if (!b) return;
      S.metric = b.dataset.m;
      try { localStorage.setItem("ga-floor-metric", S.metric); } catch { /* */ }
      render();
    };
    try { const p = +localStorage.getItem("ga-move-price"); if (p >= 0 && localStorage.getItem("ga-move-price") !== null) S.price = p; } catch { /* */ }
    const price = $("#move-price");
    price.value = S.price;
    price.oninput = () => {
      const v = Number(price.value);
      if (!(v >= 0) || price.value === "") return;
      S.price = v;
      try { localStorage.setItem("ga-move-price", String(v)); } catch { /* */ }
      persist(); render();
    };
    // both optimize buttons apply the best plan at the current price and show why it stops there
    document.addEventListener("click", (e) => {
      const b = e.target.closest("[data-optimize]"); if (!b) return;
      applyBest();
    });
    $("#mb-undo").onclick = undo;
    $("#mb-redo").onclick = redo;
    $("#mb-reset").onclick = () => {
      const n = planTotals(layout()).rows.length;
      if (S.moves.length) commit([], `Reset ${n} moved machine${n === 1 ? "" : "s"}`);
    };
    document.addEventListener("keydown", (e) => {
      if (!(e.ctrlKey || e.metaKey) || e.altKey || e.target.closest("input, select, textarea")) return;
      const k = e.key.toLowerCase();
      if (k === "z" && !e.shiftKey) { e.preventDefault(); undo(); }
      else if ((k === "z" && e.shiftKey) || k === "y") { e.preventDefault(); redo(); }
    });
    buildFloor();
    render();
    persist(); // keep the action plan's move summary in step with the current period
    addEventListener("themechange", render);
  });

  // ------------------------------------------------------------- layout with moves applied
  function layoutOf(moves) {
    const p = { ...base }; // slot -> machine
    const at = {}; for (const s in p) at[p[s]] = s;
    for (const mv of moves) {
      const from = at[mv.m]; if (!from) continue;
      const other = p[mv.to];
      mv.displaced = other || null;
      delete p[from];
      if (other) { p[from] = other; at[other] = from; }
      p[mv.to] = mv.m; at[mv.m] = mv.to;
    }
    return { at, pos: p };
  }
  function layout() {
    const L = layoutOf(S.moves);
    pos = L.pos;
    return L.at;
  }

  // ------------------------------------------------------------- projection
  function projectMachine(mid, toSlot) {
    const m = byId[mid], fromBank = slotById[m.loc[5]].bank, toBank = slotById[toSlot].bank;
    if (fromBank === toBank) return { day: 0, lo: 0, hi: 0, fromBank, toBank };
    const d = bankFx[toBank] - bankFx[fromBank];
    const i = covIdx[fromBank], j = covIdx[toBank], cv = F.bankCov.cov;
    const sd = Math.sqrt(Math.max(0, cv[i][i] + cv[j][j] - 2 * cv[i][j]));
    const s = agg[mid];
    const perDay = s.days > 0 ? (s.theoHr * s.ah) / s.days : 0; // theo per day on the floor
    return {
      fromBank, toBank, d,
      day: perDay * (Math.exp(d) - 1),
      lo: perDay * (Math.exp(d - 1.645 * sd) - 1),
      hi: perDay * (Math.exp(d + 1.645 * sd) - 1),
    };
  }
  function planTotals(at) {
    const rows = [];
    for (const mid in at) {
      if (at[mid] !== byId[mid].loc[5]) rows.push({ mid, to: at[mid], ...projectMachine(mid, at[mid]) });
    }
    const day = rows.reduce((t, r) => t + r.day, 0);
    const half = Math.sqrt(rows.reduce((t, r) => t + ((r.hi - r.lo) / 2) ** 2, 0));
    return { rows, day, lo: day - half, hi: day + half, cost: rows.length * S.price };
  }

  // ------------------------------------------------------------- optimizer
  // Greedy on the same projection the drag uses: a machine earns perDay × e^(fx_to − fx_home), so with
  // q = perDay × e^(−fx_home) a move is worth q·(E_to − E_home) and a swap (q_i − q_j)(E_j − E_i).
  // Each step takes the operation that adds the most theo per machine moved: a move into an empty slot
  // (one machine) or a swap (two). For a pair of banks the best swap is always the strongest machine
  // in the weaker bank against the weakest machine in the stronger one, so that's all we check.
  // Steps are recorded in order, which is the curve the "when to stop" charts draw.
  function optimize() {
    const key = `${S.a}-${S.b}`;
    if (opt.key === key) return opt.steps;
    const E = {}; for (const b in bankFx) if (bankFx[b] != null) E[b] = Math.exp(bankFx[b]);
    const okSlot = (s) => s && s.zone !== "Z-HL" && E[s.bank] != null;
    const perDay = (mid) => { const s = agg[mid]; return s.days > 0 ? (s.theoHr * s.ah) / s.days : 0; };
    const home = {}; for (const s in base) home[base[s]] = s;
    const free = new Map(); // mid -> { q, bank } for machines still in their Jun 30 slot
    for (const mid in home) {
      const s = slotById[home[mid]];
      if (okSlot(s)) free.set(mid, { q: perDay(mid) / E[s.bank], bank: s.bank });
    }
    let empty = F.slots.filter((s) => !base[s.id] && okSlot(s)).map((s) => s.id);
    const steps = [], moves = [];
    let n = 0, cum = 0;
    while (n < CURVE_MAX) {
      let best = null;
      const consider = (c) => { if (c.g > 1e-9 && (!best || c.g / c.k > best.g / best.k)) best = c; };
      // into an empty slot
      for (const e of empty) {
        const Ee = E[slotById[e].bank];
        for (const [mid, f] of free) consider({ kind: "move", a: mid, to: e, g: f.q * (Ee - E[f.bank]), k: 1 });
      }
      // swaps, two machines
      if (n + 2 <= CURVE_MAX) {
        const hi = {}, lo = {}; // per bank: strongest and weakest free machine
        for (const [mid, f] of free) {
          if (!hi[f.bank] || f.q > free.get(hi[f.bank]).q) hi[f.bank] = mid;
          if (!lo[f.bank] || f.q < free.get(lo[f.bank]).q) lo[f.bank] = mid;
        }
        const banks = Object.keys(hi);
        for (const A of banks) for (const B of banks) {
          if (E[B] <= E[A]) continue; // A weaker, B stronger
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
      const n0 = n; n += best.k;
      const T = planTotals(layoutOf(moves.map((m) => ({ ...m }))).at);
      cum = T.day;
      steps.push({ ...best, from, n0, n, gain: best.g * DAYS, cum: cum * DAYS, lo: T.lo * DAYS, hi: T.hi * DAYS, moves: moves.map(({ m, to }) => ({ m, to })) });
    }
    opt = { key, steps };
    return steps;
  }
  // where to stop: the step count with the best net (theo over July minus move costs), zero moves included,
  // within the catalogue's limit on machine moves
  function stopAt(steps) {
    let k = 0, bestNet = 0;
    steps.forEach((s, i) => { const net = s.cum - s.n * S.price; if (s.n <= MOVE_LIMIT && net > bestNet + 1e-6) { bestNet = net; k = i + 1; } });
    const capped = !!steps[k] && steps[k].gain > steps[k].k * S.price; // the next step would still pay
    return { k, net: bestNet, capped };
  }
  function applyBest() {
    const steps = optimize(), { k } = stopAt(steps);
    S.sel = null;
    commit(k ? steps[k - 1].moves.map((m) => ({ ...m })) : [], k ? `Best plan, ${steps[k - 1].n} machines` : "Best plan, no moves");
  }

  // ------------------------------------------------------------- history: every change to the plan goes through here
  const snap = (moves) => moves.map(({ m, to }) => ({ m, to }));
  const same = (a, b) => a.length === b.length && a.every((x, i) => x.m === b[i].m && x.to === b[i].to);
  function commit(moves, label) {
    if (same(moves, S.moves)) { render(); return; }
    S.past.push({ moves: snap(S.moves), label });
    if (S.past.length > 100) S.past.shift();
    S.future = [];
    S.moves = snap(moves); S.last = label;
    persist(); render();
  }
  function undo() {
    const h = S.past.pop(); if (!h) return;
    S.future.push({ moves: snap(S.moves), label: h.label });
    S.moves = h.moves; S.last = `Undid: ${h.label}`;
    persist(); render();
  }
  function redo() {
    const f = S.future.pop(); if (!f) return;
    S.past.push({ moves: snap(S.moves), label: f.label });
    S.moves = f.moves; S.last = `Redid: ${f.label}`;
    persist(); render();
  }

  // ------------------------------------------------------------- live counter above the plan
  // Net over July = projected theo minus move costs. While dragging, it previews the drop under the pointer.
  let shown = 0, tween = 0;
  const netOf = (T) => T.day * DAYS - T.cost;
  function drawCounter(at, preview) {
    const T = planTotals(at), net = netOf(T);
    const el = $("#mb-count");
    const lastU = S.past[S.past.length - 1], nextR = S.future[S.future.length - 1];
    const u = $("#mb-undo"), r = $("#mb-redo"), x = $("#mb-reset");
    u.disabled = !lastU; u.title = lastU ? `Undo: ${lastU.label} (Ctrl+Z)` : "Nothing to undo";
    r.disabled = !nextR; r.title = nextR ? `Redo: ${nextR.label} (Ctrl+Shift+Z)` : "Nothing to redo";
    x.disabled = !S.moves.length; x.title = "Put every machine back in its Jun 30 slot";
    $("#move-bar").classList.toggle("previewing", !!preview);

    if (preview) {
      if (preview.blocked) { el.innerHTML = `<span class="mb-detail">${C.esc(preview.blocked)}</span>`; return; }
      const P = planTotals(preview.at), d = netOf(P) - net;
      el.innerHTML = `<span class="mb-net">${C.usd(netOf(P), { plus: true })}</span><span class="mb-lbl">net over July if dropped here</span>
        <span class="mb-detail"><span class="mb-delta ${d >= 0 ? "up" : "down"}">${C.usd(d, { plus: true })}</span> ${C.esc(preview.label)}</span>`;
      return;
    }
    if (!T.rows.length) {
      el.innerHTML = `<span class="mb-intro"><strong>Machines can be moved.</strong> Drag one onto another slot to project the change; dropping on an occupied slot swaps the two.</span>`
        + (S.last ? `<span class="mb-detail">${C.esc(S.last)}</span>` : "");
      shown = 0; return;
    }
    el.innerHTML = `<span class="mb-net" id="mb-net">${C.usd(shown, { plus: true })}</span><span class="mb-lbl">net over July</span>
      <span class="mb-detail">${T.rows.length} machine${T.rows.length === 1 ? "" : "s"} moved: ${C.usd(T.day * DAYS, { plus: true })} theo, ${C.usd(-T.cost)} in moves${S.last ? `. ${C.esc(S.last)}` : ""}</span>`;
    // count to the new figure so the change registers; instant when motion is reduced
    const from = shown, to = net, out = $("#mb-net");
    cancelAnimationFrame(tween);
    if (matchMedia("(prefers-reduced-motion: reduce)").matches || from === to) { shown = to; out.textContent = C.usd(to, { plus: true }); return; }
    const t0 = performance.now(), dur = 320;
    const step = (t) => {
      const p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 3);
      shown = from + (to - from) * e;
      out.textContent = C.usd(shown, { plus: true });
      if (p < 1) tween = requestAnimationFrame(step); else shown = to;
    };
    tween = requestAnimationFrame(step);
  }

  // ------------------------------------------------------------- static floor geometry
  // Zone shape = convex hull of its slots, padded by a round-joined stroke.
  function hull(pts) {
    pts = pts.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    const cross = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
    const lo = [], up = [];
    for (const p of pts) { while (lo.length > 1 && cross(lo[lo.length - 2], lo[lo.length - 1], p) <= 0) lo.pop(); lo.push(p); }
    for (const p of pts.reverse()) { while (up.length > 1 && cross(up[up.length - 2], up[up.length - 1], p) <= 0) up.pop(); up.push(p); }
    return lo.slice(0, -1).concat(up.slice(0, -1));
  }
  function zoneShape(z) {
    const ss = F.slots.filter((s) => s.zone === z.id);
    const pts = ss.flatMap((s) => [[s.x, Y0 - s.y - CELL_H / 2], [s.x + CELL_W, Y0 - s.y - CELL_H / 2], [s.x, Y0 - s.y + CELL_H / 2], [s.x + CELL_W, Y0 - s.y + CELL_H / 2]]);
    const h = hull(pts);
    const top = Math.max(...ss.map((s) => s.y));
    const lx = Math.min(...ss.filter((s) => s.y === top).map((s) => s.x));
    return { d: "M" + h.map((p) => p.join(" ")).join("L") + "Z", cx: pts.reduce((t, p) => t + p[0], 0) / pts.length,
      cy: pts.reduce((t, p) => t + p[1], 0) / pts.length, lx, ly: Y0 - top - 5.4 };
  }
  const DOOR = { "L-ENT-MAIN": ["Main door", 0, 4.6], "L-ENT-GAR": ["Garage door", 0, -2.4], "L-ENT-HTL": ["Hotel door", 0, 4.6] };
  let boxes;
  function buildFloor() {
    const svg = $("#floor");
    svg.setAttribute("viewBox", "-6 -5 148 130");
    boxes = Object.fromEntries(F.zones.map((z) => [z.id, zoneShape(z)]));
    svg.innerHTML = `<defs><marker id="arrow" viewBox="0 0 6 6" refX="5" refY="3" markerWidth="4" markerHeight="4" orient="auto"><path d="M0 0L6 3L0 6z" fill="var(--accent)"/></marker></defs>
      <g id="walks"></g><g id="zones-g"></g><g id="slots-g"></g><g id="mach-g"></g><g id="lines-g"></g><g id="flags-g"></g><g id="hot-g"></g><g id="ghost-g"></g>`;
    $("#zones-g").innerHTML = F.zones.map((z) => {
      const b = boxes[z.id];
      return `<g data-zone="${z.id}"><path class="zone-edge" d="${b.d}"/><path class="zone-area" d="${b.d}"/>
        <text class="zone-label" x="${b.lx}" y="${b.ly}">${C.esc(z.name)}<tspan class="zone-sub" dx="1.6" id="zs-${z.id}"></tspan></text></g>`;
    }).join("") + F.entrances.map((e) => {
      const [name, dx, dy] = DOOR[e.id] || [e.id, 0, 4.6];
      return `<g><path class="entr" d="M${e.x - 1.6} ${Y0 - e.y + 1.2}L${e.x} ${Y0 - e.y - 1.2}L${e.x + 1.6} ${Y0 - e.y + 1.2}z"/>
       <title>${name}</title></g>`;
    }).join("");
    $("#slots-g").innerHTML = F.slots.map((s) =>
      `<rect class="slot" data-slot="${s.id}" x="${s.x}" y="${Y0 - s.y - CELL_H / 2}" width="${CELL_W}" height="${CELL_H}" rx=".3"/>`).join("");
    wireDrag(svg);
  }
  function drawWalks() {
    const closedInPeriod = S.a <= 3 && S.b >= 2; // Mar–Apr
    $("#walks").innerHTML = F.walkways.map((w) => {
      const A = boxes[w.a], B = boxes[w.b];
      const closed = w.closed && closedInPeriod;
      return `<path class="walk ${closed ? "closed" : ""}" d="M${A.cx} ${A.cy}L${B.cx} ${B.cy}"><title>${w.id}${w.closed ? ", closed Mar 3 – Apr 6 for renovation" : ""}</title></path>`;
    }).join("");
  }

  // ------------------------------------------------------------- colour
  const SEQ = ["--seq-0", "--seq-1", "--seq-2", "--seq-3", "--seq-4", "--seq-5"];
  const DIV = [["--div-neg", -Infinity, -1.96], ["--div-neg-2", -1.96, -1], ["--div-mid", -1, 1], ["--div-pos-2", 1, 1.96], ["--div-pos", 1.96, Infinity]];
  function quantiles(vals, k) {
    const v = vals.filter((x) => x != null && isFinite(x)).sort((p, q) => p - q);
    return Array.from({ length: k - 1 }, (_, i) => v[Math.floor(((i + 1) / k) * (v.length - 1))]);
  }
  function colorFn(metric, at) {
    if (metric === "luck") {
      const col = DIV.map(([v]) => C.css(v));
      return { fn: (s) => col[DIV.findIndex(([, lo, hi]) => s.z >= lo && s.z < hi)],
        legend: `<span>Luck z</span>${DIV.map(([v, lo, hi], i) => `<span style="display:inline-flex;align-items:center;gap:4px"><i style="width:10px;height:10px;border-radius:3px;background:${col[i]};display:inline-block"></i>${
          lo === -Infinity ? "< −1.96" : hi === Infinity ? "> 1.96" : `${C.num(lo, lo % 1 ? 2 : 0)} to ${C.num(hi, hi % 1 ? 2 : 0)}`}</span>`).join("")}
          <span class="muted">blue = house got lucky</span>` };
    }
    const key = metric === "play" ? "ciHr" : "theoHr";
    const vals = Object.keys(at).map((id) => agg[id][key]);
    const cuts = quantiles(vals, 6), col = SEQ.map(C.css);
    const label = metric === "play" ? "Coin-in per hour" : "Theo per hour";
    return { fn: (s) => { const v = s[key]; let i = 0; while (i < cuts.length && v > cuts[i]) i++; return col[i]; },
      legend: `<span>${label}</span><span>${C.usd(Math.min(...vals.filter(Number.isFinite)))}</span>
        <span class="ramp" style="background:linear-gradient(90deg,${col.join(",")})"></span>
        <span>${C.usd(Math.max(...vals.filter(Number.isFinite)))}</span><span class="muted">sixths of machines</span>` };
  }

  // ------------------------------------------------------------- render
  function render() {
    C.$$("#metric button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.m === S.metric));
    $("#metric-desc").textContent = DESC[S.metric] + ", " + C.periodLabel(S.a, S.b) + ".";
    $("#title").textContent = `Floor plan, ${C.periodLabel(S.a, S.b)}`;
    agg = Object.fromEntries(M.map((m) => [m.id, C.agg(m, S.a, S.b)]));
    flags = C.machineFlags(M, S.a, S.b, PF);
    const at = layout();
    drawWalks();
    drawStats(at);

    // traffic: zone areas carry the colour
    const tr = Object.fromEntries(Object.entries(F.traffic).map(([z, v]) => {
      const xs = v.slice(S.a, S.b + 1).filter((x) => x != null);
      return [z, xs.reduce((t, x) => t + x, 0) / (xs.length || 1)];
    }));
    const trCuts = quantiles(Object.values(tr), 6), seq = SEQ.map(C.css);
    C.$$("#zones-g > g[data-zone]").forEach((g) => {
      const z = g.dataset.zone, rect = g.querySelector(".zone-area");
      if (S.metric === "traffic") { let i = 0; while (i < trCuts.length && tr[z] > trCuts[i]) i++; rect.style.fill = rect.style.stroke = seq[Math.min(i, 5)]; }
      else { rect.style.fill = rect.style.stroke = ""; }
      rect.style.opacity = S.zone && S.zone !== z ? ".45" : "";
      $(`#zs-${z}`).textContent = S.metric === "traffic" ? `${C.num(tr[z], 0)} entries/h` : "";
    });

    const { fn, legend } = S.metric === "traffic"
      ? { fn: () => C.css("--ink-3"), legend: `<span>Entries per counted hour</span><span>${C.num(Math.min(...Object.values(tr)), 0)}</span><span class="ramp" style="background:linear-gradient(90deg,${seq.join(",")})"></span><span>${C.num(Math.max(...Object.values(tr)), 0)}</span>` }
      : colorFn(S.metric, at);
    $("#scale").innerHTML = legend;

    C.$$("#slots-g .slot").forEach((r) => r.classList.toggle("filled", !!pos[r.dataset.slot]));
    $("#mach-g").innerHTML = Object.entries(at).map(([mid, sl]) => {
      const s = slotById[sl], m = byId[mid];
      const moved = sl !== m.loc[5], dim = S.zone && s.zone !== S.zone;
      return `<rect class="m${m.b10 ? " b10" : ""}${moved ? " moved" : ""}${S.sel === mid ? " sel" : ""}${dim ? " dim" : ""}" data-m="${mid}"
        x="${s.x}" y="${Y0 - s.y - CELL_H / 2}" width="${CELL_W}" height="${CELL_H}" rx=".3" fill="${fn(agg[mid])}"
        ${S.metric === "traffic" ? 'fill-opacity=".35"' : ""} tabindex="-1"/>`;
    }).join("");
    // each move is a bowed curve, origin dot to arrow; the two legs of a swap bow to opposite sides
    lines = Object.entries(at).filter(([mid, sl]) => sl !== byId[mid].loc[5]).map(([mid, sl]) => {
      const f = slotById[byId[mid].loc[5]], t = slotById[sl];
      return { mid, from: f, to: t, g: curve(f, t) };
    });
    $("#lines-g").innerHTML = lines.map((l) => `<path class="move-line" data-m="${l.mid}" d="M${l.g.x1} ${l.g.y1}Q${l.g.cx} ${l.g.cy} ${l.g.x2} ${l.g.y2}"/>
      <circle class="move-from" data-m="${l.mid}" cx="${l.g.x1}" cy="${l.g.y1}" r=".45"/>`).join("");
    hotLine(S.hot && lines.some((l) => l.mid === S.hot) ? S.hot : null);
    // flag markers: filled red dot = flagged, red ring = watch; drawn above the cell so the shading stays readable
    $("#flags-g").innerHTML = Object.entries(at).filter(([mid]) => flags[mid]).map(([mid, sl]) => {
      const s = slotById[sl], f = flags[mid], cx = s.x + CELL_W / 2, cy = Y0 - s.y - CELL_H / 2 - 1.1;
      return f.level === "flag"
        ? `<circle class="flag-dot" cx="${cx}" cy="${cy}" r=".75"><title>${mid}: ${C.esc(f.reasons.join("; "))}</title></circle>`
        : `<circle class="flag-ring" cx="${cx}" cy="${cy}" r=".6"><title>${mid}: ${C.esc(f.reasons.join("; "))}</title></circle>`;
    }).join("");
    drawDetail(); drawPlan(at); drawCounter(at); drawStop(at); drawZones(at, tr);
  }

  // ------------------------------------------------------------- when to stop
  function drawStop(at) {
    const steps = optimize(), { k, net, capped } = stopAt(steps), P = S.price;
    const mine = planTotals(at);
    const nMax = steps.length ? steps[steps.length - 1].n : 0;
    const desc = (s) => s.kind === "swap"
      ? `Swap ${s.a} (bank ${slotById[s.from].bank.slice(2)}) with ${s.b} (bank ${slotById[s.to].bank.slice(2)})`
      : `Move ${s.a} from bank ${slotById[s.from].bank.slice(2)} to the empty slot in bank ${slotById[s.to].bank.slice(2)}`;

    // the answer, in words
    const next = steps[k];
    const best = k ? steps[k - 1] : null;
    const mineBest = steps.filter((s) => s.n <= mine.rows.length).pop();
    $("#stop-answer").innerHTML = !steps.length
      ? `No move improves on the Jun 30 layout for ${C.periodLabel(S.a, S.b)}.`
      : (k
        ? `<strong>Stop after ${best.n} machine${best.n === 1 ? "" : "s"}.</strong> That adds ${C.usd(best.cum, { plus: true })} theo over July's ${DAYS} days for ${C.usd(best.n * P)}, net ${C.usd(net, { plus: true })}.`
        : `<strong>Don't move anything at ${C.usd(P)} a move.</strong> The best single step adds ${C.usd(steps[0].gain / steps[0].k)} per machine, less than it costs.`)
        + (next ? (capped
          ? ` That's the catalogue's limit of ${MOVE_LIMIT} machine moves; the next step would still add ${C.usd(next.gain)} for ${C.usd(next.k * P)}.`
          : ` The next step, ${next.kind === "swap" ? "a swap of two machines" : "one more machine"}, would add only ${C.usd(next.gain)} for ${C.usd(next.k * P)}.`) : "")
        + (mine.rows.length && S.moves.length
          ? ` Your plan on the floor now: ${mine.rows.length} machine${mine.rows.length === 1 ? "" : "s"}, net ${C.usd(mine.day * DAYS - mine.cost, { plus: true })}${mineBest ? `; the best ${mineBest.n}-machine plan nets ${C.usd(mineBest.cum - mineBest.n * P, { plus: true })}` : ""}.`
          : "");
    const applied = best && S.moves.length === best.moves.length && best.moves.every((m, i) => S.moves[i] && S.moves[i].m === m.m && S.moves[i].to === m.to);
    const btn = $("#stop-apply");
    btn.disabled = !k || applied;
    btn.textContent = !k ? "Nothing worth moving" : applied ? `${best.n}-machine plan is on the floor` : `Put the ${best.n}-machine plan on the floor`;
    btn.onclick = () => { applyBest(); };
    // once the best plan is on the floor (or the best plan is to move nothing and nothing is moved), the optimize buttons have nothing left to do
    const found = k ? applied : !S.moves.length && steps.length > 0;
    C.$$("[data-optimize]").forEach((b) => {
      b.disabled = found;
      b.title = found ? (k ? `The best ${best.n}-machine plan is already on the floor` : "Nothing is worth moving at this price") : "";
    });

    if (!steps.length) { $("#stop-bars").innerHTML = ""; $("#stop-net").innerHTML = ""; return; }

    // chart 1: what each step adds per machine moved, against the price of a move
    const svg = $("#stop-bars");
    const W = Math.max(300, svg.clientWidth || 600), H = 240, Pd = { l: 56, r: 12, t: 20, b: 32 };
    const perM = steps.map((s) => s.gain / s.k);
    const yMax = C.niceMax(Math.max(P * 1.15, ...perM));
    const x = C.scale(0, nMax, Pd.l, W - Pd.r), y = C.scale(0, yMax, H - Pd.b, Pd.t);
    let g = "";
    const tick = yMax / 4;
    for (let v = 0; v <= yMax + 1e-6; v += tick) g += `<line x1="${Pd.l}" x2="${W - Pd.r}" y1="${y(v)}" y2="${y(v)}" stroke="var(--grid)"/><text x="${Pd.l - 8}" y="${y(v) + 4}" text-anchor="end">${C.usd(v, { short: true })}</text>`;
    const xStep = nMax > 12 ? 4 : nMax > 6 ? 2 : 1;
    for (let n = 0; n <= nMax; n += xStep) g += `<text x="${x(n)}" y="${H - 12}" text-anchor="middle">${n}</text>`;
    g += `<text x="${W - Pd.r}" y="${H}" text-anchor="end">machines moved</text>`;
    steps.forEach((s, i) => {
      const keep = i < k, gap = 1.5;
      g += `<rect class="stop-bar" data-i="${i}" x="${x(s.n0) + gap}" y="${y(perM[i])}" width="${Math.max(1, x(s.n) - x(s.n0) - 2 * gap)}" height="${y(0) - y(perM[i])}" rx="2"
        fill="${keep ? "var(--accent)" : "var(--ink-3)"}" fill-opacity="${keep ? 1 : 0.3}"/>`;
    });
    const halo = "paint-order:stroke;stroke:var(--card);stroke-width:4px;stroke-linejoin:round";
    const vlabel = (xx, text, color) => `<text x="${xx > W - 90 ? xx - 6 : xx + 6}" y="${Pd.t - 4}" text-anchor="${xx > W - 90 ? "end" : "start"}" style="fill:${color};${halo}">${text}</text>`;
    if (nMax > MOVE_LIMIT && (!k || best.n !== MOVE_LIMIT)) g += `<line x1="${x(MOVE_LIMIT)}" x2="${x(MOVE_LIMIT)}" y1="${Pd.t + 10}" y2="${y(0)}" stroke="var(--ink-3)" stroke-dasharray="2 3"/>
      <text x="${x(MOVE_LIMIT) + 6}" y="${Pd.t + 18}" style="fill:var(--ink-3);${halo}">Catalogue limit, ${MOVE_LIMIT}</text>`;
    g += `<line x1="${Pd.l}" x2="${W - Pd.r}" y1="${y(P)}" y2="${y(P)}" stroke="var(--neg)" stroke-width="1.5" stroke-dasharray="5 4"/>
      <text x="${W - Pd.r}" y="${y(P) - 6}" text-anchor="end" style="fill:var(--neg);font-weight:600;${halo}">${C.usd(P)} a move</text>`;
    if (k) g += `<line x1="${x(best.n)}" x2="${x(best.n)}" y1="${Pd.t - 2}" y2="${y(0)}" stroke="var(--ink)" stroke-width="1"/>
      ${vlabel(x(best.n), best.n === MOVE_LIMIT && capped ? "Stop here, catalogue limit" : "Stop here", "var(--ink)")}`;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.innerHTML = g;
    svg.onmousemove = (e) => {
      const r = e.target.closest(".stop-bar"); if (!r) return C.tip(null);
      const s = steps[+r.dataset.i];
      C.tip(C.tipRows(`Step ${+r.dataset.i + 1}, machines ${s.n0 + 1}${s.k > 1 ? `–${s.n}` : ""}`, [
        ["Adds over July", C.usd(s.gain, { plus: true })], ["Per machine moved", C.usd(s.gain / s.k)], ["Costs", C.usd(s.k * P)],
      ]) + `<div class="small muted" style="margin-top:4px">${desc(s)}</div>`, e);
    };
    svg.onmouseleave = () => C.tip(null);

    // chart 2: net over July after move costs, with the 90% model range
    const nv = $("#stop-net");
    const W2 = Math.max(300, nv.clientWidth || 600), H2 = 240;
    const pts = [{ n: 0, net: 0, lo: 0, hi: 0 }].concat(steps.map((s) => ({ n: s.n, net: s.cum - s.n * P, lo: s.lo - s.n * P, hi: s.hi - s.n * P })));
    const vMin = Math.min(0, ...pts.map((p) => p.lo)), vMax = Math.max(1, ...pts.map((p) => p.hi));
    const span = C.niceMax(vMax - vMin);
    const t2 = span / 4, y0 = Math.floor(vMin / t2) * t2;
    const x2 = C.scale(0, nMax, Pd.l, W2 - Pd.r), y2 = C.scale(y0, Math.max(vMax, y0 + span), H2 - Pd.b, Pd.t);
    let h = "";
    for (let v = y0; v <= Math.max(vMax, y0 + span) + 1e-6; v += t2) h += `<line x1="${Pd.l}" x2="${W2 - Pd.r}" y1="${y2(v)}" y2="${y2(v)}" stroke="${Math.abs(v) < 1e-6 ? "var(--ink-3)" : "var(--grid)"}"/><text x="${Pd.l - 8}" y="${y2(v) + 4}" text-anchor="end">${C.usd(v, { short: true, plus: v > 0 })}</text>`;
    for (let n = 0; n <= nMax; n += xStep) h += `<text x="${x2(n)}" y="${H2 - 12}" text-anchor="middle">${n}</text>`;
    h += `<text x="${W2 - Pd.r}" y="${H2}" text-anchor="end">machines moved</text>`;
    const line = (arr) => arr.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join("");
    h += `<path d="${line(pts.map((p) => [x2(p.n), y2(p.hi)]).concat(pts.slice().reverse().map((p) => [x2(p.n), y2(p.lo)])))}Z" fill="var(--band)"/>`;
    h += `<path d="${line(pts.map((p) => [x2(p.n), y2(p.net)]))}" fill="none" stroke="var(--accent)" stroke-width="2" stroke-linejoin="round"/>`;
    h += pts.map((p, i) => `<circle class="net-pt" data-i="${i}" cx="${x2(p.n)}" cy="${y2(p.net)}" r="${i === k ? 5 : 3}" fill="${i === k ? "var(--accent)" : "var(--card)"}" stroke="var(--accent)" stroke-width="1.5"/>`).join("");
    if (k) h += `<text x="${x2(best.n)}" y="${y2(net) - 12}" text-anchor="middle" style="fill:var(--ink);font-weight:600;paint-order:stroke;stroke:var(--card);stroke-width:4px">${C.usd(net, { plus: true, short: true })}</text>`;
    if (nMax > MOVE_LIMIT) h += `<line x1="${x2(MOVE_LIMIT)}" x2="${x2(MOVE_LIMIT)}" y1="${Pd.t}" y2="${H2 - Pd.b}" stroke="var(--ink-3)" stroke-dasharray="2 3"><title>Catalogue limit, ${MOVE_LIMIT} machine moves</title></line>`;
    if (mine.rows.length && S.moves.length) {
      const mx = x2(Math.min(nMax, mine.rows.length)), my = y2(mine.day * DAYS - mine.cost);
      h += `<path d="M${mx - 5} ${my - 5}L${mx + 5} ${my + 5}M${mx - 5} ${my + 5}L${mx + 5} ${my - 5}" stroke="var(--ink)" stroke-width="1.5"><title>Your plan on the floor</title></path>`;
    }
    nv.setAttribute("viewBox", `0 0 ${W2} ${H2}`);
    nv.innerHTML = h;
    nv.onmousemove = (e) => {
      const c = e.target.closest(".net-pt"); if (!c) return C.tip(null);
      const i = +c.dataset.i, p = pts[i];
      C.tip(C.tipRows(i ? `After step ${i}, ${p.n} machine${p.n === 1 ? "" : "s"} moved` : "No moves", [
        ["Net over July", C.usd(p.net, { plus: true })], ["90% model range", `${C.usd(p.lo, { plus: true })} to ${C.usd(p.hi, { plus: true })}`], ["Move costs", C.usd(p.n * P)],
      ]) + (i ? `<div class="small muted" style="margin-top:4px">${desc(steps[i - 1])}</div>` : ""), e);
    };
    nv.onmouseleave = () => C.tip(null);
  }

  function drawStats(at) {
    const ids = Object.keys(at);
    const all = M.map((m) => agg[m.id]);
    const sum = (k, arr = all) => arr.reduce((t, s) => t + s[k], 0);
    const theoHr = sum("theo") / sum("ah"), avail = sum("ah") / (sum("ah") + sum("dh"));
    const luck = sum("luck"), z = luck / Math.sqrt(sum("var"));
    const b40 = M.filter((m) => agg[m.id].ah > 0 && slotById[agg[m.id].loc]?.zone === "Z-B40").map((m) => agg[m.id]);
    const b40hr = sum("theo", b40) / sum("ah", b40);
    $("#stats").innerHTML = [
      ["Theo per available hour", C.usd(theoHr, { d: 2 }), `Expected win, all ${C.int(all.filter((s) => s.ah > 0).length)} machines that played`],
      ["Availability", C.pct(avail), `${C.int(sum("dh"))} machine-hours down`],
      ["Luck, house win − theo", C.usd(luck, { short: true, plus: true }), `z ${C.num(z, 1, true)} across the floor, ${Math.abs(z) < 1.96 ? "inside normal swings" : "outside normal swings"}`],
      ["Back Forty theo per hour", C.usd(b40hr, { d: 2 }), `${C.pct(b40hr / theoHr - 1, 0, true)} vs the floor average`],
    ].map(([l, v, f], i) => `<div class="stat"><div class="label">${l}</div><div class="value${i === 3 ? " accent" : ""}">${v}</div><div class="foot">${f}</div></div>`).join("");
  }

  function drawDetail() {
    const el = $("#detail");
    if (!S.sel) {
      // empty state: the review's findings, each one a click away on this plan or another page
      const red = Object.entries(flags).filter(([, f]) => f.level === "flag").map(([id]) => id);
      const nWatch = Object.values(flags).filter((f) => f.level === "watch").length;
      const b40 = M.filter((m) => m.b10 && m.zone === "Z-B40").length;
      const go = (t) => `<span class="go">${t}</span>`;
      el.innerHTML = `<h3>Start here</h3><p class="muted" style="margin:4px 0 0">What the review found, ${C.periodLabel(S.a, S.b)}.</p>
        <ul class="start">
          ${red.length ? `<li><button type="button" data-pick="${red[0]}"><span class="t"><span class="dot lead"></span>${red.length === 1 ? `<span class="mono">${red[0]}</span> pays out off its configuration` : `${red.length} machines flagged`}</span>
            <span class="d">The only flag that survives correction for testing 310 machines.${nWatch ? ` ${nWatch} more are on watch.` : ""}</span>${go("Show")}</button></li>` : ""}
          <li><button type="button" data-zone="Z-B40"><span class="t">${b40} of the GM's bottom 10 are in Back Forty</span>
            <span class="d">The zone furthest from the entrances. Location explains them better than the machines do.</span>${go("Show")}</button></li>
          <li><a href="comps.html${location.search}"><span class="t">Comps got 53% cheaper on May 1</span>
            <span class="d">A floor-wide price cut with no control group; play didn't rise with it.</span>${go("Comps")}</a></li>
          <li><a href="actions.html${location.search}"><span class="t">The $100,000 plan for July</span>
            <span class="d">Three funded fixes, each with its effect, uncertainty and how to measure it.</span>${go("Actions")}</a></li>
        </ul>
        <p class="start-hint">Hover a machine for its figures, select it to pin them here. Drag it onto another slot to project a move;
          dropping on an occupied slot swaps the two.</p>`;
      el.onclick = (e) => {
        const p = e.target.closest("[data-pick]"), z = e.target.closest("[data-zone]");
        if (p) { S.sel = p.dataset.pick; render(); }
        else if (z) { S.zone = S.zone === z.dataset.zone ? null : z.dataset.zone; render(); }
      };
      return;
    }
    const m = byId[S.sel], s = agg[S.sel], sl = slotById[m.loc[5]];
    const zn = F.zones.find((z) => z.id === sl?.zone)?.name ?? "–";
    el.onclick = (e) => { if (e.target.closest("[data-clear]")) { S.sel = null; render(); } };
    el.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center;gap:8px"><h3 class="mono" style="margin:0">${m.id}</h3>
        <button class="btn" type="button" data-clear aria-label="Clear the selection and go back to Start here">${C.icon("x", 14)}Clear</button></div>
      <div class="muted">${C.esc(m.theme)}, ${C.esc(m.mfr)}, ${zn}, bank ${sl?.bank.slice(2) ?? "–"}</div>
      <dl class="kv">
        <dt>Coin-in per available hour</dt><dd>${C.usd(s.ciHr)}</dd>
        <dt>Theo per available hour</dt><dd>${C.usd(s.theoHr, { d: 2 })}</dd>
        <dt>Availability</dt><dd>${C.pct(s.avail)}</dd>
        <dt>Days on the floor</dt><dd>${s.days}</dd>
        <dt>Luck</dt><dd>${C.usd(s.luck, { plus: true })}, z ${C.num(s.z, 2, true)}</dd>
        <dt>Bank location effect</dt><dd>${C.pct(Math.exp(bankFx[sl?.bank] ?? 0) - 1, 0, true)}</dd>
      </dl>
      <div style="margin-top:12px;display:flex;align-items:center;gap:12px">${C.holdBand(s, { w: 140 })}<span class="small muted">hold ${C.pct(s.hold)} vs ${C.pct(s.theoHold)} configured</span></div>
      ${flags[m.id] ? `<div style="margin-top:16px">${C.flagTag(flags[m.id])}<ul class="small" style="margin:6px 0 0;padding-left:18px;color:var(--ink-2)">${flags[m.id].reasons.map((x) => `<li>${C.esc(x)}</li>`).join("")}</ul></div>` : ""}
      ${m.b10 ? `<p class="callout" style="margin-top:16px"><strong style="color:var(--ink);font-weight:500">GM's bottom 10, rank ${m.b10.rank}.</strong> ${C.esc(m.b10.verdict)}. ${C.esc(m.b10.action)}.</p>` : ""}
      <p class="small" style="margin:12px 0 0"><a href="machines.html${location.search}#${m.id}">See it in the luck ranking</a></p>`;
  }

  function drawPlan(at) {
    const T = planTotals(at);
    const el = $("#plan");
    const over = T.rows.length > MOVE_LIMIT;
    el.innerHTML = `<h3>Move plan for July</h3>
      <p class="muted" style="margin:4px 0 0">${C.usd(S.price)} a machine, ${LEAD}-day lead, so ${DAYS} days of effect in July.</p>
      ${T.rows.length ? `<ul class="moves">${T.rows.map((r) => `<li data-line="${r.mid}">
          <span><span class="mono">${r.mid}</span><span class="sub small muted">${r.fromBank} → ${r.toBank}${(slotById[r.to].zone === "Z-B40") ? ", into Back Forty" : ""}</span></span>
          <span class="num ${r.day >= 0 ? "" : "muted"}">${C.usd(r.day, { plus: true })}/day</span>
          <button type="button" data-undo="${r.mid}" aria-label="Put ${r.mid} back" title="Put ${r.mid} back">${C.icon("x", 14)}</button></li>`).join("")}</ul>
        <div class="total-row"><span class="muted">Projected theo, ${DAYS} days</span><span class="big">${C.usd(T.day * DAYS, { plus: true })}</span></div>
        <div class="small muted" style="text-align:right">90% range ${C.usd(T.lo * DAYS, { plus: true })} to ${C.usd(T.hi * DAYS, { plus: true })}</div>
        <div class="total-row"><span class="muted">Cost</span><span class="num">${C.usd(T.cost)} of ${C.usd(C.BUDGET)}</span></div>
        <div class="meter" aria-hidden="true"><span style="transform:scaleX(${Math.min(1, T.cost / C.BUDGET)})"></span></div>
        ${over ? `<p class="note" style="color:var(--neg)">The catalogue allows ${MOVE_LIMIT} machine moves; this plan has ${T.rows.length}.</p>` : ""}
        <div style="display:flex;gap:8px;margin-top:16px;flex-wrap:wrap">
          <a class="btn primary" href="actions.html${location.search}" style="text-decoration:none">Open the action plan ${C.icon("arrow", 14)}</a></div>`
        : `<p class="empty">No moves yet. Drag a machine onto another slot to price a move, or let the optimizer pick the moves that pay for themselves.</p>
          <button class="btn primary" type="button" data-optimize="scroll">Find the best moves</button>`}
      <p class="note">Projection: the machine's own theo per day × the change in bank effect from the location model (fit Jan–Apr).
        Back-test on the one real move, M-1152 from Back Forty to the Entrance on Feb 4: predicted <span class="mono">+$303</span>/day,
        measured <span class="mono">+$342</span>/day (90% CI <span class="mono">+$188</span> to <span class="mono">+$497</span>).
        The range shown covers model uncertainty only, so it is narrower than what a real move will show.
        High-Limit Room slots are locked: its clientele and games don't exist elsewhere.</p>`;
    el.onclick = (e) => {
      const u = e.target.closest("[data-undo]");
      if (u) { undoMachine(u.dataset.undo); return; }
    };
    // pointing at a row in the list lights its line on the plan
    el.onmouseover = (e) => { const li = e.target.closest("li[data-line]"); hotLineIfChanged(li ? li.dataset.line : null); };
    el.onmouseleave = () => hotLineIfChanged(null);
  }
  function undoMachine(mid) {
    // rebuild the move list without any move that touched this machine's final slot chain
    layout(); // refreshes mv.displaced
    commit(S.moves.filter((mv) => mv.m !== mid && mv.displaced !== mid), `Put ${mid} back`);
  }
  function persist() {
    const p = C.plan();
    const at = layout();
    p.moves = S.moves.map(({ m, to }) => ({ m, to }));
    p.moveSummary = (() => { const T = planTotals(at); return { n: T.rows.length, cost: T.cost, day: T.day, lo: T.lo, hi: T.hi, days: DAYS,
      rows: T.rows.map((r) => ({ m: r.mid, from: r.fromBank, to: r.toBank, day: r.day })) }; })();
    C.savePlan(p);
  }

  function drawZones(at, tr) {
    const rows = F.zones.map((z) => {
      const ms = M.filter((m) => agg[m.id].ah > 0 && slotById[agg[m.id].loc]?.zone === z.id).map((m) => agg[m.id]);
      const sum = (k) => ms.reduce((t, s) => t + s[k], 0);
      const fx = F.banks.filter((b) => b.zone === z.id && b.fx != null).map((b) => Math.exp(b.fx) - 1);
      return { z, n: Object.values(at).filter((sl) => slotById[sl].zone === z.id).length, ciHr: sum("ci") / sum("ah"),
        theoHr: sum("theo") / sum("ah"), avail: sum("ah") / (sum("ah") + sum("dh")), luck: sum("luck"),
        tr: tr[z.id], fxLo: Math.min(...fx), fxHi: Math.max(...fx), b10: M.filter((m) => m.b10 && slotById[m.loc[5]]?.zone === z.id).length };
    }).sort((p, q) => q.theoHr - p.theoHr);
    $("#zones").innerHTML = `<thead><tr><th>Zone</th><th class="num">Machines Jun 30</th><th class="num">Coin-in / hour</th><th class="num">Theo / hour</th>
      <th class="num">Availability</th><th class="num">Entries / hour</th><th class="num">Bank effects</th><th class="num">Luck</th><th class="num">GM's bottom 10</th></tr></thead>
      <tbody>${rows.map((r) => `<tr class="clickable ${S.zone === r.z.id ? "on" : ""}" data-z="${r.z.id}" tabindex="0">
        <td>${C.esc(r.z.name)}</td><td class="num">${r.n}</td><td class="num">${C.usd(r.ciHr)}</td><td class="num">${C.usd(r.theoHr, { d: 2 })}</td>
        <td class="num">${C.pct(r.avail)}</td><td class="num">${C.num(r.tr, 0)}</td>
        <td class="num">${C.pct(r.fxLo, 0, true)} to ${C.pct(r.fxHi, 0, true)}</td><td class="num">${C.usd(r.luck, { short: true, plus: true })}</td>
        <td class="num">${r.b10 || ""}</td></tr>`).join("")}</tbody>`;
    const pick = (tr) => { S.zone = S.zone === tr.dataset.z ? null : tr.dataset.z; render(); };
    $("#zones").onclick = (e) => { const tr = e.target.closest("tr[data-z]"); if (tr) pick(tr); };
    $("#zones").onkeydown = (e) => { const tr = e.target.closest("tr[data-z]"); if (tr && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); pick(tr); } };
  }

  // ------------------------------------------------------------- hover + drag
  function svgPoint(svg, e) {
    const p = svg.createSVGPoint(); p.x = e.clientX; p.y = e.clientY;
    return p.matrixTransform(svg.getScreenCTM().inverse());
  }
  function nearestSlot(pt) {
    let best = null, bd = 9;
    for (const s of F.slots) {
      const dx = s.x + CELL_W / 2 - pt.x, dy = Y0 - s.y - pt.y, d = dx * dx + dy * dy;
      if (d < bd) { bd = d; best = s; }
    }
    return best;
  }
  function tipFor(mid, e) {
    const m = byId[mid], s = agg[mid], sl = slotById[layout()[mid]];
    const zn = F.zones.find((z) => z.id === sl.zone)?.name;
    C.tip(C.tipRows(`<span class="mono">${m.id}</span>, ${C.esc(m.theme)}`, [
      ["Zone, bank", `${zn}, ${sl.bank.slice(2)}`], ["Coin-in / hour", C.usd(s.ciHr)], ["Theo / hour", C.usd(s.theoHr, { d: 2 })],
      ["Luck", `${C.usd(s.luck, { plus: true })} (z ${C.num(s.z, 1, true)})`], ["Availability", C.pct(s.avail)],
    ]) + (flags[mid] ? `<div class="small" style="margin-top:4px;color:var(--neg)">${flags[mid].level === "flag" ? "Flagged" : "Watch"}: ${C.esc(flags[mid].reasons[0])}</div>` : "")
      + (m.b10 ? `<div class="small muted" style="margin-top:4px">GM's bottom 10, rank ${m.b10.rank}</div>` : ""), e);
  }
  function wireDrag(svg) {
    let drag = null;
    svg.addEventListener("pointermove", (e) => {
      if (drag) {
        const pt = svgPoint(svg, e);
        if (!drag.moving && Math.hypot(e.clientX - drag.x0, e.clientY - drag.y0) < 4) return;
        if (!drag.moving) { drag.moving = true; C.tip(null); svg.setPointerCapture(e.pointerId); }
        $("#ghost-g").innerHTML = `<rect class="ghost" x="${pt.x - CELL_W / 2}" y="${pt.y - CELL_H / 2}" width="${CELL_W}" height="${CELL_H}" rx=".3"/>`;
        const s = nearestSlot(pt);
        C.$$("#slots-g .slot.drop, #slots-g .slot.blocked").forEach((r) => r.classList.remove("drop", "blocked"));
        const ok = s && okTarget(drag.mid, s);
        if (s) svg.querySelector(`[data-slot="${s.id}"]`).classList.add(ok ? "drop" : "blocked");
        if (s?.id !== drag.target?.id) previewDrop(drag.mid, s, ok);
        drag.target = s;
        return;
      }
      const r = e.target.closest(".m");
      if (r) {
        tipFor(r.dataset.m, e);
        hotLineIfChanged(lines.some((l) => l.mid === r.dataset.m) ? r.dataset.m : null);
        return;
      }
      const l = lineAt(svgPoint(svg, e));
      hotLineIfChanged(l ? l.mid : null);
      if (l) tipLine(l.mid, e); else C.tip(null);
    });
    svg.addEventListener("pointerleave", () => { if (!drag) { C.tip(null); hotLineIfChanged(null); } });
    svg.addEventListener("pointerdown", (e) => {
      const r = e.target.closest(".m"); if (!r || e.button > 0) return;
      e.preventDefault();
      drag = { mid: r.dataset.m, x0: e.clientX, y0: e.clientY, moving: false };
    });
    const end = () => {
      if (!drag) return;
      const d = drag; drag = null;
      $("#ghost-g").innerHTML = "";
      C.$$("#slots-g .slot.drop, #slots-g .slot.blocked").forEach((r) => r.classList.remove("drop", "blocked"));
      if (!d.moving) { S.sel = S.sel === d.mid ? null : d.mid; render(); return; }
      const at = layout();
      if (d.target && okTarget(d.mid, d.target) && at[d.mid] !== d.target.id) {
        S.sel = d.mid;
        commit([...S.moves, { m: d.mid, to: d.target.id }], dropLabel(d.mid, d.target));
      } else drawCounter(at); // dropped nowhere useful: clear the preview
    };
    svg.addEventListener("pointerup", end);
    svg.addEventListener("pointercancel", () => { drag = null; $("#ghost-g").innerHTML = ""; drawCounter(layout()); });
  }
  function dropLabel(mid, s) {
    const other = pos[s.id];
    return other && other !== mid ? `Swap ${mid} with ${other}` : `Move ${mid} to bank ${s.bank.slice(2)}`;
  }
  function previewDrop(mid, s, ok) {
    const at = layout();
    if (!s || at[mid] === s.id) return drawCounter(at);
    if (!ok) return drawCounter(at, { blocked: s.zone === "Z-HL" || slotById[at[mid]].zone === "Z-HL" ? "High-Limit Room slots are locked." : "That slot can't take this machine." });
    drawCounter(at, { at: layoutOf([...S.moves.map((m) => ({ ...m })), { m: mid, to: s.id }]).at, label: dropLabel(mid, s) });
  }
  // ------------------------------------------------------------- move lines: geometry + hover
  function curve(f, t) {
    const x1 = f.x + CELL_W / 2, y1 = Y0 - f.y, x2 = t.x + CELL_W / 2, y2 = Y0 - t.y;
    const dx = x2 - x1, dy = y2 - y1, L = Math.hypot(dx, dy) || 1, k = Math.min(9, 2 + L * 0.16);
    return { x1, y1, x2, y2, cx: (x1 + x2) / 2 - (dy / L) * k, cy: (y1 + y2) / 2 + (dx / L) * k };
  }
  // nearest line to a point on the plan, within reach; sampled along each curve
  function lineAt(pt, reach = 1.1) {
    let best = null, bd = reach * reach;
    for (const l of lines) {
      const g = l.g;
      for (let i = 0; i <= 24; i++) {
        const t = i / 24, u = 1 - t;
        const x = u * u * g.x1 + 2 * u * t * g.cx + t * t * g.x2, y = u * u * g.y1 + 2 * u * t * g.cy + t * t * g.y2;
        const d = (x - pt.x) ** 2 + (y - pt.y) ** 2;
        if (d < bd) { bd = d; best = l; }
      }
    }
    return best;
  }
  // what stands in a move's origin slot now: its swap partner, or nobody
  function partnerOf(l) {
    layout();
    const back = pos[l.from.id];
    return back && back !== l.mid ? back : null;
  }
  // light one line, fade the rest, and label both ends with the machine that sits there now
  function hotLine(mid) {
    S.hot = mid;
    $("#lines-g").classList.toggle("hovering", !!mid);
    C.$$("#lines-g [data-m]").forEach((p) => p.classList.toggle("hot", p.dataset.m === mid));
    C.$$("#plan .moves li[data-line]").forEach((li) => li.classList.toggle("on", li.dataset.line === mid));
    const l = mid && lines.find((x) => x.mid === mid);
    if (!l) { $("#hot-g").innerHTML = ""; return; }
    const back = partnerOf(l);
    const box = (s) => `<rect class="hot-cell" x="${s.x - .35}" y="${Y0 - s.y - CELL_H / 2 - .35}" width="${CELL_W + .7}" height="${CELL_H + .7}" rx=".5"/>`;
    const tag = (s, text, below) => `<text class="hot-label" x="${s.x + CELL_W / 2}" y="${Y0 - s.y + (below ? CELL_H / 2 + 2.6 : -CELL_H / 2 - 1.3)}" text-anchor="middle">${text}</text>`;
    const down = l.g.y2 > l.g.y1; // put each label on the side away from the line
    $("#hot-g").innerHTML = box(l.from) + box(l.to)
      + tag(l.to, `${mid}, new spot`, down)
      + tag(l.from, back ? `${back}, swapped in` : `empty, ${mid} left`, !down);
  }
  function tipLine(mid, e) {
    const l = lines.find((x) => x.mid === mid); if (!l) return;
    const zn = (s) => F.zones.find((z) => z.id === s.zone)?.name;
    const p = projectMachine(mid, l.to.id);
    const partner = partnerOf(l);
    const rows = [["From", `${zn(l.from)}, bank ${l.from.bank.slice(2)}`], ["To", `${zn(l.to)}, bank ${l.to.bank.slice(2)}`],
      [mid, `${C.usd(p.day, { plus: true })}/day`]];
    if (partner) {
      const q = projectMachine(partner, l.from.id);
      rows.push([`${partner}, the other way`, `${C.usd(q.day, { plus: true })}/day`],
        ["Swap over July, after 2 moves", C.usd((p.day + q.day) * DAYS - 2 * S.price, { plus: true })]);
    } else rows.push(["Over July, after the move", C.usd(p.day * DAYS - S.price, { plus: true })]);
    C.tip(C.tipRows(partner ? `Swap: ${mid} and ${partner}` : `Move: ${mid} into an empty slot`, rows)
      + `<div class="small muted" style="margin-top:4px">${C.esc(byId[mid].theme)}${partner ? `; ${C.esc(byId[partner].theme)}` : ""}</div>`, e);
  }
  function hotLineIfChanged(mid) { if (mid !== S.hot) hotLine(mid); }

  function okTarget(mid, s) {
    const at = layout();
    const from = slotById[at[mid]];
    if (s.zone === "Z-HL" || from.zone === "Z-HL") return false;
    const other = pos[s.id];
    if (other && slotById[byId[other].loc[5]]?.zone === "Z-HL") return false;
    return bankFx[s.bank] != null && bankFx[from.bank] != null;
  }
})();
