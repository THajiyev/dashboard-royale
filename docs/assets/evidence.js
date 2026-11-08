/* Evidence page: the Claims & Evidence appendix, grouped by GUIDE question. Rows come from data/claims.js,
   written by scripts/reproduce_claims.py from the raw tables. */
(function () {
  "use strict";
  const C = window.Core, $ = C.$;

  document.addEventListener("DOMContentLoaded", async () => {
    let K;
    try { K = await C.load("claims"); } catch (e) { return C.fail($("#main"), e); }
    const ok = K.claims.filter((c) => c.pass).length;
    $("#rep-note").innerHTML = `Last run ${C.esc(K.generated)}: <strong>${ok} of ${K.claims.length}</strong> claims reproduce. Three read a fitted model's saved output
      (C6, C8, C12's adjusted ratio) and say so under "Table"; the rest use <code>data/</code> only.`;
    const shown = (c) => c.shown.replace(/^-/, "−");
    $("#groups").innerHTML = C.QUESTIONS.map((Q) => {
      const rows = K.claims.filter((c) => c.q === Q.n);
      return `<section class="section" aria-labelledby="q${Q.n}-h">
        <h2 id="q${Q.n}-h">${Q.n}. ${C.esc(Q.q)}</h2>
        <div class="card table-wrap"><table class="claims">
          <thead><tr><th>Claim</th><th class="num">Result</th><th>Table and method</th><th>Alternative tested</th><th>Limitation</th></tr></thead>
          <tbody>${rows.map((c) => `<tr id="${c.id}">
            <td class="claim"><span class="claim-id">${c.id}</span> ${C.esc(c.text)}${c.original ? ' <span class="tag"><span class="dot accent"></span>Original finding</span>' : ""}
              <a class="src" href="${c.page}">Shown here</a></td>
            <td class="num"><span class="mono">${C.esc(shown(c))}</span><span class="src ${c.pass ? "ok" : "bad"}">${c.pass ? "Reproduces" : "Doesn't match the site"}</span></td>
            <td>${C.esc(c.source)}<span class="src">${C.esc(c.method)}</span></td>
            <td>${C.esc(c.alternative)}</td><td>${C.esc(c.limitation)}</td></tr>`).join("")}</tbody></table></div></section>`;
    }).join("");
    C.toc();
    if (location.hash) document.getElementById(location.hash.slice(1))?.scrollIntoView({ block: "center" });
  });
})();
