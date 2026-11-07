"""Iteration 2 holdout submissions (agent "iter2", 3 allowed). Chosen by the CV rule in README before any
holdout number was seen: CV-best single model, CV-best combination, CV-best classical TS model."""
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE))
import harness
from models import CANDIDATES

PICKS = {
    "EL + recent-level (28d) + payday": "EL with the non-event weekday profile rescaled to the last 28 non-event days' level, x shrunk day-of-month bucket factors (1-3, 4-14, 15-17, 18-end; k=10). CV-best single model.",
    "Combo: EL-level28 + AutoTheta-adj + Prophet-lin-adj": "Equal-weight geometric mean of EL-level28, AutoTheta and linear Prophet, both fitted on the EL event-adjusted series with the lift re-applied. CV-best combination.",
    "AutoTheta on event-adjusted": "statsforecast AutoTheta (season 7) on actual / EL in-sample event lift; future EL lift re-applied. CV-best classical TS model.",
}
for name, desc in PICKS.items():
    harness.submit("iter2", name, CANDIDATES[name], desc)
