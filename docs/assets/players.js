/* Players page (Q4): tracked wagers, payouts and net; loss concentration; per-player luck
   (expected vs actual payout, $ and %), payout z ranked against peers, and an exact win-rate check. */
(function () {
  "use strict";
  const C = window.Core, $ = C.$;
  const S = { a: 0, b: 5, seg: "all", dir: "up", all: null, q: "", sort: "diff", ord: "desc", page: 0 };
  const DIM = { region: "Home region", age: "Age band", tier: "Tier" };
  let P;

  C.registerPage("players.html", async () => {
    try { P = await C.load("players"); } catch (e) { return C.fail($("#main"), e); }
    if (!C.pageActive()) return;
    try { S.seg = new URLSearchParams(location.search).get("group") || localStorage.getItem("ga-player-seg") || "all"; } catch { /* */ }
    $("#seg").innerHTML = `<option value="all">All players</option>` + Object.entries(P.groups).map(([d, vals]) =>
      `<optgroup label="${DIM[d]}">${vals.map((v) => `<option value="${d}:${v}">${v}</option>`).join("")}</optgroup>`).join("");
    $("#seg").value = S.seg;
    $("#seg").onchange = (e) => setSeg(e.target.value);
    [S.a, S.b] = C.periodControl($("#period"), (a, b) => { S.a = a; S.b = b; render(); });
    $("#mdir").onclick = (e) => { const b = e.target.closest("button"); if (b) { S.dir = b.dataset.d; drawMoney(); } };
    $("#load-all").onclick = loadAll;
    render();
    C.listen(window, "resize", drawCharts); C.listen(window, "themechange", drawCharts);
  });

  function setSeg(v) {
    S.seg = v; $("#seg").value = v; S.page = 0;
    try { localStorage.setItem("ga-player-seg", v); } catch { /* */ }
    const u = new URL(location.href); if (v === "all") u.searchParams.delete("group"); else u.searchParams.set("group", v);
    history.replaceState(null, "", u);
    render();
  }
  const range = () => P.ranges[`${S.a}-${S.b}`];
  const cur = () => range()[S.seg] || range().all;
  const segOk = (x) => S.seg === "all" || x[S.seg.split(":")[0]] === S.seg.split(":")[1];
  const segLabel = () => (S.seg === "all" ? "All players" : S.seg.split(":")[1] + (S.seg.startsWith("tier") ? " tier" : S.seg.startsWith("age") ? " years" : ""));
  const peer = (p) => (p == null ? "–" : p >= 0.5 ? `top ${fmtShare(1 - p)}` : `bottom ${fmtShare(p)}`);
  const fmtShare = (f) => (f < 0.001 ? "0.1%" : f < 0.01 ? (f * 100).toFixed(1) + "%" : Math.round(f * 100) + "%");

  function render() {
    $("#title").textContent = `Tracked players · ${C.periodLabel(S.a, S.b)}`;
    const s = cur();
    const net = s.po - s.ci;
    $("#stats").innerHTML = [
      ["Wagered", C.usd(s.ci, { short: true }), `${C.int(s.players)} ${segLabel().toLowerCase() === "all players" ? "players" : segLabel()}, ${C.int(s.sessions)} sessions`],
      ["Paid back", C.usd(s.po, { short: true }), `${C.pct(s.po / s.ci)} of wagers; the odds predicted ${C.pct((s.ci - s.theo) / s.ci)}`],
      ["Players' net result", C.usd(net, { short: true }), `expected ${C.usd(s.expNet, { short: true })} from the odds; the gap is ${Math.abs(s.luck / s.sd) < 1.96 ? "inside" : "outside"} normal swings`],
      ["Finished ahead", `${C.pct(s.ahead / s.players, 0)}`, `${C.int(s.ahead)} players won ${C.usd(s.winnings, { short: true })} between them`],
    ].map(([l, v, f], i) => `<div class="stat"><div class="label">${l}</div><div class="value${i === 2 ? " accent" : ""}">${v}</div><div class="foot">${f}</div></div>`).join("");
    drawGroups(); drawCharts(); drawHit(); drawMoney(); if (S.all) drawAll();
  }

  // ------------------------------------------------------------- charts
  function drawCharts() { if (!P) return; drawLorenz(); phist("#hhit", cur().hitP); phist("#hz", cur().monP); }

  // p-value histogram: under fair play every bar sits on the flat line; a pile-up near 0 is the signal
  function phist(sel, counts) {
    const svg = $(sel), W = svg.clientWidth || 500, H = 200, P0 = { l: 44, r: 8, t: 8, b: 24 }, bins = P.pbins;
    const n = counts.reduce((t, v) => t + v, 0), flat = n / counts.length, max = Math.max(...counts, flat) * 1.15;
    const x = C.scale(0, 1, P0.l, W - P0.r), y = C.scale(0, max, H - P0.b, P0.t), step = C.niceMax(max / 3);
    let g = "";
    for (let t = 0; t <= max; t += step) g += `<line x1="${P0.l}" x2="${W - P0.r}" y1="${y(t)}" y2="${y(t)}" stroke="var(--grid)"/><text x="${P0.l - 6}" y="${y(t) + 4}" text-anchor="end">${t >= 1000 ? +(t / 1000).toFixed(1) + "K" : t}</text>`;
    counts.forEach((c, i) => {
      const x0 = x(bins[i]) + 1, bw = Math.max(1, x(bins[i + 1]) - x(bins[i]) - 2);
      g += `<rect x="${x0}" y="${y(c)}" width="${bw}" height="${y(0) - y(c)}" rx="2" fill="${i === 0 ? "var(--accent)" : "var(--ink-3)"}" fill-opacity="${i === 0 ? 0.9 : 0.55}"><title>p ${bins[i]}–${bins[i + 1]}: ${C.int(c)} players (fair play: about ${C.int(flat)})</title></rect>`;
    });
    g += `<line x1="${P0.l}" x2="${W - P0.r}" y1="${y(flat)}" y2="${y(flat)}" stroke="var(--ink)" stroke-dasharray="4 3"/>`;
    for (const t of [0, 0.25, 0.5, 0.75, 1]) g += `<text x="${x(t)}" y="${H - 6}" text-anchor="middle">${t}</text>`;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.innerHTML = g;
    const s = cur();
    C.dataTable(svg, `${sel.slice(1)}-table`, sel === "#hhit" ? "Win-rate p-value histogram by bin" : "Peer-based payout p-value histogram by bin",
      ["p-value range", "Players", "Expected if fair"], counts.map((c, i) => [`${bins[i]} to ${bins[i + 1]}`, C.int(c), C.int(flat)]));
    if (sel === "#hhit") $("#hit-sub").textContent = `${C.pct(s.hitP05 / s.players, 1)} of players have p < 0.05 (fair play: 5%). ${s.hitFlag} flagged after correcting for ${C.int(s.players)} tests. The tall last bar is very short play, where an exact test can't give a small p.`;
    else $("#z-sub").textContent = `${C.pct(s.monP05 / s.players, 1)} have p < 0.05, as fair play gives. ${s.monFlag} flagged: a peer-based p can't go below 1 in the peer group, so it ranks players but can't single one out of ${C.int(s.players)}.`;
  }

  function drawLorenz() {
    const s = cur(), svg = $("#lor"), W = svg.clientWidth || 700, H = 320, P0 = { l: 48, r: 16, t: 12, b: 32 };
    const x = C.scale(0, 1, P0.l, W - P0.r), y = C.scale(0, 1, H - P0.b, P0.t), k = s.lorLoss.length - 1;
    let g = "";
    for (let t = 0; t <= 1.0001; t += 0.25) {
      g += `<line x1="${P0.l}" x2="${W - P0.r}" y1="${y(t)}" y2="${y(t)}" stroke="var(--grid)"/><text x="${P0.l - 8}" y="${y(t) + 4}" text-anchor="end">${Math.round(t * 100)}%</text>`;
      g += `<text x="${x(t)}" y="${H - 12}" text-anchor="middle">${Math.round(t * 100)}%</text>`;
    }
    g += `<text x="${W - P0.r}" y="${H - 0}" text-anchor="end">share of players, biggest losers first</text>`;
    g += `<path d="M${x(0)} ${y(0)}L${x(1)} ${y(1)}" stroke="var(--line-2)" stroke-dasharray="2 4"/>`;
    const path = (arr) => arr.map((v, i) => `${i ? "L" : "M"}${x(i / k).toFixed(1)},${y(v).toFixed(1)}`).join("");
    g += `<path d="${path(s.lorTheo)}" fill="none" stroke="var(--series-base)" stroke-width="2" stroke-dasharray="4 3"/>`;
    g += `<path d="${path(s.lorLoss)}" fill="none" stroke="var(--accent)" stroke-width="2"/>`;
    // mark top 10%
    const i10 = Math.round(k * 0.1);
    g += `<line x1="${x(0.1)}" x2="${x(0.1)}" y1="${y(0)}" y2="${y(s.lorLoss[i10])}" stroke="var(--ink-3)" stroke-dasharray="2 3"/>
      <circle cx="${x(0.1)}" cy="${y(s.lorLoss[i10])}" r="4" fill="var(--accent)" stroke="var(--card)" stroke-width="2"/>
      <text x="${x(0.1) + 8}" y="${y(s.lorLoss[i10]) + 14}" style="fill:var(--ink)">Top 10%: ${C.pct(s.top10, 0)} of losses</text>`;
    g += `<rect x="${P0.l}" y="${P0.t}" width="${W - P0.l - P0.r}" height="${H - P0.t - P0.b}" fill="transparent" id="lor-hit"/><g id="lor-dot"></g>`;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.innerHTML = g;
    C.dataTable(svg, "lor-table", "Share of losses held by the biggest losers", ["Biggest losers", "Share of actual losses", "Share of expected losses (theo)"],
      [0.01, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1].map((f) => { const i = Math.round(k * f); return [C.pct(f, 0), C.pct(s.lorLoss[i], 0), C.pct(s.lorTheo[i], 0)]; }));
    $("#lor-note").innerHTML = `The top 1% of losers account for <span class="mono">${C.pct(s.top1, 1)}</span> of all losses, the top 10% for
      <span class="mono">${C.pct(s.top10, 0)}</span>. Expected losses (theo) are even more concentrated, <span class="mono">${C.pct(s.top10Theo, 0)}</span> in the top 10%,
      because a few players simply play much more; luck spreads actual results out. ${C.usd(s.losses, { short: true })} lost by players who finished down,
      ${C.usd(s.winnings, { short: true })} won by those who finished up.`;
    svg.onmousemove = (e) => {
      const r = svg.getBoundingClientRect(), px = ((e.clientX - r.left) / r.width) * W;
      const f = Math.max(0, Math.min(1, (px - P0.l) / (W - P0.l - P0.r))), i = Math.round(f * k);
      $("#lor-dot").innerHTML = `<circle cx="${x(i / k)}" cy="${y(s.lorLoss[i])}" r="4" fill="var(--accent)" stroke="var(--card)" stroke-width="2"/>
        <circle cx="${x(i / k)}" cy="${y(s.lorTheo[i])}" r="4" fill="var(--series-base)" stroke="var(--card)" stroke-width="2"/>`;
      C.tip(C.tipRows(`Top ${Math.round((i / k) * 100)}% of players`, [["Share of actual losses", C.pct(s.lorLoss[i], 0)], ["Share of expected losses", C.pct(s.lorTheo[i], 0)]]), e);
    };
    svg.onmouseleave = () => { C.tip(null); $("#lor-dot").innerHTML = ""; };
  }

  // ------------------------------------------------------------- tables
  function drawGroups() {
    const R = range(), rows = [["all", "All players"], ...Object.entries(P.groups).flatMap(([d, vals]) => vals.map((v) => [`${d}:${v}`, v, d]))];
    const tot = R.all.ci;
    let last = null;
    $("#groups").innerHTML = `<thead><tr><th>Group</th><th class="num">Players</th><th class="num">Wagers</th><th class="num">Net each</th><th class="num">Ahead</th></tr></thead><tbody>${rows.map(([k, name, d]) => {
      const s = R[k]; if (!s) return "";
      const head = d && d !== last ? `<tr><td colspan="5" class="small muted" style="padding-top:16px">${DIM[d]}</td></tr>` : "";
      last = d || last;
      return `${head}<tr class="clickable ${S.seg === k ? "on" : ""}" data-k="${k}" tabindex="0"><td>${name}</td><td class="num">${C.int(s.players)}</td>
        <td class="num">${C.pct(s.ci / tot, 0)}</td><td class="num">${C.usd((s.po - s.ci) / s.players)}</td><td class="num">${C.pct(s.ahead / s.players, 0)}</td></tr>`;
    }).join("")}</tbody>`;
    const go = (e) => { const tr = e.target.closest("tr[data-k]"); if (tr) setSeg(S.seg === tr.dataset.k ? "all" : tr.dataset.k); };
    $("#groups").onclick = go;
    $("#groups").onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(e); } };
  }

  const pfmt = (p) => (p == null ? "–" : p < 0.001 ? "<0.001" : p < 0.01 ? p.toFixed(3) : p.toFixed(2));
  // Expected result = expected payout − wagered (= −theo); actual result = payout − wagered.
  // Difference = actual − expected (same in payout or result terms); % is of the expected payout.
  const rowCells = (x) => {
    const diff = x.po - x.exp, pctd = x.exp > 0 ? diff / x.exp : null;
    return `<td><span class="mono">${x.id}</span><span class="sub">${[x.region, x.age, x.tier].filter(Boolean).join(", ")}</span></td>
      <td class="num">${C.usd(x.ci)}<span class="sub">${C.int(x.ses)} sessions</span></td>
      <td class="num">${C.usd(x.exp)}<span class="sub">${C.usd(x.po)} actual</span></td>
      <td class="num">${C.usd(x.exp - x.ci, { plus: true })}</td><td class="num">${C.usd(x.po - x.ci, { plus: true })}</td>
      <td class="num">${C.usd(diff, { plus: true })}</td><td class="num">${pctd == null ? "–" : C.pct(pctd, 0, true)}</td>
      <td class="num">${C.num(x.z, 1, true)}</td>
      <td class="num">${pfmt(x.mp)}<span class="sub">${peer(x.pct)}, ${C.esc(x.game || "")}</span></td>`;
  };
  const HEAD = `<th>Player</th><th class="num">Wagered</th><th class="num">Expected back</th><th class="num">Expected result</th><th class="num">Actual result</th>
    <th class="num">Difference</th><th class="num">% of expected back</th><th class="num">Payout z</th><th class="num">Payout p, vs peers</th>`;

  function drawHit() {
    const L = P.anomalies[`${S.a}-${S.b}`].filter((x) => x.list === "hit" && segOk(x)).sort((p, q) => p.hq - q.hq || Math.abs(q.hz) - Math.abs(p.hz)).slice(0, 25);
    const flagged = L.filter((x) => x.hq < 0.05), m1158 = flagged.filter((x) => x.mach === "M-1158" && x.machShare > 0.5).length;
    $("#hitl-p").innerHTML = `Players whose share of paying spins is furthest from what their games promise. Flagged means it survives correction for testing every player.
      ${flagged.length ? `<strong style="color:var(--ink);font-weight:500">${m1158} of ${flagged.length} flagged ${flagged.length === 1 ? "player" : "players"} played mostly on M-1158</strong>, the machine whose meters already showed a payout mismatch.` : "No player is flagged in this period and group."}`;
    $("#hitl").innerHTML = `<thead><tr><th>Player</th><th class="num">Spins</th><th class="num">Paying spins</th><th class="num">Expected</th><th class="num">Win-rate z</th><th class="num">p</th><th class="num">q, corrected</th><th>Main machine</th><th>Check</th></tr></thead><tbody>
      ${L.map((x) => `<tr class="${x.mach === "M-1158" ? "hl" : ""}"><td><span class="mono">${x.id}</span><span class="sub">${[x.region, x.age, x.tier].filter(Boolean).join(", ")}</span></td>
        <td class="num">${C.int(x.n)}</td><td class="num">${C.int(x.pos)}<span class="sub">${C.pct(x.pos / x.n, 1)}</span></td>
        <td class="num">${C.int(x.epos)}<span class="sub">${C.pct(x.epos / x.n, 1)}</span></td>
        <td class="num">${C.num(x.hz, 1, true)}</td><td class="num">${pfmt(x.hp)}</td><td class="num">${x.hq < 0.001 ? "<0.001" : x.hq.toFixed(3)}</td>
        <td><a class="mono" href="machines.html${location.search}#${x.mach}">${x.mach}</a><span class="sub">${C.pct(x.machShare, 0)} of their play, ${C.esc(x.game || "")}</span></td>
        <td>${x.hq < 0.05 ? '<span class="tag"><span class="dot lead"></span>Flagged</span>' : '<span class="tag muted">Within chance</span>'}</td></tr>`).join("") || '<tr><td colspan="9" class="empty">No players in this group.</td></tr>'}</tbody>`;
  }

  function drawMoney() {
    C.$$("#mdir button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.d === S.dir));
    const L = P.anomalies[`${S.a}-${S.b}`].filter((x) => x.list === "money" && segOk(x))
      .map((x) => ({ ...x, d: x.po - x.exp })).filter((x) => (S.dir === "up" ? x.d > 0 : x.d < 0))
      .sort((p, q) => (S.dir === "up" ? q.d - p.d : p.d - q.d)).slice(0, 20);
    $("#mon").innerHTML = `<thead><tr>${HEAD}</tr></thead><tbody>${L.map((x) => `<tr>${rowCells(x)}</tr>`).join("") ||
      '<tr><td colspan="9" class="empty">None of the period\'s largest results fall in this group. Load every player below to see the whole group.</td></tr>'}</tbody>`;
  }

  // ------------------------------------------------------------- every player (lazy)
  async function loadAll() {
    $("#load-all").disabled = true; $("#load-all").textContent = "Loading…";
    try {
      const A = await C.load("players_all"), G = P.groups;
      S.all = A.id.map((id, i) => {
        const exp = A.ci[i] - A.theo[i], diff = A.po[i] - exp;
        return { id, region: G.region[A.region[i]], age: G.age[A.age[i]], tier: G.tier[A.tier[i]], ses: A.ses[i], ci: A.ci[i], exp, po: A.po[i],
          diff, pctd: exp > 0 ? diff / exp : 0, z: A.sd[i] > 0 ? diff / A.sd[i] : 0, peer: A.pct[i], pct: A.pct[i], game: A.games[A.game[i]],
          hz: A.hz[i], hq: A.hq[i], hp: A.hp[i], mp: A.mp[i], mq: A.mq[i], n: A.n[i], pos: A.pos[i], epos: A.epos[i] };
      });
    } catch (e) { $("#load-all").textContent = "Couldn't load the file"; return; }
    $("#all-ctl").hidden = true; $("#all-wrap").hidden = false;
    $("#all-q").oninput = (e) => { S.q = e.target.value.trim().toUpperCase(); S.page = 0; drawAll(); };
    $("#all-sort").onchange = (e) => { S.sort = e.target.value; S.page = 0; drawAll(); };
    $("#all-ord").onclick = (e) => { const b = e.target.closest("button"); if (b) { S.ord = b.dataset.o; S.page = 0; drawAll(); } };
    $("#all-prev").onclick = () => { S.page = Math.max(0, S.page - 1); drawAll(); };
    $("#all-next").onclick = () => { S.page++; drawAll(); };
    drawAll();
  }
  function drawAll() {
    C.$$("#all-ord button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.o === S.ord));
    let L = S.all.filter(segOk);
    if (S.q) L = L.filter((x) => x.id.toUpperCase().includes(S.q));
    const k = S.sort, sgn = S.ord === "desc" ? -1 : 1;
    L = L.slice().sort((p, q) => sgn * (p[k] - q[k]));
    const per = 25, pages = Math.max(1, Math.ceil(L.length / per));
    S.page = Math.min(S.page, pages - 1);
    $("#all-count").textContent = `${C.int(L.length)} players, page ${S.page + 1} of ${C.int(pages)}${S.seg !== "all" ? ", " + segLabel() : ""}`;
    $("#all-prev").disabled = S.page === 0; $("#all-next").disabled = S.page >= pages - 1;
    $("#all").innerHTML = `<thead><tr>${HEAD}<th class="num">Win rate</th><th class="num">Win-rate z</th></tr></thead><tbody>${L.slice(S.page * per, S.page * per + per).map((x) => `<tr>${rowCells(x)}
      <td class="num">${C.pct(x.pos / x.n, 1)}<span class="sub">expected ${C.pct(x.epos / x.n, 1)}</span></td>
      <td class="num">${C.num(x.hz, 1, true)}<span class="sub" ${x.hq < 0.05 ? 'style="color:var(--neg)"' : ""}>p ${pfmt(x.hp)}${x.hq < 0.05 ? ", flagged" : ""}</span></td></tr>`).join("") ||
      '<tr><td colspan="11" class="empty">No players match.</td></tr>'}</tbody>`;
  }
})();
