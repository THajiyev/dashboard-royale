/* Brief page: the six GUIDE questions with a one-line answer each, and the two original findings with the
   code that reproduces them. Numbers come from data/claims.js (scripts/reproduce_claims.py). */
(function () {
  "use strict";
  const C = window.Core, $ = C.$;

  C.registerPage("index.html", async () => {
    let K;
    try { K = await C.load("claims"); } catch (e) { return C.fail($("#main"), e); }
    if (!C.pageActive()) return;
    const by = Object.fromEntries(K.claims.map((c) => [c.id, c]));
    const ok = K.claims.filter((c) => c.pass).length;

    $("#qrows").innerHTML = C.QUESTIONS.map((Q) => `<li class="qrow">
      <div class="num-q" aria-hidden="true">${Q.n}</div>
      <div><h2><span class="sr">Question ${Q.n}: </span>${C.esc(Q.q)}</h2><p>${C.esc(Q.a)}</p></div>
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
# -> ${by.C7.shown}, against a 4.7% detectable effect`;
    $("#v-check").innerHTML = `${ok} of ${K.claims.length} claims recompute from the raw data: <code>python scripts/reproduce_claims.py</code> · <a href="evidence.html${location.search}">Evidence</a>`;
  });
})();
