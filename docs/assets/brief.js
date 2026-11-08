/* Brief page: the six GUIDE questions with a one-line answer each, and the two original findings with the
   code that reproduces them. Numbers come from data/claims.js (scripts/reproduce_claims.py). */
(function () {
  "use strict";
  const C = window.Core, $ = C.$;

  C.registerPage("index.html", async () => {
    let K, B, F, M, Mo;
    try {
      [K, B, F, M, Mo] = await Promise.all([
        C.load("claims"), C.load("benefits"), C.load("floor"), C.load("machines"), C.load("models"),
      ]);
    } catch (e) { return C.fail($("#main"), e); }
    if (!C.pageActive()) return;
    const by = Object.fromEntries(K.claims.map((c) => [c.id, c]));
    const ok = K.claims.filter((c) => c.pass).length;
    const cat = Mo.catalog.filter((a) => a.action_type_id !== "A-HOLD");
    const mm = C.moveModel(F, M, 0, 5);
    const actionModels = C.actionModels({ B, F, M, cat, a: 0, b: 5, asm: C.DEFAULT_ASSUMPTIONS, mm });
    const best = C.bestPlan(actionModels, 1, C.BUDGET);
    const value = C.planValue(actionModels, best.qty);
    const selected = Object.entries(best.qty).filter(([, q]) => q > 0)
      .map(([id, q]) => {
        const model = actionModels.find((m) => m.id === id);
        const target = model.target(q);
        if (id === "A-MOVE-MACHINE" || id === "A-PROMO") return target;
        if (id === "A-WAYFINDING") return `signs for ${target}`;
        return `${model.name}: ${target}`;
      });
    $("#plan-summary").innerHTML = `The evidence-based plan spends <strong>${C.usd(value.cost)}</strong> on ${C.esc(selected.join("; "))}.
      Its estimated net July theo is <strong>${C.usd(value.net[1], { plus: true })}</strong> in the central case
      (${C.usd(value.net[0], { plus: true })} to ${C.usd(value.net[2], { plus: true })} across the four explicit assumptions).
      <a href="actions.html#asm-h">Review the plan and assumptions</a>.`;

    $("#qrows").innerHTML = C.QUESTIONS.map((Q) => `<li class="qrow">
      <div class="num-q" aria-hidden="true">${Q.n}</div>
      <div><h2><span class="sr">Question ${Q.n}: </span>${C.esc(Q.q)}</h2><p>${Q.a}</p></div>
      <a class="go" href="${Q.page}${location.search}">See why ${C.icon("arrow", 14)}</a></li>`).join("");

    $("#f1").textContent = C.pct(by.C3.value / 100, 0);
    $("#f1-code").textContent = `v  = pd.read_parquet("data/1_prepared_views/prepared_daily_view.parquet")
v  = v[v.active & v.location_id.notna()]
z  = v.groupby(["gaming_date", "zone_id"])[["coin_in_usd", "available_hours"]].sum()
lr = np.log(z.coin_in_usd / z.available_hours).unstack()
gap = lr["Z-B40"] - lr.drop(columns=["Z-B40", "Z-HL"]).mean(axis=1)
# regress gap on closed (Mar 3-Apr 6) + reopened + weekday
# -> ${by.C3.shown}; placebo zones at most ±${by.C4.shown}`;
    $("#f2").textContent = by.C7.shown;
    $("#f2-code").textContent = `d  = pd.read_parquet("data/1_prepared_views/property_day.parquet")
b1 = d[d.gaming_date <= "2025-04-30"].groupby(d.gaming_date.dt.dayofweek).theo_usd.mean()
jun = d[(d.gaming_date.dt.month == 6) & ~event_day]
jun.gaming_date.dt.dayofweek.map(b1).sum() / jun.theo_usd.sum() - 1
  # -> ${by.C7.shown}, against a ${by.C22.shown} detectable effect`;
    $("#v-check").innerHTML = `${ok} of ${K.claims.length} claims recompute from the raw data: <code>python scripts/reproduce_claims.py</code> · <a href="evidence.html${location.search}">Evidence</a>`;
  });
})();
