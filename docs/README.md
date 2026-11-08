# Gilded Ace floor review (dashboard site)

A fully static site: HTML, CSS and JavaScript only. Open `index.html` (the Brief) directly in a browser, or publish the folder as is.
No server, build step or Python is needed to view it.

The nav is the GUIDE's six questions, one page each (Machines, Demand, Downtime, Players, Comps, Actions), then a Methods menu
with Evidence and the supporting analysis. The brand links home to the summary page (`index.html`).

| Page | Shows |
| --- | --- |
| `index.html` Summary (home) | The six questions, each with its answer, the decision it leads to and the claims behind it; two original findings with the code that reproduces them |
| `machines.html` Machines | Luck z for every machine with BH correction, payout-rate check, the GM's bottom 10 with verdicts |
| `forecast.html` Demand | Jan–Jun daily theo, frozen May–Jun forecasts with EL's 90% band, the two decisions the forecast changes, the June shortfall, the July no-action yardstick |
| `downtime.html` Downtime | Down hours and theo lost by month, hour, shift, maker and zone; the technician replay and the preventive break-even |
| `players.html` Players | Tracked wagers, payback and net by guest group; loss concentration; each player's expected vs actual payout, payout z against peers, and an exact win-rate test |
| `comps.html` Comps | Comp cost and reinvestment, the May 1 points-price cut by tier, tier growth, unspent points, and the pilot that would test it |
| `actions.html` Actions | The $100,000 builder, starting from the floor optimizer's best moves (`assets/moves.js`), with cost, effect, uncertainty, measurement and evidence per action; assumption sliders and a sensitivity table |
| `evidence.html` Evidence | Every headline claim: table and method, result recomputed from raw data, alternative tested, limitation |
| `floor.html` Floor | Floor plan from `floor_locations` x/y, shaded by play, theo, luck or traffic; drag a machine to project a move |
| `weekly.html` Weekly | The seven-day cycle and the tests behind it |
| `models.html` Models | How B1 was built, every model vs B1 with bootstrap CIs, iterations, machine and impact-model checks |
| `correlations.html` Correlations | Correlation matrices with Benjamini–Hochberg q-values |
| `context.html` Context | Walkway closure, weather and rain, measured events, LVCVA visitation, data left out |
| `streaks.html` Streaks | Whether any player is "due" |

The period selector (From/To) is shared across pages and kept in the URL. Moves placed on the Floor page are saved in the browser and appear on the Actions page.

## Data

`data/*.js` holds the precomputed results. Each file sets `window.__DATA[name]`, which is why the pages work straight from disk.
They are generated from the analysis outputs by `scripts/build_site_data.py` (outside this folder), only when the analysis changes.
`data/weekly.js` and `data/corr.js` come from `scripts/build_site_patterns.py`; `data/downtime.js` from `scripts/build_site_downtime.py`.
`data/claims.js` comes from `scripts/reproduce_claims.py`, which recomputes every claim from `data/` and checks it against the site (`--check` exits 1 on any mismatch).

## Publish

GitHub Pages: Settings → Pages → Deploy from a branch → `main`, folder `/docs`.
