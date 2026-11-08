/* Machines page: luck z for every machine over the chosen period, BH-corrected flags,
   payout-rate check, the GM's bottom 10 with verdicts, and a sortable ranking. */
(function () {
  "use strict";
  const C = window.Core, $ = C.$;
  const S = { a: 0, b: 5, order: "best", q: "", zone: "", all: false, hl: null, onlyFlags: false };
  let F, M, PF, rows, zoneName, bankOf, flags;

  document.addEventListener("DOMContentLoaded", async () => {
    try { [F, M, PF] = await Promise.all([C.load("floor"), C.load("machines"), C.load("player_flags")]); }
    catch (e) { return C.fail($("#main"), e); }
    zoneName = Object.fromEntries(F.zones.map((z) => [z.id, z.name]));
    bankOf = Object.fromEntries(F.slots.map((s) => [s.id, s]));
    $("#zone").innerHTML += F.zones.map((z) => `<option value="${z.id}">${C.esc(z.name)}</option>`).join("");
    S.hl = location.hash.slice(1) || null;
    if (S.hl) { S.order = "worst"; S.all = true; }
    [S.a, S.b] = C.periodControl($("#period"), (a, b) => { S.a = a; S.b = b; render(); });
    $("#q").oninput = (e) => { S.q = e.target.value.trim().toLowerCase(); drawRank(); };
    $("#zone").onchange = (e) => { S.zone = e.target.value; drawRank(); };
    $("#order").onclick = (e) => { const b = e.target.closest("button"); if (b) { S.order = b.dataset.o; drawRank(); } };
    $("#more").onclick = () => { S.all = !S.all; drawRank(); };
    $("#fl").onclick = (e) => { const b = e.target.closest("button"); if (b) { S.onlyFlags = b.dataset.f === "1"; drawRank(); } };
    render();
    addEventListener("themechange", drawCat);
    addEventListener("resize", drawCat);
    if (S.hl) setTimeout(() => document.getElementById("row-" + S.hl)?.scrollIntoView({ block: "center" }), 50);
  });

  function render() {
    $("#title").textContent = `Luck ranking, ${C.periodLabel(S.a, S.b)}`;
    rows = M.map((m) => ({ m, s: C.agg(m, S.a, S.b) })).filter((r) => r.s.n > 0);
    const q = C.bh(rows.map((r) => r.s.p));
    const qh = C.bh(rows.map((r) => C.p2(r.s.hitZ)));
    flags = C.machineFlags(M, S.a, S.b, PF);
    rows.forEach((r, i) => {
      r.q = q[i]; r.qh = qh[i]; r.flag = flags[r.m.id];
      r.zone = bankOf[r.s.loc]?.zone ?? r.m.zone;
    });
    drawStats(); drawFlags(); drawCat(); drawB10(); drawRank();
  }

  function drawStats() {
    const n = rows.length, out = rows.filter((r) => Math.abs(r.s.z) > 1.96).length;
    const flagged = rows.filter((r) => r.q < 0.05).length, leads = rows.filter((r) => r.qh < 0.05);
    const worst = rows.reduce((w, r) => (r.s.luck < w.s.luck ? r : w), rows[0]);
    $("#stats").innerHTML = [
      ["Outside the fair range", `${out}`, `of ${n} machines; about ${Math.round(n * 0.05)} expected by chance`],
      ["Luck flags after correction", `${flagged}`, "Benjamini–Hochberg, 5% false discovery rate"],
      ["Flagged machines", `${rows.filter((r) => r.flag?.level === "flag").length}`, `${rows.filter((r) => r.flag?.level === "watch").length} more on watch; ${leads.length} with payout rate off configuration`],
      ["Largest luck deficit", C.usd(worst.s.luck, { short: true }), `${worst.m.id}, z ${C.num(worst.s.z, 1)}`],
    ].map(([l, v, f], i) => `<div class="stat"><div class="label">${l}</div><div class="value${i === 2 ? " accent" : ""}">${v}</div><div class="foot">${f}</div></div>`).join("");
  }

  // ------------------------------------------------------------- flags panel
  function drawFlags() {
    const list = rows.filter((r) => r.flag).sort((p, q) => (p.flag.level === q.flag.level ? Math.abs(q.s.z) - Math.abs(p.s.z) : p.flag.level === "flag" ? -1 : 1));
    $("#flags").innerHTML = list.length ? `<thead><tr><th>Machine</th><th>Zone</th><th>Flag</th><th>Why</th><th class="num">Luck</th><th>Hold</th></tr></thead><tbody>${list.map((r) => `
      <tr class="clickable" data-id="${r.m.id}" tabindex="0"><td><span class="mono">${r.m.id}</span><span class="sub">${C.esc(r.m.theme)}</span></td><td>${C.esc(zoneName[r.zone] ?? "")}</td>
        <td>${C.flagTag(r.flag)}</td><td style="color:var(--ink-2)">${r.flag.reasons.map(C.esc).join("<br>")}</td>
        <td class="num">${C.usd(r.s.luck, { plus: true })}</td><td>${C.holdBand(r.s)}</td></tr>`).join("")}</tbody>`
      : `<tbody><tr><td class="empty">No machine is flagged or on watch in this period.</td></tr></tbody>`;
    $("#flags").onclick = (e) => {
      const tr = e.target.closest("tr[data-id]"); if (!tr) return;
      S.hl = tr.dataset.id; S.all = true; S.onlyFlags = false; history.replaceState(null, "", "#" + S.hl); drawRank();
      document.getElementById("row-" + S.hl)?.scrollIntoView({ behavior: "smooth", block: "center" });
    };
  }

  // ------------------------------------------------------------- caterpillar
  function drawCat() {
    const svg = $("#cat"); if (!rows) return;
    const W = svg.clientWidth || 900, H = 300, P = { l: 40, r: 16, t: 12, b: 28 };
    const sorted = rows.slice().sort((p, q) => q.s.z - p.s.z);
    const lim = Math.max(4, Math.ceil(Math.max(...sorted.map((r) => Math.abs(r.s.z)))));
    const x = C.scale(0, sorted.length - 1, P.l + 4, W - P.r - 4), y = C.scale(-lim, lim, H - P.b, P.t);
    let g = `<rect x="${P.l}" y="${y(1.96)}" width="${W - P.l - P.r}" height="${y(-1.96) - y(1.96)}" fill="var(--band)" rx="4"/>`;
    for (let v = -lim; v <= lim; v += lim > 6 ? 2 : 1) {
      g += `<line x1="${P.l}" x2="${W - P.r}" y1="${y(v)}" y2="${y(v)}" stroke="var(--grid)"/>
        <text x="${P.l - 8}" y="${y(v) + 4}" text-anchor="end">${v > 0 ? "+" + v : v < 0 ? "−" + -v : 0}</text>`;
    }
    const sfx = W < 560 ? "" : " for the house";
    g += `<text x="${P.l}" y="${H - 8}">Luckiest${sfx}</text><text x="${W - P.r}" y="${H - 8}" text-anchor="end">Unluckiest${sfx}</text>`;
    sorted.forEach((r, i) => {
      const lead = r.flag?.level === "flag", watch = r.flag?.level === "watch";
      const fill = lead ? "var(--neg)" : Math.abs(r.s.z) > 1.96 ? "var(--ink-2)" : "var(--ink-3)";
      g += `<circle data-i="${i}" cx="${x(i)}" cy="${y(r.s.z)}" r="${lead ? 4.5 : 2.6}" fill="${fill}" fill-opacity="${lead ? 1 : 0.75}" stroke="var(--card)" stroke-width="1"/>`;
      if (watch) g += `<circle cx="${x(i)}" cy="${y(r.s.z)}" r="4.5" fill="none" stroke="var(--neg)" stroke-width="1.5" pointer-events="none"/>`;
      if (r.m.b10) g += `<circle cx="${x(i)}" cy="${y(r.s.z)}" r="5" fill="none" stroke="var(--ink)" stroke-width="1.3" pointer-events="none"/>`;
      if (lead) g += `<text x="${x(i) - 10}" y="${y(r.s.z) + 4}" text-anchor="end" style="fill:var(--ink)">${r.m.id}</text>`;
    });
    g += `<line id="cat-x" y1="${P.t}" y2="${H - P.b}" stroke="var(--ink-3)" stroke-width="1" opacity="0"/>`;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.innerHTML = g;
    svg.onmousemove = (e) => {
      const r = svg.getBoundingClientRect(), px = ((e.clientX - r.left) / r.width) * W;
      const i = Math.round(((px - P.l - 4) / (W - P.l - P.r - 8)) * (sorted.length - 1));
      const d = sorted[i]; if (!d) return C.tip(null);
      const ln = $("#cat-x"); ln.setAttribute("x1", x(i)); ln.setAttribute("x2", x(i)); ln.setAttribute("opacity", 0.4);
      C.tip(C.tipRows(`<span class="mono">${d.m.id}</span> · ${C.esc(d.m.theme)}`, [
        ["Zone", zoneName[d.zone]], ["Luck", C.usd(d.s.luck, { plus: true })], ["z", C.num(d.s.z, 2, true)],
        ["BH q", d.q < 0.001 ? "< 0.001" : d.q.toFixed(2)], ["Hold", `${C.pct(d.s.hold)} vs ${C.pct(d.s.theoHold)}`],
      ]) + (d.flag ? `<div class="small" style="margin-top:4px;color:var(--neg)">${d.flag.level === "flag" ? "Flagged" : "Watch"}: ${C.esc(d.flag.reasons[0])}</div>` : "") + (d.m.b10 ? `<div class="small muted" style="margin-top:4px">GM's bottom 10, rank ${d.m.b10.rank}</div>` : ""), e);
    };
    svg.onmouseleave = () => { C.tip(null); $("#cat-x")?.setAttribute("opacity", 0); };
    svg.onclick = (e) => {
      const r = svg.getBoundingClientRect(), px = ((e.clientX - r.left) / r.width) * W;
      const d = sorted[Math.round(((px - P.l - 4) / (W - P.l - P.r - 8)) * (sorted.length - 1))];
      if (!d) return;
      S.hl = d.m.id; S.all = true; S.q = ""; $("#q").value = ""; S.zone = ""; $("#zone").value = "";
      history.replaceState(null, "", "#" + d.m.id); drawRank();
      document.getElementById("row-" + d.m.id)?.scrollIntoView({ behavior: "smooth", block: "center" });
    };
  }

  // ------------------------------------------------------------- bottom 10
  function drawB10() {
    const list = M.filter((m) => m.b10).sort((p, q) => p.b10.rank - q.b10.rank).map((m) => ({ m, s: C.agg(m, 0, 5) }));
    $("#b10").innerHTML = `<thead><tr><th class="num">Rank</th><th>Machine</th><th>Zone</th><th class="num">House win</th><th class="num">Theo</th>
      <th class="num">Luck</th><th>Hold</th><th>Flag</th><th>Verdict</th><th>Action</th></tr></thead><tbody>${list.map(({ m, s }) => `
      <tr id="b10-${m.id}" ${S.hl === m.id ? 'class="on"' : ""}>
        <td class="num">${m.b10.rank}</td>
        <td><span class="mono">${m.id}</span><span class="sub">${C.esc(m.theme)}, ${s.days} days</span></td>
        <td>${C.esc(zoneName[m.zone])}</td>
        <td class="num">${C.usd(s.win)}</td><td class="num">${C.usd(s.theo)}</td>
        <td class="num">${C.usd(s.luck, { plus: true })}<span class="sub">z ${C.num(s.z, 1, true)}</span></td>
        <td>${C.holdBand(s)}</td>
        <td>${C.flagTag(flags[m.id])}</td>
        <td>${m.b10.verdict.startsWith("Leak") ? '<span class="tag"><span class="dot lead"></span>' : '<span class="tag">'}${C.esc(m.b10.verdict)}</span></td>
        <td class="small" style="color:var(--ink-2);max-width:260px">${C.esc(m.b10.action)}</td></tr>`).join("")}</tbody>`;
  }

  // ------------------------------------------------------------- ranking
  function drawRank() {
    C.$$("#order button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.o === S.order));
    let list = rows.slice().sort((p, q) => (S.order === "best" ? q.s.z - p.s.z : p.s.z - q.s.z));
    list.forEach((r, i) => { r.rank = i + 1; });
    if (S.zone) list = list.filter((r) => r.zone === S.zone);
    if (S.q) list = list.filter((r) => (r.m.id + " " + r.m.theme + " " + r.m.mfr).toLowerCase().includes(S.q));
    if (S.onlyFlags) list = list.filter((r) => r.flag);
    C.$$("#fl button").forEach((b) => b.setAttribute("aria-pressed", (b.dataset.f === "1") === S.onlyFlags));
    const shown = S.all ? list : list.slice(0, 25);
    $("#more").textContent = S.all ? "Show the first 25" : `Show all ${list.length}`;
    $("#more").hidden = list.length <= 25;
    $("#rank").innerHTML = `<thead><tr><th class="num">#</th><th>Machine</th><th>Zone</th><th class="num">Days</th><th class="num">Coin-in</th>
      <th class="num">House win</th><th class="num">Theo</th><th class="num">Luck</th><th class="num">z</th><th class="num">BH q</th><th>Hold</th><th>Flag</th></tr></thead>
      <tbody>${shown.map((r) => `<tr id="row-${r.m.id}" class="${S.hl === r.m.id ? "on" : ""}${r.m.b10 ? " hl" : ""}">
        <td class="num">${r.rank}</td>
        <td><span class="mono">${r.m.id}</span><span class="sub">${C.esc(r.m.theme)} · ${C.esc(r.m.mfr)}</span></td>
        <td>${C.esc(zoneName[r.zone] ?? "")}</td>
        <td class="num">${r.s.days}</td><td class="num">${C.usd(r.s.ci, { short: true })}</td>
        <td class="num">${C.usd(r.s.win, { short: true })}</td><td class="num">${C.usd(r.s.theo, { short: true })}</td>
        <td class="num">${C.usd(r.s.luck, { plus: true })}</td><td class="num">${C.num(r.s.z, 2, true)}</td>
        <td class="num">${r.q < 0.001 ? "<0.001" : r.q.toFixed(2)}</td>
        <td>${C.holdBand(r.s)}</td>
        <td>${C.flagTag(r.flag)}${r.flag ? `<span class="sub" style="max-width:240px;white-space:normal">${C.esc(r.flag.reasons[0])}</span>` : ""}</td>
      </tr>`).join("") || '<tr><td colspan="12" class="empty">No machines match.</td></tr>'}</tbody>`;
  }
})();
