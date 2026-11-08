"""Rebuild analysis outputs and the static dashboard from the source data.

Run `python scripts/rebuild_dashboard.py` after changing source data or analysis code.
Use `--site-only` when the analysis outputs are already current.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> None:
    command = [sys.executable, *args]
    print(f"\n> {' '.join(args)}", flush=True)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    subprocess.run(command, cwd=ROOT, check=True, env=env)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-only", action="store_true", help="reuse existing outputs/ analysis results")
    args = parser.parse_args()

    if not args.site_only:
        run("analysis/run_phase0.py")
        run("analysis/run_models.py")
        run("analysis/run_impact.py")

    run("scripts/build_site_data.py")
    run("scripts/build_site_benefits.py")
    run("scripts/build_site_downtime.py")
    run("scripts/build_site_patterns.py")
    run("scripts/build_site_streaks.py")
    run("scripts/reproduce_claims.py", "--check")


if __name__ == "__main__":
    main()
