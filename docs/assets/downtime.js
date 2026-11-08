/* Downtime page (question 3): how much play was lost to downtime and when. Data from data/downtime.js,
   built by scripts/build_site_downtime.py from operations, machine_day and the analysis/downtime.py valuation. */
(function () {
  "use strict";
  const C = window.Core, $ = C.$;
  const SHIFTS = { day: ["Day", "6 a.m. – 2 p.m."], swing: ["Swing", "2 p.m. – 10 p.m."], grave: ["Grave", "10 p.m. – 6 a.m."] };
  const S = { a: 0, b: 5 };
  let D;

  document.addEventListener("DOMContentLoaded", async () => {
    try { D = await C.load("downtime"); } catch (e) { return C.fail($("#main"), e); }
    [S.a, S.b] = C.periodControl($("#period"), (a, b) => { S.a = a; S.b = b; render(); });
    render(); tables();
    addEventListener("resize", charts);
    addEventListener("themechange", charts);
  });

  const inP = (m) => m.m >= S.a && m.m <= S.b;
  function render() {
    $("#title").textContent = `Downtime, ${C.periodLabel(S.a, S.b)}`;
    const ms = D.months.filter(inP), T = D.totals;
    const sum = (k) => ms.reduce((t, m) => t + m[k], 0);
    const share = sum("lost") / T.lostFault;   // the cruder valuations scaled to the period by the same share
    const theo = sum("theo"), down = sum("meterDownH");
    const sched = ms.reduce((t, m) => t + m.meterDownH / (1 - m.availability), 0);   // scheduled = down / (1 − availability)
    $("#stats").innerHTML = [
      ["Machine-hours down", C.int(down), `${C.pct(down / sched, 1)} of scheduled time; ${C.int(sum("faults"))} faults`],
      ["Theo lost", `${C.usd(T.lostFlat * share, { short: true })}–${C.usd(sum("lost"), { short: true })}`, `${C.pct(sum("lost") / theo, 1)} of the period's theo; range by how a down hour is valued`],
      ["Average fault", `${C.num(sum("waitH") / sum("faults"), 1)} h + ${C.num(sum("fixH") / sum("faults"), 1)} h`, "Waiting for a technician, then being fixed"],
      ["Repairs cost, Jan–Jun", C.usd(T.repairCost, { short: true }), `More than the ${C.usd(T.lostFault, { short: true })} of play the faults cost`],
    ].map(([l, v, f], i) => `<div class="stat"><div class="label">${l}</div><div class="value${i === 1 ? " accent" : ""}">${v}</div><div class="foot">${f}</div></div>`).join("");
    $("#mon-t").innerHTML = `<thead><tr><th>Month</th><th class="num">Faults</th><th class="num">Fault hours</th><th class="num">Waiting</th><th class="num">Fixing</th><th class="num">Availability</th><th class="num">Theo lost</th></tr></thead><tbody>
      ${D.months.map((m) => `<tr class="${inP(m) ? "" : "muted"}"><td>${C.MONTHS[m.m]}</td><td class="num">${C.int(m.faults)}</td><td class="num">${C.int(m.downH)}</td>
        <td class="num">${C.int(m.waitH)}</td><td class="num">${C.int(m.fixH)}</td><td class="num">${C.pct(m.availability, 2)}</td><td class="num">${C.usd(m.lost)}</td></tr>`).join("")}</tbody>`;
    charts();
  }

  function charts() { if (D) { monthChart(); hourChart(); } }

  function monthChart() {
    const svg = $("#mon"), W = svg.clientWidth || 800, H = 240, P = { l: 52, r: 8, t: 12, b: 26 };
    const max = Math.ceil(Math.max(...D.months.map((m) => m.downH)) / 200) * 200;
    const y = C.scale(0, max, H - P.b, P.t), bw = (W - P.l - P.r) / 6;
    let g = "";
    for (let t = 0; t <= max; t += 200) g += `<line x1="${P.l}" x2="${W - P.r}" y1="${y(t)}" y2="${y(t)}" stroke="var(--grid)"/><text x="${P.l - 6}" y="${y(t) + 4}" text-anchor="end">${t} h</text>`;
    D.months.forEach((m, i) => {
      const x0 = P.l + i * bw + bw * 0.2, w = bw * 0.6, op = inP(m) ? 1 : 0.35;
      g += `<g opacity="${op}" data-i="${i}"><rect x="${x0}" y="${y(m.fixH)}" width="${w}" height="${y(0) - y(m.fixH)}" fill="var(--ink-3)" fill-opacity=".55"/>
        <rect x="${x0}" y="${y(m.fixH + m.waitH)}" width="${w}" height="${y(m.fixH) - y(m.fixH + m.waitH)}" fill="var(--accent)"/>
        <rect x="${x0}" y="${P.t}" width="${w}" height="${H - P.b - P.t}" fill="transparent"/></g>
        <text x="${x0 + w / 2}" y="${H - 8}" text-anchor="middle">${C.MONTHS[i]}</text>`;
    });
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.innerHTML = g;
    svg.onmousemove = (e) => {
      const t = e.target.closest("[data-i]"); if (!t) return C.tip(null);
      const m = D.months[+t.dataset.i];
      C.tip(C.tipRows(`${C.MONTHS[m.m]} 2025`, [["Faults", C.int(m.faults)], ["Waiting", `${C.int(m.waitH)} h`], ["Fixing", `${C.int(m.fixH)} h`], ["Theo lost", C.usd(m.lost)]]), e);
    };
    svg.onmouseleave = () => C.tip(null);
  }

  function hourChart() {
    const svg = $("#hr"), W = svg.clientWidth || 500, H = 240, P = { l: 52, r: 8, t: 22, b: 26 };
    const hs = Array.from({ length: 24 }, (_, h) => D.hours.find((r) => r.h === h) || { h, faults: 0, lost: 0, wait: 0, fix: 0 });
    const max = Math.ceil(Math.max(...hs.map((r) => r.lost)) / 4000) * 4000;
    const y = C.scale(0, max, H - P.b, P.t), bw = (W - P.l - P.r) / 24, x = (h) => P.l + h * bw;
    let g = "";
    [[6, 14, "Day"], [14, 22, "Swing"]].forEach(([a, b, t], k) => {
      g += `<rect x="${x(a)}" y="${P.t}" width="${x(b) - x(a)}" height="${H - P.b - P.t}" fill="var(--raised)" opacity="${k ? 0.9 : 0.45}"/><text x="${(x(a) + x(b)) / 2}" y="${P.t - 8}" text-anchor="middle">${t}</text>`;
    });
    g += `<text x="${(x(0) + x(6)) / 2}" y="${P.t - 8}" text-anchor="middle">Grave</text>`;
    for (let t = 0; t <= max; t += max / 4) g += `<line x1="${P.l}" x2="${W - P.r}" y1="${y(t)}" y2="${y(t)}" stroke="var(--grid)"/><text x="${P.l - 6}" y="${y(t) + 4}" text-anchor="end">$${(t / 1000).toFixed(0)}K</text>`;
    hs.forEach((r) => {
      g += `<rect x="${x(r.h) + 1}" y="${y(r.lost)}" width="${Math.max(1, bw - 2)}" height="${y(0) - y(r.lost)}" rx="1.5" fill="var(--accent)" data-h="${r.h}"/>`;
      if (r.h % 6 === 0) g += `<text x="${x(r.h)}" y="${H - 8}">${r.h === 0 ? "12a" : r.h === 12 ? "12p" : r.h < 12 ? r.h + "a" : r.h - 12 + "p"}</text>`;
    });
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.innerHTML = g;
    svg.onmousemove = (e) => {
      const t = e.target.closest("[data-h]"); if (!t) return C.tip(null);
      const r = hs[+t.dataset.h];
      C.tip(C.tipRows(`${String(r.h).padStart(2, "0")}:00–${String(r.h).padStart(2, "0")}:59`, [["Faults opened", C.int(r.faults)], ["Mean wait", `${C.num(r.wait, 1)} h`], ["Mean fix", `${C.num(r.fix, 1)} h`], ["Theo lost", C.usd(r.lost)]]), e);
    };
    svg.onmouseleave = () => C.tip(null);
  }

  function tables() {
    const T = D.totals;
    const shifts = ["day", "swing", "grave"].map((k) => D.shifts.find((s) => s.shift === k));
    $("#sh").innerHTML = `<thead><tr><th>Shift</th><th class="num">Faults</th><th class="num">Mean wait</th><th class="num">Mean fix</th><th class="num">Theo lost</th></tr></thead><tbody>
      ${shifts.map((s) => `<tr><td>${SHIFTS[s.shift][0]}<span class="sub">${SHIFTS[s.shift][1]}</span></td><td class="num">${C.int(s.faults)}</td>
        <td class="num">${C.num(s.wait, 1)} h</td><td class="num">${C.num(s.fix, 1)} h</td><td class="num">${C.usd(s.lost)} <span class="muted">${C.pct(s.lost / T.lostFault, 0)}</span></td></tr>`).join("")}</tbody>`;
    $("#mk").innerHTML = `<thead><tr><th>Maker</th><th class="num">Machines</th><th class="num">Faults per machine-month</th><th class="num">Rate vs Halcyon</th><th class="num">Theo + repairs per 30 days</th><th class="num">Sweep break-even</th></tr></thead><tbody>
      ${D.makers.slice().sort((a, b) => b.perMachineMonth - a.perMachineMonth).map((m) => { const r = D.irr[m.maker];
        return `<tr class="${m.maker === "Ridgeline" ? "hl" : ""}"><td>${m.maker}</td><td class="num">${m.machines}</td><td class="num">${C.num(m.perMachineMonth, 2)}</td>
        <td class="num">${r ? `${C.num(r[0], 1)}× <span class="muted">(${C.num(r[1], 1)}–${C.num(r[2], 1)})</span>` : "1.0×, reference"}</td>
        <td class="num">${C.usd(m.per30)}</td><td class="num">${C.pct(m.breakeven, 0)} fewer faults</td></tr>`; }).join("")}</tbody>`;
    $("#zn").innerHTML = `<thead><tr><th>Zone</th><th class="num">Faults</th><th class="num">Fault hours</th><th class="num">Theo lost</th></tr></thead><tbody>
      ${D.zones.slice().sort((a, b) => b.lost - a.lost).map((z) => `<tr class="${z.id === "Z-B40" ? "hl" : ""}"><td>${C.esc(z.zone)}</td><td class="num">${C.int(z.faults)}</td>
        <td class="num">${C.int(z.downH)}</td><td class="num">${C.usd(z.lost)}</td></tr>`).join("")}</tbody>`;
    $("#tech").innerHTML = `<thead><tr><th>Option</th><th class="num">Down hours saved, 6 months</th><th class="num">Theo recovered per 30 days</th><th class="num">Cost per 30 days</th><th class="num">Net per 30 days</th></tr></thead><tbody>
      ${D.tech.map((t) => `<tr><td>${C.esc(t.scenario.replace("+1 tech", "One more technician"))}</td><td class="num">${C.int(t.hoursSaved)}</td><td class="num">${C.usd(t.saved30)}</td>
        <td class="num">${C.usd(t.cost30)}</td><td class="num" style="color:var(--neg)">${C.usd(t.net30)}</td></tr>`).join("")}
      ${D.makers.filter((m) => m.maker === "Ridgeline").map((m) => `<tr class="hl"><td>Ridgeline maintenance sweep, at a 40% fault cut</td><td class="num">–</td>
        <td class="num">${C.usd(0.4 * m.per30)}</td><td class="num">${C.usd(m.sweep)}</td><td class="num" style="color:var(--pos)">${C.usd(0.4 * m.per30 - m.sweep, { plus: true })}</td></tr>`).join("")}</tbody>`;
    const rc = D.recapture;
    $("#fix-note").innerHTML = `Players don't move to the next machine (bank play ${C.pct(rc.share, 0, true)}, 90% CI ${C.pct(rc.lo, 0, true)} to ${C.pct(rc.hi, 0, true)}), so lost play is lost.
      The 40% cut is an assumption: <a href="actions.html#sens-h">sensitivity</a>.`;
    $("#top").innerHTML = `<thead><tr><th>Machine</th><th>Zone</th><th>Maker</th><th class="num">Faults</th><th class="num">Fault hours</th><th class="num">Theo lost</th></tr></thead><tbody>
      ${D.top.map((t) => `<tr><td><a href="machines.html#${t.id}">${t.id}</a></td><td>${C.esc(t.zone)}</td><td>${C.esc(t.maker)}</td><td class="num">${t.faults}</td>
        <td class="num">${C.num(t.downH, 0)}</td><td class="num">${C.usd(t.lost)}</td></tr>`).join("")}</tbody>`;
  }
})();
