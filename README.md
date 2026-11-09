# Casino Manager

**1st place, TAMU Datathon 2026 (Casino Royale).** [Live dashboard](https://thajiyev.github.io/dashboard-royale/) · [Write-up](WRITEUP.md) · [Devpost](https://devpost.com/software/casino-manager)

A fictional 300-machine casino's general manager wanted to replace the 10 machines that earned the least over six months. Casino Manager is an interactive dashboard that tests whether those machines were unlucky, badly placed or actually broken, and then plans how to spend a $100,000 budget for July.

## What we found

- **The bottom 10 shouldn't be replaced.** 9 of them are in Back Forty, a zone whose play fell 31% when its walkway closed and recovered when it reopened. The problem is the location, not the machines.
- **One machine is worth inspecting.** M-1158 held 3.0% against its configured 10%, and it was the only machine whose win rate stood out after correcting for 310 tests (Benjamini–Hochberg). It's a lead to check, not proof of a fault.
- **Demand** follows the day of the week and events, with a visitor-driven slowdown in June. **Downtime** cost 5,021 hours and about $102K in theo. Tracked players lost a net $15.6M, and the May 1 comp price cut raised comp cost 9% without bringing in more play.
- **July plan:** two promotion weekends, 6 machine moves and new signs for Back Forty, for $48.3K. The remaining $51.7K is kept.

Every headline number is recomputed from the raw data by `scripts/reproduce_claims.py` and listed on the dashboard's [Evidence page](https://thajiyev.github.io/dashboard-royale/evidence.html), along with the alternative explanation tested and the limitation for each claim. The full submission, including the July plan, the AI statement and the Claims & Evidence table, is in [WRITEUP.md](WRITEUP.md).

## ML and statistics

- **Machine play model:** a Poisson GLM predicting each machine's coin-in per available hour from bank, theme, weekday, events and the walkway closure. It was trained on Jan–Apr and tested on May–Jun, where it beat zone averages by 28% (MAE $38.2 vs $53.1). Its bank effects decide which machine moves pay off.
- **Daily demand forecast:** a weekday baseline plus lifts by event type, frozen before the test period. It cut daily error by 36% on May–Jun (MAE $6,699 → $4,290) and gives the July forecast the plan is measured against.
- **Luck test:** a z-score per machine comparing actual to expected house win and payout frequency, with Benjamini–Hochberg correction.
- **Causal checks:** difference-in-differences with placebo zones for the walkway closure, and impact estimates with 90% intervals for past promotions, moves and new banks.

## Tech stack

- **Analysis:** Python with pandas, NumPy, SciPy, statsmodels, scikit-learn and LightGBM (`analysis/`, `requirements-analysis.txt`).
- **Dashboard:** a static site of plain HTML, CSS and JavaScript with hand-built SVG charts, no framework or build step (`docs/`). It's hosted on GitHub Pages and also opens straight from disk.
- **Pipeline:** `python scripts/rebuild_dashboard.py` reruns the analyses, exports the site data to `docs/data/` and checks every claim against its published value.

## Credits

Built for TAMU Datathon 2026. The challenge, the synthetic casino dataset (`data/`, `reference/`) and [GUIDE.md](GUIDE.md) come from the TAMU Datathon organizers and are under the [MIT license](LICENSE). The casino and its people are fictional.
