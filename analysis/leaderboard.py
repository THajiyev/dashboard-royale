"""One leaderboard for every daily property forecast scored on the May-Jun 2025 holdout (61 days).

Collects the stored results of Phase 2 and iterations 1-4 (nothing is refitted), one row per
(protocol, model, target). Writes outputs/model_leaderboard_forecast.csv.

Columns
  protocol   fixed = one forecast made Apr 30 for all of May-Jun; refresh = refit weekly, 7 days ahead
  holdout_mae, holdout_bias      May-Jun, dollars per day (bias > 0 = over-forecast)
  mae_ex_locals                  excluding the Locals Appreciation Week (Jun 9-15), where available
  cv_mae                         Jan-Apr CV MAE (protocol's own CV; Phase 2 used 2 origins, later work 7)
  chosen_by_cv                   True if the model was picked on Jan-Apr before the holdout was seen
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
X = ROOT / "analysis" / "experiments"
rows = []


def add(source, protocol, target, model, mae, bias=None, cv=None, ex_locals=None, chosen=False):
    rows.append(dict(source=source, protocol=protocol, target=target, model=model, holdout_mae=mae,
                     holdout_bias=bias, mae_ex_locals=ex_locals, cv_mae=cv, chosen_by_cv=chosen))


# Phase 2 + iteration 1 (fixed)
p = pd.read_csv(ROOT / "outputs" / "model_comparison.csv")
p = p[p.target.isin(["theo_usd", "coin_in_usd"])]
for r in p.itertuples():
    name = "EL event-type lift (iter 1)" if r.model.startswith("Iteration 1") else r.model
    add("Phase 2" if not r.model.startswith("Iteration 1") else "Iter 1", "fixed", r.target, name, r.MAE, r.bias,
        r.cv7_mae if pd.notna(r.cv7_mae) else r.cv_mae_janapr,
        chosen=bool(r.cv_choice) or r.model.startswith("Iteration 1"))

# iteration 2 (fixed), post-hoc scores of all 30 models; 3 were submitted on CV
SUBMITTED = {"EL + recent-level (28d) + payday", "Combo: EL-level28 + AutoTheta-adj + Prophet-lin-adj",
             "AutoTheta on event-adjusted"}
for r in pd.read_csv(X / "iter2" / "posthoc_holdout.csv").itertuples():
    if r.model.startswith("EL (iteration 1"):
        continue
    add("Iter 2", "fixed", r.target, r.model, r.holdout_mae, r.holdout_bias, r.cv7_mae, chosen=r.model in SUBMITTED)

# iteration 3 (fixed + refresh)
CV3 = {("refresh", "EL2 k_ev=0.5 + anchor 100% (28d)")}
for r in pd.read_csv(X / "iter3" / "final_table.csv").itertuples():
    if r.protocol == "fixed" and r.model in ("B2", "EL (current best)"):
        continue
    add("Iter 3", r.protocol, r.target, r.model, r.holdout_mae, r.holdout_bias,
        r.cv_mae if pd.notna(r.cv_mae) else None, r.mae_ex_locals, chosen=(r.protocol, r.model) in CV3)

# iteration 4 (fixed + refresh), bases already counted above
CV4 = {("fixed", "hist seasonal beta=0.5"), ("refresh", "hol longwknd+day lam=2")}
cv4 = pd.read_csv(X / "iter4" / "cv_results.csv").set_index(["protocol", "target", "model"]).mae
BASE = {"fixed": "EL", "refresh": "EL2 + anchor"}
for r in pd.read_csv(X / "iter4" / "holdout_results.csv").itertuples():
    if r.model == "base":
        continue
    add("Iter 4", r.protocol, r.target, f"{BASE[r.protocol]} + {r.model}", r.mae, r.bias,
        cv4.get((r.protocol, r.target, r.model)), r.mae_ex_locals, chosen=(r.protocol, r.model) in CV4)

df = pd.DataFrame(rows)
ref = df[(df.model == "B1 weekday mean") & (df.protocol == "fixed")].set_index("target").holdout_mae  # official baseline
df["skill_vs_B1"] = 1 - df.holdout_mae / df.target.map(ref)
df["rank"] = df.groupby("target").holdout_mae.rank(method="min").astype(int)
df = df.sort_values(["target", "holdout_mae"], ascending=[False, True])
df.to_csv(ROOT / "outputs" / "model_leaderboard_forecast.csv", index=False)

if __name__ == "__main__":
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300); pd.set_option("display.max_colwidth", 60)
    for t in ["theo_usd", "coin_in_usd"]:
        d = df[df.target == t]
        print(f"\n=== {t}: {len(d)} models ===")
        print(d[["rank", "source", "protocol", "model", "holdout_mae", "skill_vs_B1", "holdout_bias", "mae_ex_locals",
                 "cv_mae", "chosen_by_cv"]].to_string(index=False, float_format=lambda x: f"{x:+.1%}" if abs(x) < 1 else f"{x:,.0f}"))
