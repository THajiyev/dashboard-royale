/* Correlations page: daily metrics (raw / weekday-removed), machines, players, forecast errors. */
(function () {
  "use strict";
  const C = window.Core, $ = C.$;
  let dayMode = "resid";

  C.registerPage("correlations.html", async () => {
    let D;
    try { D = await C.load("corr"); } catch (e) { return C.fail($("#main"), e); }
    if (!C.pageActive()) return;
    $("#key").innerHTML = `<span class="scale">−1<span class="ramp" style="background:${C.gradient(C.DIV)}"></span>+1</span><span><i class="ns"></i>Not significant (q ≥ 0.05)</span>`;
    const draw = () => { daily(D); machines(D); players(D); errors(D); };
    draw();
    $("#day-mode").onclick = (e) => {
      const b = e.target.closest("button[data-m]"); if (!b) return;
      C.$$("button", $("#day-mode")).forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      dayMode = b.dataset.m; daily(D);
    };
    C.listen(window, "resize", draw);
    C.listen(window, "themechange", draw);
  });

  const r2 = (v) => (v == null ? "–" : v.toFixed(2).replace("-", "−"));
  const r3 = (v) => (v == null ? "–" : (Object.is(v, -0) ? 0 : v).toFixed(3).replace("-", "−"));
  const q = (x) => `q ${C.peq(x.q)}`;
  const pairTable = (el, M, sym) => {
    const rows = C.topPairs(M, 8);
    el.innerHTML = `<thead><tr><th>Strongest significant pairs</th><th></th><th class="num">${sym}</th><th class="num">q</th><th class="num">n</th></tr></thead><tbody>
      ${rows.map((x) => `<tr><td>${C.esc(x.a)}</td><td>${C.esc(x.b)}</td><td class="num">${r2(x.r)}</td><td class="num">${C.pfmt(x.q)}</td><td class="num">${C.int(x.n)}</td></tr>`).join("")}</tbody>`;
  };

  function daily(D) {
    const B = D.daily, M = { vars: B.vars, ...B.modes[dayMode] };
    C.matrix($("#day"), M, { kind: "r", focus: ["Theo", "Rain", "Hold"] });
    $("#day-meta").textContent = dayMode === "resid" ? `Pearson r · ${B.n_resid} ordinary days` : `Pearson r · all ${B.n_days} days`;
    pairTable($("#day-top"), M, "r");
    const f = (a, b) => C.find(M, a, b);
    const say = $("#day-says");
    if (dayMode === "raw") {
      const tz = f("Theo", "Zone entries"), th = f("Theo", "Occupied hours"), hold = f("Theo", "Hold");
      say.innerHTML = `<li><b>Everything tied to play moves together</b>: theo with occupied hours ${r2(th.r)}, with zone entries ${r2(tz.r)}. That's the weekday cycle measured twice, not a finding.</li>
        <li><b>Hold doesn't follow the crowd</b> even here (${r2(hold.r)} with theo): busier days don't produce luckier or unluckier slots.</li>
        <li>Switch to <b>Weekday and trend removed</b> to see what co-moves beyond the calendar.</li>`;
    } else {
      const rl = f("Locals' theo", "Rain"), rv = f("Visitors' theo", "Rain"), re = f("Zone entries", "Rain");
      const hh = f("House win", "Hold"), ht = f("Theo", "Hold"), hz = f("Zone entries", "Hold");
      const fa = f("Available hours", "Faults"), ft = f("Theo", "Faults");
      const fb = f("Zone entries", "F&B cash"), cg = f("Occupied hours", "Comps given"), tz = f("Zone entries", "High temp");
      say.innerHTML = `<li><b>Rain is the one outside force</b>: wet days cut locals' play (${r2(rl.r)}, ${q(rl)}) far more than visitors' (${r2(rv.r)}), and footfall with it (${r2(re.r)}). Visitors are already inside; locals stay home.</li>
        <li><b>Hold is luck</b>: it moves with house win (${r2(hh.r)}) and with nothing that measures demand (theo ${r2(ht.r)}, entries ${r2(hz.r)}). A good or bad win day says nothing about traffic.</li>
        <li><b>Spend follows play</b>: F&B cash with entries ${r2(fb.r)}, comps with occupied hours ${r2(cg.r)}.</li>
        <li><b>Faults cost hours, not demand</b>: more faults mean fewer available hours (${r2(fa.r)}, ${q(fa)}), but no measurable dent in theo (${r2(ft.r)}).</li>
        <li><b>Heat barely matters</b>: hotter-than-recent days bring slightly more entries (${r2(tz.r)}).</li>`;
    }
  }

  function machines(D) {
    const B = D.machines, M = { vars: B.vars, ...B.modes.all }, f = (a, b) => C.find(M, a, b);
    C.matrix($("#mac"), M, { kind: "r", sym: "ρ", focus: ["Luck z, Jan–Apr", "Luck z, May–Jun", "Theo/day, Jan–Apr", "Theo/day, May–Jun"] });
    $("#mac-meta").textContent = `Spearman ρ · ${B.n} machines`;
    const th = f("Theo/day, Jan–Apr", "Theo/day, May–Jun"), oc = f("Occupancy, Jan–Apr", "Occupancy, May–Jun");
    const lk = f("Luck z, Jan–Apr", "Luck z, May–Jun"), lt = f("Luck z, Jan–Apr", "Theo/day, May–Jun");
    const he = f("Theo/day, Jan–Apr", "House edge (config)"), af = f("Availability", "Faults / 1,000 h"), ob = f("Occupancy, Jan–Apr", "Average bet");
    const X = B.luckCheck;
    $("#mac-says").innerHTML = `<li><b>Earning power persists almost perfectly</b>: theo per day ${r2(th.r)} and occupancy ${r2(oc.r)} from one period to the next. Spot and game set them, and they don't drift.</li>
      <li><b>Luck barely carries over</b>: luck z ${r2(lk.r)} (${q(lk)}), about ${C.pct(lk.r * lk.r, 0)} of the variation. It holds without the machine whose payout rate is off configuration (${r2(X.excl_payout_off.r)}) and is strongest on high-volatility games (${r2(X.by_vol.high.r)}). That's real but far too weak to rank machines on.</li>
      <li><b>Past luck doesn't predict future earnings</b>: luck z in Jan–Apr against theo per day in May–Jun, ${r2(lt.r)} (${q(lt)}).</li>
      <li><b>Tighter games earn more theo per day</b> (${r2(he.r)}), and bigger average bets mean lower occupancy (${r2(ob.r)}).</li>
      <li>Availability and fault rate are two views of one thing (${r2(af.r)}).</li>`;
  }

  function players(D) {
    const B = D.players, M = { vars: B.vars, ...B.modes.all }, f = (a, b) => C.find(M, a, b);
    C.matrix($("#ply"), M, { kind: "r", sym: "ρ", focus: ["Luck ÷ theo, Jan–Mar", "Luck ÷ theo, Apr–Jun"] });
    $("#ply-meta").textContent = `Spearman ρ · ${C.int(B.n)} carded players`;
    const v = f("Visits, Jan–Mar", "Visits, Apr–Jun"), t = f("Theo, Jan–Mar", "Theo, Apr–Jun");
    const l = f("Luck ÷ theo, Jan–Mar", "Luck ÷ theo, Apr–Jun"), lv = f("Luck ÷ theo, Jan–Mar", "Visits, Apr–Jun");
    const ch = f("Play hours", "Comps"), ct = f("Theo, Jan–Mar", "Comps ÷ theo"), P = B.luckReturn;
    $("#ply-says").innerHTML = `<li><b>Habits persist</b>: visits ${r2(v.r)} and theo ${r2(t.r)} from Jan–Mar to Apr–Jun.</li>
      <li><b>Luck doesn't</b>: a player's luck in Jan–Mar against Apr–Jun, ${r2(l.r)}. With ${C.int(B.n)} players even this is "significant" (${q(l)}), but it's negligible. Nobody is beating the games, which supports the Players page.</li>
      <li><b>A correlation that isn't a cause</b>: lucky players seem to return more (${r2(lv.r)}). Holding their Jan–Mar visits and theo fixed, it drops to ${r2(P.r)} (p ${C.peq(P.p)}). Heavy players just have both.</li>
      <li><b>Comps follow play</b>: comps with play hours ${r2(ch.r)}, while comps ÷ theo barely moves with theo (${r2(ct.r)}). Reinvestment is close to flat across player sizes.</li>`;
    const A = B.age, strongest = A.rows.reduce((best, row) => Math.abs(row.r) > Math.abs(best.r) ? row : best);
    $("#age-meta").textContent = `Spearman ρ · ${C.int(A.n)} carded players with known age`;
    $("#age-tab").innerHTML = `<thead><tr><th>Player measure</th><th class="num">ρ</th><th class="num">q (BH)</th><th class="num">n</th></tr></thead><tbody>
      ${A.rows.map((row) => `<tr><td>${C.esc(row.metric)}</td><td class="num">${r3(row.r)}</td><td class="num">${C.pfmt(row.q)}</td><td class="num">${C.int(row.n)}</td></tr>`).join("")}</tbody>`;
    const significant = A.rows.filter((row) => row.q < 0.05);
    $("#age-says").innerHTML = significant.length
      ? `<li><b>${significant.length} of four age relationships survive correction.</b> The largest is age band with ${C.esc(strongest.metric)} (ρ ${r3(strongest.r)}, ${C.pfmt(strongest.q)}).</li>
        <li>These are associations in synthetic carded-player data, not evidence that age causes a play pattern.</li>`
      : `<li><b>No age relationship survives correction.</b> The largest effect is age band with ${C.esc(strongest.metric)} (ρ ${r3(strongest.r)}, q ${C.pfmt(strongest.q)}), which is negligible.</li>
        <li>These are associations in synthetic carded-player data, not evidence that age causes a play pattern.</li>`;
  }

  function errors(D) {
    const B = D.errors, M = { vars: B.vars, ...B.modes.all }, f = (a, b) => C.find(M, a, b);
    const displayModel = (name) => name.replace(/\bEL2A\b/g, "weekly refit").replace(/\bEL\b/g, "our model");
    C.matrix($("#err"), M, { kind: "r", focus: ["EL (headline)"], displayName: displayModel });
    $("#err-meta").textContent = `Pearson r · ${B.n} days, May 1 – Jun 30`;
    const fixed = B.vars.filter((x) => x.startsWith("EL") && !x.includes("refit"));
    const fr = []; for (let i = 0; i < fixed.length; i++) for (let j = 0; j < i; j++) fr.push(f(fixed[i], fixed[j]).r);
    const ea = f("EL (headline)", "EL2A, weekly refit"), eb = f("EL (headline)", "B1 weekday mean");
    $("#err-says").innerHTML = `<li><b>The fixed versions of our model make the same mistakes</b>: their errors correlate ${Math.min(...fr).toFixed(2)}–${Math.max(...fr).toFixed(2)}. Averaging two of them is averaging one forecast with itself.</li>
      <li><b>One shared error</b> carries ${C.pct(B.pc1_share, 0)} of the variation across all nine models.</li>
      <li><b>Weekly refits make different mistakes</b>: our model vs the weekly refit only ${r2(ea.r)}. The refit follows June's decline but over-forecasts Locals Week, while our model does the reverse. This is the one pair where averaging could help, but averaging the two lost in Jan–Apr validation, so it wasn't adopted.</li>
      <li>The weekday baseline, which ignores events, shares part of our model's error (${r2(eb.r)}).</li>`;
    $("#err-tab").innerHTML = `<thead><tr><th>Model</th><th class="num">RMSE, May–Jun</th><th class="num">Mean error (bias) / day</th></tr></thead><tbody>
      ${B.vars.map((m) => `<tr class="${m === "EL (headline)" ? "hl" : ""}"><td>${C.esc(displayModel(m))}</td><td class="num">${C.usd(B.rmse[m])}</td><td class="num">${C.usd(B.bias[m], { plus: true })}</td></tr>`).join("")}</tbody>`;
  }
})();
