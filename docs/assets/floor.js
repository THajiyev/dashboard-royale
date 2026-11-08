/* Floor page: plan drawn from floor_locations x/y, shaded by the chosen measure,
   with drag-to-move projections from the Phase 3 location GLM (bank effects, Jan–Apr fit). */
(function () {
  "use strict";
  const C = window.Core, $ = C.$;
  const LEAD = 2, HORIZON = 30, MOVE_COST = 1800, MOVE_LIMIT = 24;
  const DAYS = HORIZON - LEAD;
  const Y0 = 118; // flip: svg y = Y0 - y_m
  const CELL_W = 1.3, CELL_H = 2.4;
  const DESC = {
    play: "Coin-in per available hour: how much is wagered while the machine can be played",
    rev: "Theo per available hour: expected house win, so luck is taken out",
    luck: "Luck z: house win minus theo, in standard deviations. Beyond ±1.96 happens to 5% of fair machines",
    traffic: "Entries per counted hour at each zone's door sensor. Counters see entries, not unique guests",
  };

  const S = { metric: "play", a: 0, b: 5, sel: null, zone: null, moves: [] };
  let F, M, PF, flags = {}, byId, slotById, bankFx, covIdx, agg, pos, base;

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
    buildFloor();
    render();
    persist(); // keep the action plan's move summary in step with the current period
    addEventListener("themechange", render);
  });

  // ------------------------------------------------------------- layout with moves applied
  function layout() {
    pos = { ...base }; // slot -> machine
    const at = {}; for (const s in pos) at[pos[s]] = s;
    for (const mv of S.moves) {
      const from = at[mv.m]; if (!from) continue;
      const other = pos[mv.to];
      mv.displaced = other || null;
      delete pos[from];
      if (other) { pos[from] = other; at[other] = from; }
      pos[mv.to] = mv.m; at[mv.m] = mv.to;
    }
    return at;
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
    return { rows, day, lo: day - half, hi: day + half, cost: rows.length * MOVE_COST };
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
      <g id="walks"></g><g id="zones-g"></g><g id="slots-g"></g><g id="mach-g"></g><g id="lines-g"></g><g id="flags-g"></g><g id="ghost-g"></g>`;
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
    $("#lines-g").innerHTML = Object.entries(at).filter(([mid, sl]) => sl !== byId[mid].loc[5]).map(([mid, sl]) => {
      const f = slotById[byId[mid].loc[5]], t = slotById[sl];
      return `<path class="move-line" d="M${f.x + CELL_W / 2} ${Y0 - f.y}L${t.x + CELL_W / 2} ${Y0 - t.y}"/>`;
    }).join("");
    // flag markers: filled red dot = flagged, red ring = watch; drawn above the cell so the shading stays readable
    $("#flags-g").innerHTML = Object.entries(at).filter(([mid]) => flags[mid]).map(([mid, sl]) => {
      const s = slotById[sl], f = flags[mid], cx = s.x + CELL_W / 2, cy = Y0 - s.y - CELL_H / 2 - 1.1;
      return f.level === "flag"
        ? `<circle class="flag-dot" cx="${cx}" cy="${cy}" r=".75"><title>${mid}: ${C.esc(f.reasons.join("; "))}</title></circle>`
        : `<circle class="flag-ring" cx="${cx}" cy="${cy}" r=".6"><title>${mid}: ${C.esc(f.reasons.join("; "))}</title></circle>`;
    }).join("");
    drawDetail(); drawPlan(at); drawZones(at, tr);
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
      el.innerHTML = `<h3>No machine selected</h3><p class="muted" style="margin:4px 0 0">Hover a machine for its figures, select it to pin them here.
        Drag it onto another slot to project a move; dropping on an occupied slot swaps the two.</p>`;
      return;
    }
    const m = byId[S.sel], s = agg[S.sel], sl = slotById[m.loc[5]];
    const zn = F.zones.find((z) => z.id === sl?.zone)?.name ?? "–";
    el.innerHTML = `<h3 class="mono">${m.id}</h3>
      <div class="muted">${C.esc(m.theme)} · ${C.esc(m.mfr)} · ${zn}, bank ${sl?.bank.slice(2) ?? "–"}</div>
      <dl class="kv">
        <dt>Coin-in per available hour</dt><dd>${C.usd(s.ciHr)}</dd>
        <dt>Theo per available hour</dt><dd>${C.usd(s.theoHr, { d: 2 })}</dd>
        <dt>Availability</dt><dd>${C.pct(s.avail)}</dd>
        <dt>Days on the floor</dt><dd>${s.days}</dd>
        <dt>Luck</dt><dd>${C.usd(s.luck, { plus: true })} · z ${C.num(s.z, 2, true)}</dd>
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
      <p class="muted" style="margin:4px 0 0">$1,800 a machine, 2-day lead, so ${DAYS} days of effect in July.</p>
      ${T.rows.length ? `<ul class="moves">${T.rows.map((r) => `<li>
          <span><span class="mono">${r.mid}</span><span class="sub small muted">${r.fromBank} → ${r.toBank}${(slotById[r.to].zone === "Z-B40") ? ", into Back Forty" : ""}</span></span>
          <span class="num ${r.day >= 0 ? "" : "muted"}">${C.usd(r.day, { plus: true })}/day</span>
          <button type="button" data-undo="${r.mid}" aria-label="Undo move of ${r.mid}">${C.icon("x", 14)}</button></li>`).join("")}</ul>
        <div class="total-row"><span class="muted">Projected theo, ${DAYS} days</span><span class="big">${C.usd(T.day * DAYS, { plus: true })}</span></div>
        <div class="small muted" style="text-align:right">90% range ${C.usd(T.lo * DAYS, { plus: true })} to ${C.usd(T.hi * DAYS, { plus: true })}</div>
        <div class="total-row"><span class="muted">Cost</span><span class="num">${C.usd(T.cost)} of ${C.usd(C.BUDGET)}</span></div>
        <div class="meter" aria-hidden="true"><span style="transform:scaleX(${Math.min(1, T.cost / C.BUDGET)})"></span></div>
        ${over ? `<p class="note" style="color:var(--neg)">The catalogue allows ${MOVE_LIMIT} machine moves; this plan has ${T.rows.length}.</p>` : ""}
        <div style="display:flex;gap:8px;margin-top:16px;flex-wrap:wrap">
          <button class="btn" type="button" id="reset">${C.icon("undo", 14)}Reset moves</button>
          <a class="btn primary" href="actions.html${location.search}" style="text-decoration:none">Open the action plan ${C.icon("arrow", 14)}</a></div>`
        : `<p class="empty">No moves yet. Empty slots at Jun 30: two in the Center Pit, one in Hotel Corridor, two in Back Forty, one in the High-Limit Room.</p>`}
      <p class="note">Projection: the machine's own theo per day × the change in bank effect from the location model (fit Jan–Apr).
        Back-test on the one real move, M-1152 from Back Forty to the Entrance on Feb 4: predicted <span class="mono">+$303</span>/day,
        measured <span class="mono">+$342</span>/day (90% CI <span class="mono">+$188</span> to <span class="mono">+$497</span>).
        The range shown covers model uncertainty only, so it is narrower than what a real move will show.
        High-Limit Room slots are locked: its clientele and games don't exist elsewhere.</p>`;
    el.onclick = (e) => {
      const u = e.target.closest("[data-undo]");
      if (u) { undoMachine(u.dataset.undo); return; }
      if (e.target.closest("#reset")) { S.moves = []; persist(); render(); }
    };
  }
  function undoMachine(mid) {
    // rebuild the move list without any move that touched this machine's final slot chain
    layout(); // refreshes mv.displaced
    S.moves = S.moves.filter((mv) => mv.m !== mid && mv.displaced !== mid);
    persist(); render();
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
    C.tip(C.tipRows(`<span class="mono">${m.id}</span> · ${C.esc(m.theme)}`, [
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
        if (s) svg.querySelector(`[data-slot="${s.id}"]`).classList.add(okTarget(drag.mid, s) ? "drop" : "blocked");
        drag.target = s;
        return;
      }
      const r = e.target.closest(".m");
      if (r) tipFor(r.dataset.m, e); else C.tip(null);
    });
    svg.addEventListener("pointerleave", () => { if (!drag) C.tip(null); });
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
        S.moves.push({ m: d.mid, to: d.target.id });
        S.sel = d.mid; persist(); render();
      }
    };
    svg.addEventListener("pointerup", end);
    svg.addEventListener("pointercancel", () => { drag = null; $("#ghost-g").innerHTML = ""; });
  }
  function okTarget(mid, s) {
    const at = layout();
    const from = slotById[at[mid]];
    if (s.zone === "Z-HL" || from.zone === "Z-HL") return false;
    const other = pos[s.id];
    if (other && slotById[byId[other].loc[5]]?.zone === "Z-HL") return false;
    return bankFx[s.bank] != null && bankFx[from.bank] != null;
  }
})();
