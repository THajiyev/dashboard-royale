"""Holdout submission 1 (counts against budget). python analysis/experiments/ds_alpha/submit_1.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import harness  # noqa: E402
import models as M  # noqa: E402

harness.submit(
    "ds-alpha", "typed_event_lift_k3", M.make_typed(3, 3),
    "B2 non-event weekday base x hierarchical event lift: pooled -> a-priori class (business=convention; "
    "leisure=sports_viewing/festival/property_promotion) -> event_type, EB pseudo-count 3 days at each level. "
    "Events used only if announced_date <= train origin. Festival (EDC) has no training example, so it gets "
    "the leisure class lift.")
