"""CV only (no holdout). python analysis/experiments/ds_alpha/run_cv.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import harness  # noqa: E402
import models as M  # noqa: E402

CANDS = {
    "b2_lab (sanity)": M.m_b2_lab,
    "typed k=3/3": M.make_typed(3, 3),
    "typed k=0/0": M.make_typed(0, 0),
    "typed k=1/1": M.make_typed(1, 1),
    "typed k=6/6": M.make_typed(6, 6),
    "class only (k_type=1e9)": M.make_typed(3, 1e9),
}
if __name__ == "__main__":
    for name, f in CANDS.items():
        for t in ["theo_usd", "coin_in_usd"]:
            r = harness.cv(f, t)
            print(f"{name:28s} {t:12s} cv={r['cv_mae']:>10.0f} b2={r['cv_mae_b2']:>10.0f} "
                  f"skill={r['cv_skill_vs_b2']:+.3f} won={r['folds_won']}/{r['folds']}")
