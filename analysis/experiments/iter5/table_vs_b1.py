"""Every model vs the simple baseline B1 (weekday mean of Jan-Apr; no events, holidays or outside data).

Reads the May-Jun predictions saved by evaluate.py (holdout_daily.csv, final_table.csv); adds B0 and B1.
No model is refitted or re-selected. Writes table_vs_b1.csv and table_vs_b1.md.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parent.parent), str(HERE)]
import forecast  # noqa: E402
import harness  # noqa: E402
from common import TRAIN_END  # noqa: E402
from evaluate import ALPHA, _EV, boot_idx, cv_residuals, fixed_run  # noqa: E402

END = pd.Timestamp("2025-06-30")
d = pd.read_csv(HERE / "holdout_daily.csv", parse_dates=["gaming_date"])
ft = pd.read_csv(HERE / "final_table.csv").set_index("model")
y = d.actual.to_numpy()
df = harness.frame(); df_cv = df[df.gaming_date <= TRAIN_END]

const = lambda tr, te, t: np.full(len(te), tr[t].mean())
meta = {k: (r.iteration, r.protocol, bool(r.picked_in_advance)) for k, r in ft.iterrows()}
meta["B2 event-aware weekday"] = ("Phase 0", "fixed", True)  # final_table.csv mislabels it "Phase 2"
bands = {}
for name, f in [("B0 constant mean", const), ("B1 weekday mean", forecast.m_b1)]:
    p, yy, _ = fixed_run(f, df, TRAIN_END, END); assert np.allclose(yy, y)
    d[name] = p
    lr, _, _ = cv_residuals(f, "fixed", df_cv)
    bands[name] = np.quantile(lr, [ALPHA / 2, 1 - ALPHA / 2])
    meta[name] = ("Phase 0", "fixed", True)

ev_days = set()
for r in _EV.itertuples():
    ev_days |= set(pd.date_range(r.start_date, r.end_date))
ev = d.gaming_date.isin(ev_days).to_numpy()

rmse = lambda e: float(np.sqrt(np.mean(e ** 2)))
mae = lambda e: float(np.mean(np.abs(e)))
rng = np.random.default_rng(0)
I = [boot_idx(len(y), rng) for _ in range(2000)]
eB1 = d["B1 weekday mean"].to_numpy() - y


def ci(e, f):
    v = [f(e[i]) / f(eB1[i]) - 1 for i in I]
    return np.quantile(v, [0.025, 0.975])


MAIN = "EL2 + 28d anchor"
rows = []
for m in meta:
    p = d[m].to_numpy(); e = p - y
    if m in bands:
        lo, hi = p * np.exp(bands[m][0]), p * np.exp(bands[m][1])
        cover = float(np.mean((y >= lo) & (y <= hi)))
        iscore = float(np.mean((hi - lo) + (2 / ALPHA) * ((lo - y) * (y < lo) + (y - hi) * (y > hi))))
    else:
        cover, iscore = ft.loc[m, "cover90"], ft.loc[m, "interval_score"]
    it, proto, adv = meta[m]
    r = {"model": m, "iteration": it, "protocol": proto, "picked_in_advance": adv,
         "MAE": mae(e), "RMSE": rmse(e), "WAPE": float(np.abs(e).sum() / y.sum()), "bias": float(e.mean()),
         "ordinary_RMSE": rmse(e[~ev]), "event_RMSE": rmse(e[ev]), "cover90": cover, "interval_score": iscore,
         "dMAE_vs_B1": mae(e) / mae(eB1) - 1, "dRMSE_vs_B1": rmse(e) / rmse(eB1) - 1}
    if m != "B1 weekday mean":
        (r["dMAE_lo"], r["dMAE_hi"]), (r["dRMSE_lo"], r["dRMSE_hi"]) = ci(e, mae), ci(e, rmse)
    rows.append(r)

t = pd.DataFrame(rows)
t["rank_RMSE"] = t.RMSE.rank(method="min").astype(int)
t["rank_MAE"] = t.MAE.rank(method="min").astype(int)
t["beats_B1_RMSE_sig"] = t.dRMSE_hi < 0
t["beats_B1_MAE_sig"] = t.dMAE_hi < 0
t = t.sort_values("RMSE").reset_index(drop=True)
t.to_csv(HERE / "table_vs_b1.csv", index=False)

pct = lambda x: f"{x:+.1%}".replace("-", "−")
usd = lambda x: f"{x:,.0f}"
L = ["| Rank (RMSE) | Rank (MAE) | Model | Iter | Protocol | Picked in advance? | RMSE | Δ RMSE vs B1 (95% CI) | MAE | Δ MAE vs B1 (95% CI) | WAPE | Bias | Ordinary RMSE | Event RMSE | 90% cover | Interval score |",
     "|---:|---:|---|---|---|---|---:|---|---:|---|---:|---:|---:|---:|---:|---:|"]
for r in t.itertuples():
    name = r.model + (" **(baseline)**" if r.model == "B1 weekday mean" else " (main)" if r.model == MAIN else "")
    def cell(delta, lo, hi, sig):
        if r.model == "B1 weekday mean":
            return "—"
        s = f"{pct(delta)} ({pct(lo)} to {pct(hi)})"
        return f"**{s}**" if sig else s
    L.append(f"| {r.rank_RMSE} | {r.rank_MAE} | {name} | {r.iteration} | {r.protocol} | {'yes' if r.picked_in_advance else 'no'} | "
             f"{usd(r.RMSE)} | {cell(r.dRMSE_vs_B1, r.dRMSE_lo, r.dRMSE_hi, r.beats_B1_RMSE_sig)} | {usd(r.MAE)} | "
             f"{cell(r.dMAE_vs_B1, r.dMAE_lo, r.dMAE_hi, r.beats_B1_MAE_sig)} | {r.WAPE:.2%} | {pct(r.bias / 1e9)[:0]}{r.bias:+,.0f} | "
             f"{usd(r.ordinary_RMSE)} | {usd(r.event_RMSE)} | {r.cover90:.0%} | {usd(r.interval_score)} |")
(HERE / "table_vs_b1.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L))
