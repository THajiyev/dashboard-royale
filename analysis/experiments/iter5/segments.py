"""Iteration 5 data: daily floor theo split into locals (carded, home_region == Local) and non-locals (the rest,
including uncarded play), so the two add up to property_day.theo_usd exactly. See PREREG.md."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from common import load  # noqa: E402

_SEG = None


def _sessions():
    s = load("3_guests/sessions.parquet")[["gaming_date", "machine_id", "player_id", "theo_cents"]]
    p = load("3_guests/players.parquet")[["player_id", "home_region"]]
    s = s.merge(p, on="player_id", how="left")
    s["gaming_date"] = pd.to_datetime(s.gaming_date)
    s["theo"] = s.theo_cents.astype(float) / 100
    return s


def segment_day() -> pd.DataFrame:
    """gaming_date, total, locals, nonlocals, carded_nonlocals (all theo $/day)."""
    global _SEG
    if _SEG is None:
        s = _sessions()
        c = s.groupby(["gaming_date", "home_region"]).theo.sum().unstack().fillna(0.0)
        pdy = load("1_prepared_views/property_day.parquet")
        pdy["gaming_date"] = pd.to_datetime(pdy.gaming_date)
        tot = pdy.set_index("gaming_date").theo_usd.astype(float)
        loc = c["Local"].reindex(tot.index).fillna(0.0)
        _SEG = pd.DataFrame({"total": tot, "locals": loc, "nonlocals": tot - loc,
                             "carded_nonlocals": c.drop(columns="Local").sum(1).reindex(tot.index)})
    return _SEG


def machine_segment(start, end) -> pd.DataFrame:
    """Per machine, mean theo/day over [start, end]: locals, carded non-locals, uncarded."""
    s = _sessions()
    s = s[(s.gaming_date >= start) & (s.gaming_date <= end)]
    m = load("2_machine_decision/machine_day.parquet")[["machine_id", "gaming_date", "theo_cents", "carded_theo_cents"]]
    m["gaming_date"] = pd.to_datetime(m.gaming_date)
    m = m[(m.gaming_date >= start) & (m.gaming_date <= end)]
    n = (pd.Timestamp(end) - pd.Timestamp(start)).days + 1
    loc = s[s.home_region == "Local"].groupby("machine_id").theo.sum() / n
    cnl = s[s.home_region != "Local"].groupby("machine_id").theo.sum() / n
    tot = m.groupby("machine_id").theo_cents.sum().astype(float) / 100 / n
    card = m.groupby("machine_id").carded_theo_cents.sum().astype(float) / 100 / n
    return pd.DataFrame({"locals": loc, "carded_nonlocals": cnl, "uncarded": tot - card, "total": tot}).fillna(0.0)
