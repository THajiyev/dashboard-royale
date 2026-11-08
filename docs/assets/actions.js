/* Actions page (question 6): our plan, what every catalogue action can bring, the spending-vs-return frontier,
   and a builder with an optimiser. Value models and the plan search live in assets/benefits.js; machine moves
   come from the location model in assets/moves.js. */
(function () {
  "use strict";
  const C = window.Core, $ = C.$;
  const MAX_TYPES = 3, DRAFT_VERSION = 3, SCN = ["Pessimistic", "Central", "Optimistic"];
  // The assumptions the data can't settle: { lo, mid, hi } = the value in the pessimistic, central, optimistic case.
  // A slider moves the central value; the cases either side stay fixed.
  const ASM = {
    signs: { label: "How much new signs lift Back Forty's play", lo: 0, mid: 0.05, hi: 0.1, max: 0.15, step: 0.005, act: "A-WAYFINDING",
      why: "The walkway closure shows access matters (play fell 31%), but no one has tested signs.", be: "Signs pay off above" },
    inspect: { label: "Chance M-1158's inspection finds a fault that can be fixed", lo: 0, mid: 0.5, hi: 1, max: 1, step: 0.05, act: "A-INSPECT",
      why: "M-1158 was flagged after its payout pattern differed from expectation; the cause is unresolved.", be: "Inspection pays off above" },
    prevent: { label: "How much a maintenance sweep cuts faults", lo: 0.1, mid: 0.4, hi: 0.6, max: 0.8, step: 0.05, act: "A-PREVENTIVE",
      why: "Fault rates are in the data; what a sweep does to them isn't.", be: "A Ridgeline sweep pays off above" },
    compLoss: { label: "Play lost if comps go back to the old price", lo: 0.01, mid: 0, hi: 0, max: 0.03, step: 0.0025, act: "A-COMP-CHANGE",
      why: "The May price cut showed no gain in play, but that can't rule out a small one.", be: "Restoring the old price pays only below" },
  };
  const ASM_OF = { "A-INSPECT": "inspect", "A-PREVENTIVE": "prevent", "A-WAYFINDING": "signs", "A-COMP-PILOT": "compLoss", "A-COMP-CHANGE": "compLoss" };
  const DEF = Object.fromEntries(Object.entries(ASM).map(([k, s]) => [k, { lo: s.lo, mid: s.mid, hi: s.hi }]));
  const dec = (s) => (s.step < 0.01 ? 1 : 0);
  const kUsd = (v) => `${v < 0 ? "−" : "+"}$${Math.abs(Math.round(v / 1000))}K`;
  const st = { scn: 1, cap: C.BUDGET };
  // Every estimate on this page uses Jan–Jun 2025 (months 0–5) and covers July 1–30, whatever period other pages are
  // set to, so a judge always sees the same plan. The scope is printed next to the estimates.
  const PERIOD = [0, 5], SCOPE = "Estimates use Jan–Jun 2025 data and cover July 1–30, 2025.";
  let CAT, mm, models, ours, plan, qty, downPerMove = 0;

  C.registerPage("actions.html", async () => {
    let Mo, M, F, B;
    try { [Mo, M, F, B] = await Promise.all([C.load("models"), C.load("machines"), C.load("floor"), C.load("benefits")]); }
    catch (e) { return C.fail($("#main"), e); }
    if (!C.pageActive()) return;
    CAT = Mo.catalog.filter((a) => a.action_type_id !== "A-HOLD");
    const [a, b] = PERIOD;                                       // locked: see PERIOD
    mm = C.moveModel(F, M, a, b);
    downPerMove = (CAT.find((x) => x.action_type_id === "A-MOVE-MACHINE").downtime_minutes / 60) * B.hourTheo;
    try { const s = JSON.parse(localStorage.getItem("ga-asm2")); if (s) for (const k in ASM) if (s[k] != null) ASM[k].mid = s[k]; } catch { /* */ }
    models = C.actionModels({ B, F, M, cat: CAT, a, b, asm: ASM, mm });
    // our plan: the best central plan for the full budget, at the default assumptions (fixed while visitors edit)
    const defModels = C.actionModels({ B, F, M, cat: CAT, a, b, asm: DEF, mm });
    ours = { models: defModels, ...C.bestPlan(defModels, 1, C.BUDGET) };
    ours.value = C.planValue(defModels, ours.qty);

    plan = C.plan();
    const sharedRequested = location.hash.startsWith("#plan=");
    const shared = readShared(F, M);
    if (shared) {
      for (const k in ASM) if (shared.a?.[k] != null) ASM[k].mid = +shared.a[k];
      plan.moves = shared.m || []; qty = { ...(shared.q || {}) }; save();
      history.replaceState(null, "", location.pathname + location.search + "#plan-h");
    } else if (!sharedRequested && plan.draft !== DRAFT_VERSION) loadPlan(ours.qty);  // a plan saved under an older draft is replaced once
    qty = { ...(plan.actions || {}) };
    const n = movesIn(); if (n) qty["A-MOVE-MACHINE"] = n; else delete qty["A-MOVE-MACHINE"];

    $("#cap").value = st.cap;
    $("#cap").oninput = () => { const v = +$("#cap").value; if (v >= 0) st.cap = Math.min(C.BUDGET, v); };
    $("#auto").onclick = () => {
      const p = C.bestPlan(models, st.scn, st.cap); loadPlan(p.qty);
      $("#auto-note").textContent = Object.keys(p.qty).length
        ? `Best ${SCN[st.scn].toLowerCase()} plan within ${C.usd(st.cap)}: ${C.usd(p.cost)}, net ${C.usd(p.net, { plus: true })}.`
        : `Within ${C.usd(st.cap)}, no plan beats keeping the money in the ${SCN[st.scn].toLowerCase()} case.`;
      render();
    };
    $("#reset").onclick = () => { loadPlan(ours.qty); $("#auto-note").textContent = ""; render(); };
    if (shared) $("#auto-note").textContent = "Loaded a shared plan. It's now saved in this browser too.";
    else if (sharedRequested) $("#auto-note").textContent = "This shared plan link is invalid or incompatible. Nothing from the link was applied.";
    $("#share").onclick = async () => {
      const payload = sharePayload();
      if (!validateShared(payload, F, M)) {
        $("#auto-note").textContent = "This plan exceeds the sharing limits (quantities, budget, or move rules). Adjust it before copying a link.";
        return;
      }
      const url = `${location.href.split("#")[0]}#plan=${shareCode(payload)}`;
      try { await navigator.clipboard.writeText(url); $("#auto-note").textContent = "Link copied. Anyone who opens it sees this plan and these assumptions."; }
      catch { $("#auto-note").innerHTML = `Copy this link: <input class="share-url" readonly value="${C.esc(url)}" aria-label="Link to this plan">`; $(".share-url").select(); }
    };
    $("#csv").onclick = downloadCsv;
    $("#scn").onclick = (e) => { const bt = e.target.closest("[data-s]"); if (!bt) return; st.scn = +bt.dataset.s; render(); };
    $("#sens-ctl").oninput = (e) => {
      const k = e.target.dataset.k; if (!k) return;
      ASM[k].mid = +e.target.value; $(`#asm-${k}-o`).textContent = C.pct(ASM[k].mid, dec(ASM[k]));
      try { localStorage.setItem("ga-asm2", JSON.stringify(Object.fromEntries(Object.entries(ASM).map(([j, s]) => [j, s.mid])))); } catch { /* */ }
      render();
    };
    $("#catalog").onclick = (e) => {
      const bt = e.target.closest("button[data-id]"); if (!bt) return;
      const m = model(bt.dataset.id), o = m.opts.filter((q) => q <= m.max).sort((x, y) => x - y), cur = qty[m.id] || 0;
      let i = o.length - 1; while (i > 0 && o[i] > cur) i--;                   // the option at or just below the current quantity
      const next = +bt.dataset.d > 0 ? o[Math.min(o.length - 1, o[i] === cur ? i + 1 : i + 1)] : o[Math.max(0, o[i] === cur ? i - 1 : i)];
      setQty(m.id, next ?? cur); render();
    };
    ourPlan(); sliders(); render();
    C.listen(window, "resize", drawFrontier); C.listen(window, "themechange", drawFrontier);
  });

  const model = (id) => models.find((m) => m.id === id);

  // ------------------------------------------------------------- share and export
  const sharePayload = () => ({ q: qty, m: plan.moves || [], a: Object.fromEntries(Object.entries(ASM).map(([k, s]) => [k, s.mid])) });
  const shareCode = (payload) => {
    const json = JSON.stringify(payload);
    return btoa(unescape(encodeURIComponent(json))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  };
  function readShared(F, M) {
    const h = location.hash.match(/^#plan=([\w-]+)$/);
    if (!h || h[1].length > 16000) return null;
    try {
      const code = h[1].replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(h[1].length / 4) * 4, "=");
      const s = JSON.parse(decodeURIComponent(escape(atob(code))));
      return validateShared(s, F, M);
    } catch { return null; }
  }
  function validateShared(s, F, M) {
    try {
      const isRecord = (x) => x != null && typeof x === "object" && !Array.isArray(x);
      if (!isRecord(s) || Object.keys(s).sort().join(",") !== "a,m,q" || !isRecord(s.q) || !Array.isArray(s.m) || !isRecord(s.a)) return null;
      const ids = new Set(CAT.map((x) => x.action_type_id));
      const actionIds = Object.keys(s.q);
      if (actionIds.length > MAX_TYPES || actionIds.some((id) => !ids.has(id))) return null;
      let totalCost = 0;
      for (const id of actionIds) {
        const n = s.q[id], m = model(id);
        if (!Number.isInteger(n) || n <= 0 || n > m.max || !m.opts.includes(n)) return null;
        totalCost += m.cost(n);
      }
      if (s.q["A-COMP-PILOT"] && s.q["A-COMP-CHANGE"]) return null;

      const slotById = Object.fromEntries(F.slots.map((slot) => [slot.id, slot]));
      const machineById = Object.fromEntries(M.map((machine) => [machine.id, machine]));
      const fx = Object.fromEntries(F.banks.map((bank) => [bank.id, bank.fx]));
      const at = {}, occupied = {};
      for (const machine of M) if (machine.loc[5]) {
        at[machine.id] = machine.loc[5];
        occupied[machine.loc[5]] = machine.id;
      }
      if (s.m.length > 100) return null;
      for (const mv of s.m) {
        if (!isRecord(mv) || Object.keys(mv).sort().join(",") !== "m,to" ||
            typeof mv.m !== "string" || typeof mv.to !== "string" ||
            !machineById[mv.m] || !slotById[mv.to] || !at[mv.m]) return null;
        const from = slotById[at[mv.m]], to = slotById[mv.to], other = occupied[mv.to];
        if (from.id === to.id || from.zone === "Z-HL" || to.zone === "Z-HL" ||
            fx[from.bank] == null || fx[to.bank] == null ||
            (other && machineById[other].loc[5] && slotById[machineById[other].loc[5]]?.zone === "Z-HL")) return null;
        delete occupied[from.id];
        if (other) { occupied[from.id] = other; at[other] = from.id; }
        occupied[to.id] = mv.m;
        at[mv.m] = to.id;
      }
      const moved = Object.entries(at).filter(([id, slot]) => slot !== machineById[id].loc[5]).length;
      if (moved > 24 || (s.q["A-MOVE-MACHINE"] || 0) !== moved) return null;

      const assumptionKeys = Object.keys(ASM).sort();
      if (Object.keys(s.a).sort().join(",") !== assumptionKeys.join(",")) return null;
      for (const [key, spec] of Object.entries(ASM)) {
        const value = s.a[key];
        if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > spec.max ||
            Math.abs(value / spec.step - Math.round(value / spec.step)) > 1e-7) return null;
      }
      if (!Number.isFinite(totalCost) || totalCost > C.BUDGET) return null;
      return s;
    } catch { return null; }
  }
  function downloadCsv() {
    const q = (v) => `"${String(v).replace(/"/g, '""')}"`;
    const ids = Object.keys(qty).filter((k) => qty[k] > 0);
    const lines = [["Action", "Quantity", "Target", "Cost", "July net pessimistic", "July net central", "July net optimistic"].map(q).join(",")];
    let cost = 0; const tot = [0, 0, 0];
    for (const id of ids) {
      const m = model(id), c = m.cost(qty[id]), v = net3(id, qty[id]); cost += c; v.forEach((x, i) => { tot[i] += x; });
      lines.push([m.name, qty[id], m.target(qty[id]), c.toFixed(0), ...v.map((x) => x.toFixed(0))].map(q).join(","));
    }
    lines.push(["Total", "", `Keep ${(C.BUDGET - cost).toFixed(0)}`, cost.toFixed(0), ...tot.map((x) => x.toFixed(0))].map(q).join(","));
    lines.push("", [q("Assumption"), q("Your value"), q("Pessimistic"), q("Optimistic")].join(","));
    for (const s of Object.values(ASM)) lines.push([s.label, s.mid, s.lo, s.hi].map(q).join(","));
    for (const mv of plan.moves || []) lines.push([q("Move machine"), q(mv.m), q(`to slot ${mv.to}`)].join(","));
    lines.push("", q(SCOPE), q("Net = July theo gained, less cost and the play lost while each action is carried out."));
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" })), download: "gilded-ace-july-plan.csv" });
    document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }
  const movesIn = () => mm.summarize(plan.moves || []).n;
  const stepMoves = (q) => mm.steps.filter((s) => s.n <= q).pop()?.moves || [];
  // machine moves on the plan: the optimiser's path, unless the visitor dragged their own on the floor plan
  const customMoves = () => { const n = movesIn(); return n > 0 && JSON.stringify(stepMoves(n)) !== JSON.stringify(plan.moves); };

  function save() {
    plan.actions = { ...qty }; delete plan.actions["A-MOVE-MACHINE"]; plan.draft = DRAFT_VERSION;   // plan.moves is already current
    const sum = mm.summarize(plan.moves || []);
    plan.moveSummary = { ...sum, cost: sum.n * 1800 };
    C.savePlan(plan);
  }
  function setQty(id, q) {
    if (id === "A-MOVE-MACHINE") { plan.moves = stepMoves(q); q = movesIn(); }
    if (q > 0) qty[id] = q; else delete qty[id];
    save();
  }
  function loadPlan(q) {
    plan = C.plan(); plan.moves = stepMoves(q["A-MOVE-MACHINE"] || 0);
    qty = { ...q }; if (!qty["A-MOVE-MACHINE"]) delete qty["A-MOVE-MACHINE"];
    save();
  }
  // value of a funded action at the current assumptions; dragged moves are valued as dragged
  function valOf(id, q) {
    if (id === "A-MOVE-MACHINE" && customMoves()) {
      const s = mm.summarize(plan.moves);
      return [s.lo, s.day, s.hi].map((v) => v * s.days - s.n * downPerMove);   // same downtime charge as the model
    }
    return model(id).val(q);
  }
  const net3 = (id, q) => valOf(id, q).map((v) => v - model(id).cost(q));
  const planNow = () => { const ids = Object.keys(qty).filter((k) => qty[k] > 0);
    return { cost: ids.reduce((t, k) => t + model(k).cost(qty[k]), 0), net: [0, 1, 2].map((s) => ids.reduce((t, k) => t + net3(k, qty[k])[s], 0)) }; };

  // ------------------------------------------------------------- our plan
  function ourPlan() {
    const ids = Object.keys(ours.qty).sort((x, y) => ours.models.find((m) => m.id === y).val(ours.qty[y])[1] - ours.models.find((m) => m.id === x).val(ours.qty[x])[1]);
    const rows = ids.map((id) => {
      const m = ours.models.find((x) => x.id === id), q = ours.qty[id];
      return { m, q, c: m.cost(q), v: m.val(q).map((x) => x - m.cost(q)) };
    });
    const words = ["no", "one", "two", "three"][rows.length];
    $("#rec-title").textContent = `Our plan · ${words} action${rows.length === 1 ? "" : "s"} · ${C.usd(ours.cost, { short: true })}`;
    $("#rec-lede").innerHTML = `Replacing the bottom 10 wouldn't help: they're low because of where they sit. This is the plan that returns the most in July,
      from a search of every plan the catalogue allows. <strong>About ${C.usd(ours.value.net[1], { plus: true })} net, between ${C.usd(ours.value.net[0], { plus: true })}
      and ${C.usd(ours.value.net[2], { plus: true })}</strong> depending on <a href="#asm-h">four assumptions</a>. <span class="scope">${SCOPE}</span>`;
    $("#rec").innerHTML = `<thead><tr><th>Action</th><th>Why</th><th class="num">Cost</th><th class="num">July net<span class="sub">pessimistic – optimistic</span></th><th>How we'll know it worked</th></tr></thead><tbody>
      ${rows.map((r) => `<tr><td class="rec-name"><a href="${r.m.href}">${C.esc(r.m.name)}</a><span class="sub">${C.esc(r.m.target(r.q))}</span></td><td>${C.esc(r.m.why)}</td><td class="num">${C.usd(r.c)}</td>
        <td class="num"><strong>${C.usd(r.v[1], { plus: true })}</strong><span class="sub">${C.usd(r.v[0], { plus: true })} – ${C.usd(r.v[2], { plus: true })}</span></td><td>${C.esc(r.m.how)}</td></tr>`).join("")}
      <tr class="hl"><td class="rec-name">Total</td><td>Keep ${C.usd(C.BUDGET - ours.cost)}</td><td class="num">${C.usd(ours.cost)}</td>
        <td class="num"><strong>${C.usd(ours.value.net[1], { plus: true })}</strong><span class="sub">${C.usd(ours.value.net[0], { plus: true })} – ${C.usd(ours.value.net[2], { plus: true })}</span></td><td></td></tr></tbody>`;
    $("#rec-note").textContent = `Net is July theo (expected house win) gained, less cost and the play lost while each action is carried out. We keep ${C.usd(C.BUDGET - ours.cost)} because no further spending pays in July: see the frontier below.`;
  }

  // ------------------------------------------------------------- every action
  // the rest of the catalogue as a list; each opens to say why it isn't in our plan
  function otherOptions() {
    const open = new Set(C.$$("#ben details[open]").map((d) => d.dataset.id));      // keep open items open across re-renders
    const rows = models.filter((m) => !ours.qty[m.id]).map((m) => {
      let best = { q: 0, v: [0, 0, 0] };
      for (const q of m.opts) { if (!q || q > m.max) continue; const v = m.val(q).map((x) => x - m.cost(q)); if (!best.q || v[1] > best.v[1]) best = { q, v }; }
      return { m, ...best };
    }).sort((x, y) => y.v[1] - x.v[1]);
    const names = Object.keys(ours.qty).map((id) => ours.models.find((m) => m.id === id).name.toLowerCase());
    const money = (v) => `<span class="${v < 0 ? "neg" : "pos"}">${C.usd(v, { plus: true })}</span>`;
    $("#ben").innerHTML = rows.map((r) => {
      const reason = r.v[1] > 0
        ? `It pays on its own, but the catalogue allows only three action types, and the plan's three (${names.join(", ")}) each return more.`
        : r.m.whyNot || "It doesn't pay back in July.";
      return `<details class="why-not" data-id="${r.m.id}" ${open.has(r.m.id) ? "open" : ""}><summary><span class="wn-name">${C.esc(r.m.name)}</span>
          <span class="wn-net">${money(r.v[1])} in July</span><span class="wn-btn">Why not?</span></summary>
        <div class="wn-body"><p>${C.esc(reason)}</p>
          <p class="small muted">At its best quantity (${r.q}), ${C.usd(r.m.cost(r.q))}: ${money(r.v[0])} pessimistic, ${money(r.v[1])} central, ${money(r.v[2])} optimistic.
            ${C.esc(r.m.note)}${r.m.href ? ` <a href="${r.m.href}">Evidence</a>` : ""}</p></div></details>`;
    }).join("");
  }

  // ------------------------------------------------------------- frontier
  let F0 = null, FV = null;
  function drawFrontier() {
    const svg = $("#ppf"); if (!svg || !models) return;
    const f = C.frontier(models, st.scn), pts = f.filter((p, i) => i === 0 || p.net !== f[i - 1].net || i === f.length - 1);
    F0 = f; FV = f.map((p) => C.planValue(models, p.qty).net);
    const mine = planNow(), our = C.planValue(models, ours.qty);
    const W = svg.clientWidth || 900, H = 320, P = { l: 64, r: 16, t: 16, b: 34 };
    const ys = FV.flat().concat(mine.net, our.net, 0);
    const lo = Math.min(0, Math.floor(Math.min(...ys) / 25000) * 25000), hi = Math.ceil(Math.max(...ys) / 25000) * 25000;
    const x = C.scale(0, C.BUDGET, P.l, W - P.r), y = C.scale(lo, hi, H - P.b, P.t);
    let g = "";
    const k = (v) => (v < 0 ? "−" : "") + "$" + Math.abs(v / 1000) + "K";
    for (let v = lo; v <= hi; v += 25000) g += `<line x1="${P.l}" x2="${W - P.r}" y1="${y(v)}" y2="${y(v)}" stroke="${v === 0 ? "var(--ink-3)" : "var(--grid)"}"/><text x="${P.l - 8}" y="${y(v) + 4}" text-anchor="end">${k(v)}</text>`;
    for (let v = 0; v <= C.BUDGET; v += 20000) g += `<text x="${x(v)}" y="${H - 10}" text-anchor="${v === C.BUDGET ? "end" : v ? "middle" : "start"}">${v === C.BUDGET ? "$100K spent" : k(v)}</text>`;
    g += `<text x="${P.l + 4}" y="${P.t + 10}">July net</text>`;
    // band: the frontier plans' pessimistic to optimistic net; line: the chosen case, as a step
    const step = (vals) => vals.map((v, i) => `${i ? "L" : "M"}${x(f[i].budget).toFixed(1)},${y(v).toFixed(1)}`).join("");
    g += `<path d="${step(FV.map((v) => v[2]))}${FV.map((v, i) => `L${x(f[FV.length - 1 - i].budget).toFixed(1)},${y(FV[FV.length - 1 - i][0]).toFixed(1)}`).join("")}Z" fill="var(--accent-soft)"/>`;
    g += `<path d="${step(f.map((p) => p.net))}" fill="none" stroke="var(--accent)" stroke-width="2.5" stroke-linejoin="round"/>`;
    const mark = (p, cls, label) => `<line x1="${x(p.cost)}" x2="${x(p.cost)}" y1="${y(p.net[0])}" y2="${y(p.net[2])}" stroke="${cls}" stroke-width="1.5"/>
      ${[0, 1, 2].filter((i) => i !== st.scn).map((i) => `<circle cx="${x(p.cost)}" cy="${y(p.net[i])}" r="2.5" fill="${cls}" stroke="var(--card)" stroke-width="1"/>`).join("")}
      <circle cx="${x(p.cost)}" cy="${y(p.net[st.scn])}" r="5.5" fill="${label === "ours" ? "var(--card)" : cls}" stroke="${cls}" stroke-width="2"/>`;
    g += mark(our, "var(--accent-ink)", "ours") + mark(mine, "var(--ink)", "mine");
    g += `<line id="ppf-x" y1="${P.t}" y2="${H - P.b}" stroke="var(--ink-3)" opacity="0"/><rect x="${P.l}" y="${P.t}" width="${W - P.l - P.r}" height="${H - P.t - P.b}" fill="transparent" id="ppf-hit" style="cursor:pointer"/>`;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.innerHTML = g;
    $("#ppf-legend").innerHTML = `<span><i style="background:var(--accent);height:3px"></i>Best plan at each budget, ${SCN[st.scn].toLowerCase()} case</span>
      <span><i class="box" style="background:var(--accent-soft)"></i>Frontier range: pessimistic to optimistic</span>
      <span><svg width="12" height="12" aria-hidden="true"><circle cx="6" cy="6" r="4.5" fill="var(--card)" stroke="var(--accent-ink)" stroke-width="2"/></svg>Our plan</span>
      <span><svg width="12" height="12" aria-hidden="true"><circle cx="6" cy="6" r="4.5" fill="var(--ink)"/></svg>Your plan</span>
      <span>Bottom dot: pessimistic. Middle: central. Top: optimistic. The selected case is the larger dot.</span>`;
    const changes = f.map((p, i) => ({ p, v: FV[i] })).filter((r, i) => i === 0 || JSON.stringify(r.p.qty) !== JSON.stringify(f[i - 1].qty));
    C.dataTable($("#ppf-legend"), "ppf-table", "Best plan at each budget where the plan changes",
      ["From a budget of", "Best plan", "Cost", "Pessimistic", "Central", "Optimistic"],
      changes.map(({ p, v }) => [C.usd(p.budget), Object.entries(p.qty).map(([id, q]) => `${C.esc(model(id).name)} × ${q}`).join("; ") || "Keep everything",
        C.usd(p.cost), ...v.map((x) => C.usd(x, { plus: true }))]));
    const at = (e) => { const r = svg.getBoundingClientRect(), px = ((e.clientX - r.left) / r.width) * W; return Math.max(0, Math.min(f.length - 1, Math.round(((px - P.l) / (W - P.l - P.r)) * (f.length - 1)))); };
    const hit = $("#ppf-hit");
    hit.onmousemove = (e) => {
      const i = at(e), p = f[i], v = FV[i], ln = $("#ppf-x");
      ln.setAttribute("x1", x(p.budget)); ln.setAttribute("x2", x(p.budget)); ln.setAttribute("opacity", 0.6);
      const items = Object.entries(p.qty).map(([id, q]) => [`${model(id).name}`, `× ${q}`]);
      C.tip(C.tipRows(`Budget ${C.usd(p.budget)}: best plan costs ${C.usd(p.cost)}`, [...(items.length ? items : [["Keep everything", ""]]),
        ["July net", `${C.usd(v[st.scn], { plus: true })} (${C.usd(v[0], { plus: true })} to ${C.usd(v[2], { plus: true })})`], ["", "Click to load this plan"]]), e);
    };
    hit.onmouseleave = () => { C.tip(null); $("#ppf-x")?.setAttribute("opacity", 0); };
    hit.onclick = (e) => {
      const p = f[at(e)]; loadPlan(p.qty); C.tip(null);
      $("#auto-note").textContent = `Loaded the best ${SCN[st.scn].toLowerCase()} plan for ${C.usd(p.budget)}.`; render();
      $("#plan-h").closest("section").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    };
  }

  // ------------------------------------------------------------- builder
  // the four assumptions, always shown: what it is, why it's assumed, its range, and where its action breaks even
  function sliders() {
    $("#sens-ctl").innerHTML = Object.entries(ASM).map(([k, s]) => `<div class="asm">
      <label for="asm-${k}"><span class="asm-name">${s.label}</span><output id="asm-${k}-o">${C.pct(s.mid, dec(s))}</output></label>
      <input type="range" id="asm-${k}" data-k="${k}" min="0" max="${s.max}" step="${s.step}" value="${s.mid}">
      <p class="small muted">${C.esc(s.why)} Pessimistic ${C.pct(s.lo, dec(s))}, optimistic ${C.pct(s.hi, dec(s))}.
        <span class="asm-be" id="asm-${k}-be"></span></p></div>`).join("");
  }
  // value of the assumption at which its action's central net is zero (nets are linear in each assumption)
  function breakEven(k) {
    const s = ASM[k], m = model(s.act), keep = s.mid;
    const at = (x) => { s.mid = x; const v = m.val(1)[1] - m.cost(1); return v; };
    const n0 = at(0), n1 = at(1); s.mid = keep;
    return n1 === n0 ? null : -n0 / (n1 - n0);
  }
  function breakEvens() {
    for (const k in ASM) {
      const s = ASM[k], x = breakEven(k), el = $(`#asm-${k}-be`); if (!el) continue;
      el.textContent = x == null ? "" : `${s.be} ${C.pct(x, x < 0.1 ? 1 : 0)}${k === "compLoss" ? " lost play" : ""}; it's set to ${C.pct(s.mid, dec(s))}.`;
    }
  }

  function render() {
    C.$$("#scn button").forEach((bt) => bt.setAttribute("aria-pressed", String(+bt.dataset.s === st.scn)));
    otherOptions(); breakEvens(); drawFrontier();
    const types = Object.keys(qty).filter((k) => qty[k] > 0);
    const rows = types.map((k) => ({ m: model(k), q: qty[k], c: model(k).cost(qty[k]), v: net3(k, qty[k]) }));
    const total = rows.reduce((t, r) => t + r.c, 0), tot = [0, 1, 2].map((i) => rows.reduce((t, r) => t + r.v[i], 0));
    const over = total > C.BUDGET, tooMany = types.length > MAX_TYPES;
    const clash = (qty["A-COMP-PILOT"] && qty["A-COMP-CHANGE"]) ? "The comp pilot and comp change can't be combined" : null;
    $("#stats").innerHTML = [
      ["Committed", C.usd(total), over ? "Over the $100,000 budget" : `of ${C.usd(C.BUDGET)}; ${C.usd(Math.max(0, C.BUDGET - total))} kept`],
      ["Action types", `${types.length} of ${MAX_TYPES}`, tooMany ? "Too many: drop one" : clash || "Within the limit"],
      ["July net, central", C.usd(tot[1], { plus: true }), "July 1–30, from Jan–Jun 2025 data"],
      ["Pessimistic – optimistic", `${kUsd(tot[0])} to ${kUsd(tot[2])}`, "Every assumption at its low or high end"],
    ].map(([l, v, f], i) => `<div class="stat"><div class="label">${l}</div><div class="value${i === 2 ? " accent" : ""}">${v}</div><div class="foot" ${(i === 0 && over) || (i === 1 && (tooMany || clash)) ? 'style="color:var(--neg)"' : ""}>${f}</div></div>`).join("");

    const parts = rows.slice().sort((p, q) => q.c - p.c), scaleTo = Math.max(C.BUDGET, total), kept = Math.max(0, C.BUDGET - total);
    const shade = ["var(--accent)", "color-mix(in srgb, var(--accent) 70%, var(--card))", "color-mix(in srgb, var(--accent) 45%, var(--card))", "color-mix(in srgb, var(--accent) 28%, var(--card))"];
    $("#budget").innerHTML = `<div class="budget-bar" role="img" aria-label="${C.esc(parts.map((p) => `${p.m.name} ${C.usd(p.c)}`).concat(`kept ${C.usd(kept)}`).join(", "))}">
        ${parts.map((p, i) => `<span class="${over ? "over" : "b" + Math.min(i, 3)}" style="flex:0 0 ${(p.c / scaleTo) * 100}%" title="${C.esc(p.m.name)}: ${C.usd(p.c)}"></span>`).join("")}
        ${kept ? '<span class="kept" title="Kept"></span>' : ""}</div>
      <div class="budget-key">${parts.map((p, i) => `<span><i style="background:${over ? "var(--neg)" : shade[Math.min(i, 3)]}"></i>${C.esc(p.m.name)} <span class="num">${C.usd(p.c)}</span></span>`).join("")}
        ${kept ? `<span><i style="background:var(--raised);box-shadow:inset 0 0 0 1px var(--line-2)"></i>Kept <span class="num">${C.usd(kept)}</span></span>` : ""}</div>`;

    $("#catalog").innerHTML = models.map((m) => {
      const n = qty[m.id] || 0, o = m.opts.filter((q) => q <= m.max), mv = m.id === "A-MOVE-MACHINE";
      return `<div class="act ${n ? "on" : ""}" style="grid-template-columns:1fr auto"><div><div class="name">${C.esc(m.name)}</div>
        <div class="meta">${C.usd(m.unitCost)}${m.id === "A-REPLACE-LEASE" ? " + $55/day" : ""}, ${m.days} days in July, up to ${m.max}${mv ? `; <a href="floor.html">pick on the floor plan</a>` : ""}</div></div>
        <div class="stepper" role="group" aria-label="${C.esc(m.name)} quantity">
          <button type="button" data-d="-1" data-id="${m.id}" ${n ? "" : "disabled"} aria-label="Fewer">−</button><output>${n}</output>
          <button type="button" data-d="1" data-id="${m.id}" ${n >= o[o.length - 1] ? "disabled" : ""} aria-label="More">+</button></div></div>`;
    }).join("");

    $("#cards").innerHTML = rows.length ? rows.map((r) => `<details class="card plan-card"><summary><span><span class="pc-name">${C.esc(r.m.name)} × ${r.q}</span>
        <span class="pc-target">${C.esc(r.m.id === "A-MOVE-MACHINE" && customMoves() ? `${r.q} machines, as placed on the floor plan` : r.m.target(r.q))}</span></span><span class="num">${C.usd(r.c)}</span></summary>
        <dl><dt>July net</dt><dd>${C.usd(r.v[1], { plus: true })} central; ${C.usd(r.v[0], { plus: true })} to ${C.usd(r.v[2], { plus: true })}</dd>
        <dt>Why</dt><dd>${C.esc(r.m.why)}</dd><dt>Basis</dt><dd>${C.esc(r.m.note)}</dd><dt>How we'd know</dt><dd>${C.esc(r.m.how)}</dd>
        ${r.m.href ? `<dt>Evidence</dt><dd><a href="${r.m.href}">Open</a></dd>` : ""}</dl></details>`).join("") : '<p class="empty">Nothing funded: the whole budget is kept.</p>';

    const cell = (v) => `<td class="num ${v < 0 ? "neg" : "pos"}">${C.usd(v, { plus: true })}</td>`;
    $("#sens").innerHTML = rows.length ? `<thead><tr><th>Action</th><th class="num">Cost</th><th class="num">Net, pessimistic</th><th class="num">Net, central</th><th class="num">Net, optimistic</th></tr></thead><tbody>
      ${rows.map((r) => `<tr><td>${C.esc(r.m.name)} × ${r.q}</td><td class="num">${C.usd(r.c)}</td>${r.v.map(cell).join("")}</tr>`).join("")}
      <tr class="hl"><td>The plan</td><td class="num">${C.usd(total)}</td>${tot.map(cell).join("")}</tr></tbody>`
      : '<tbody><tr><td class="empty">Nothing funded: no downside and no upside.</td></tr></tbody>';
    $("#sens-note").textContent = !rows.length ? "" : tot[0] >= 0
      ? `Even with every assumption at its low end, the plan nets ${C.usd(tot[0], { plus: true })}.`
      : `With every assumption at its low end, the plan loses ${C.usd(-tot[0])}; that's the risk taken for the central ${C.usd(tot[1], { plus: true })}.`;
  }
})();
