/* Shared chart helpers for the Weekly and Correlations pages: colour ramps read from the CSS tokens,
   p-value formatting, and a lower-triangle matrix (correlations or pairwise p-values) with hover. */
(function () {
  "use strict";
  const C = window.Core;

  const hex = (h) => { h = h.replace("#", ""); return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)); };
  const mix = (a, b, t) => a.map((v, i) => Math.round(v + (b[i] - v) * t));
  const rgb = (c) => `rgb(${c[0]},${c[1]},${c[2]})`;
  /** Piecewise-linear interpolation through CSS colour tokens; t in [0, 1]. Returns [r,g,b]. */
  C.rampAt = (tokens, t) => {
    const stops = tokens.map((n) => hex(C.css(n)));
    t = Math.max(0, Math.min(1, t));
    const k = Math.min(stops.length - 2, Math.floor(t * (stops.length - 1)));
    return mix(stops[k], stops[k + 1], t * (stops.length - 1) - k);
  };
  C.SEQ = ["--seq-0", "--seq-1", "--seq-2", "--seq-3", "--seq-4", "--seq-5"];
  C.DIV = ["--div-neg", "--div-neg-2", "--div-mid", "--div-pos-2", "--div-pos"];
  C.rgb = rgb;
  /** Text colour that stays readable on a fill (relative luminance). */
  C.onFill = (c) => {
    const L = c.map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
    const Y = 0.2126 * L[0] + 0.7152 * L[1] + 0.0722 * L[2];
    // whichever of near-black / white has the higher WCAG contrast on this fill
    return (Y + 0.05) / (0.0075 + 0.05) >= 1.05 / (Y + 0.05) ? "#0f1512" : "#ffffff";
  };
  C.gradient = (tokens) => `linear-gradient(90deg, ${tokens.map((n) => C.css(n)).join(", ")})`;

  /** p-value as text/HTML: 0.042, < 0.001 stays readable, tiny values in powers of ten. */
  C.pfmt = (p, html = true) => {
    if (p == null || !isFinite(p)) return "–";
    if (p >= 0.001) return p >= 0.995 ? "1.00" : p.toFixed(p >= 0.1 ? 2 : 3);
    if (p < 1e-16) return html ? "< 10<sup>−16</sup>" : "< 1e-16";  // below double precision; daily data are autocorrelated anyway
    const e = Math.floor(Math.log10(p)), m = p / Math.pow(10, e);
    return html ? `${m.toFixed(1)} × 10<sup>−${-e}</sup>` : `${m.toFixed(1)}e${e}`;
  };
  C.sig = (q) => q != null && q < 0.05;
  /** "= 0.042" or "< 10^-16", to follow "p " in running text. */
  C.peq = (p, html = true) => { const t = C.pfmt(p, html); return t.startsWith("<") || t.startsWith("&lt;") ? t : "= " + t; };

  /**
   * Lower-triangle matrix.
   *   M = { vars, r?, p?, q?, n?, diff? }
   *   opt.kind = "r" (correlations; colour by r, grey when q >= .05) or "p" (pairwise test; colour by -log10 p,
   *   label = diff). opt.sym = "r" | "ρ". opt.focus = [names] drawn in bold.
   */
  C.matrix = (svg, M, opt = {}) => {
    const v = M.vars, k = v.length, kind = opt.kind || "r", sym = opt.sym || "r";
    const W = svg.clientWidth || 800, narrow = W < 560;
    const labW = Math.min(narrow ? 112 : 190, Math.max(...v.map((s) => s.length)) * (narrow ? 5.8 : 6.6) + 12);
    const cell = Math.max(14, Math.min(58, Math.floor((W - labW - 8) / (k - 1))));
    const botH = Math.min(narrow ? 92 : 150, labW * 0.72 + 8);
    const H = (k - 1) * cell + botH + 8, showTxt = cell >= 30;
    const x0 = labW, y0 = 4;
    const mid = hex(C.css("--div-mid"));
    let g = "";
    for (let i = 1; i < k; i++) {
      const y = y0 + (i - 1) * cell;
      const bold = opt.focus && opt.focus.includes(v[i]);
      g += `<text x="${x0 - 8}" y="${y + cell / 2 + 4}" text-anchor="end" style="font-family:var(--sans);font-size:${narrow ? 11 : 12}px;fill:${bold ? "var(--ink)" : "var(--ink-2)"};font-weight:${bold ? 500 : 400}">${C.esc(v[i])}</text>`;
      for (let j = 0; j < i; j++) {
        const x = x0 + j * cell;
        let fill, txt = "", strong = false;
        if (kind === "r") {
          const rv = M.r[i][j], q = M.q ? M.q[i][j] : M.p[i][j];
          if (rv == null) { fill = mid; } else if (!C.sig(q)) { fill = mid; txt = rv.toFixed(opt.digits || 2); }
          else { fill = C.rampAt(C.DIV, (rv + 1) / 2); txt = rv.toFixed(opt.digits || 2); strong = true; }
        } else {
          const p = M.p[i][j];
          if (p == null || p >= 0.05) fill = mid;
          else { fill = C.rampAt(C.SEQ, 0.2 + 0.8 * Math.min(1, -Math.log10(Math.max(p, 1e-16)) / 12)); strong = true; }
          const d = M.diff[i][j]; txt = d == null ? "" : C.pct(d, 0, true);
        }
        const tc = strong ? C.onFill(fill) : "var(--ink-3)";
        g += `<rect class="cell" x="${x + 1}" y="${y + 1}" width="${cell - 2}" height="${cell - 2}" rx="3" fill="${rgb(fill)}" data-i="${i}" data-j="${j}"/>`;
        if (showTxt && txt) g += `<text x="${x + cell / 2}" y="${y + cell / 2 + 4}" text-anchor="middle" style="fill:${tc};font-size:${cell >= 44 ? 11 : 10}px;pointer-events:none">${txt.replace("-", "−")}</text>`;
      }
    }
    const yb = y0 + (k - 1) * cell + 8;
    for (let j = 0; j < k - 1; j++) {
      const x = x0 + j * cell + cell / 2;
      const bold = opt.focus && opt.focus.includes(v[j]);
      g += `<text transform="translate(${x + 4},${yb}) rotate(-40)" text-anchor="end" style="font-family:var(--sans);font-size:${narrow ? 11 : 12}px;fill:${bold ? "var(--ink)" : "var(--ink-2)"};font-weight:${bold ? 500 : 400}">${C.esc(v[j])}</text>`;
    }
    // the rotated labels hang below-left, so the box grows downward
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("height", H); svg.innerHTML = g;
    svg.onmousemove = (e) => {
      const t = e.target.closest("[data-i]"); if (!t) return C.tip(null);
      const i = +t.dataset.i, j = +t.dataset.j;
      const rows = kind === "r"
        ? [[sym, M.r[i][j] == null ? "–" : M.r[i][j].toFixed(3)], ["p", C.pfmt(M.p[i][j])],
           ...(M.q ? [["q (Benjamini–Hochberg)", C.pfmt(M.q[i][j])]] : []), ...(M.n ? [["n", C.int(M.n[i][j])]] : [])]
        : [[`${v[i]} vs ${v[j]}`, C.pct(M.diff[i][j], 1, true)], ["p (Tukey-adjusted)", C.pfmt(M.p[i][j])]];
      C.tip(C.tipRows(`${C.esc(v[i])} × ${C.esc(v[j])}`, rows), e);
    };
    svg.onmouseleave = () => C.tip(null);
  };

  /** Strongest significant pairs, for the table view under a matrix. */
  C.topPairs = (M, n = 8) => {
    const out = [];
    for (let i = 0; i < M.vars.length; i++) for (let j = 0; j < i; j++) {
      const rv = M.r[i][j], q = M.q[i][j];
      if (rv != null) out.push({ a: M.vars[j], b: M.vars[i], r: rv, p: M.p[i][j], q, n: M.n ? M.n[i][j] : null });
    }
    return out.filter((x) => C.sig(x.q)).sort((a, b) => Math.abs(b.r) - Math.abs(a.r)).slice(0, n);
  };
  C.find = (M, a, b) => { const i = M.vars.indexOf(a), j = M.vars.indexOf(b); return { r: M.r[i][j], p: M.p[i][j], q: M.q ? M.q[i][j] : null, n: M.n ? M.n[i][j] : null }; };

  /** Linear axis ticks. */
  C.ticks = (lo, hi, n = 5) => {
    const step0 = (hi - lo) / n, p = Math.pow(10, Math.floor(Math.log10(step0)));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * p).find((s) => s >= step0);
    const out = []; for (let t = Math.ceil(lo / step) * step; t <= hi + 1e-9; t += step) out.push(+t.toFixed(10));
    return out;
  };
})();
