# Gilded Ace floor review (dashboard site)

A fully static site: HTML, CSS and JavaScript only. Open `index.html` directly in a browser, or publish the folder as is.
No server, build step or Python is needed to view it.

| Page | Shows |
| --- | --- |
| `index.html` Floor | Floor plan from `floor_locations` x/y, shaded by play, theo, luck or traffic; drag a machine to project a move |
| `machines.html` Machines | Luck z for every machine with BH correction, payout-rate check, the GM's bottom 10 with verdicts |
| `players.html` Players | Tracked wagers, payback and net by guest group; loss concentration; each player's expected vs actual payout ($, %), payout z ranked against peers, and an exact win-rate test |
| `comps.html` Comps | Comp cost and reinvestment, the May 1 points-price cut by tier, tier growth, unspent points, and the pilot that would test it |
| `forecast.html` Forecast | Jan–Jun daily theo, frozen May–Jun forecasts with EL's 90% band, the July no-action yardstick |
| `models.html` Models | How B1 was built, every model vs B1 with bootstrap CIs, iterations, machine and impact-model checks |
| `context.html` Context | Walkway closure, weather and rain, measured events, LVCVA visitation, data left out |
| `actions.html` Actions | The $100,000 builder with cost, effect, uncertainty, measurement and evidence per action |

The period selector (From/To) is shared across pages and kept in the URL. Moves placed on the Floor page are saved in the browser and appear on the Actions page.

## Data

`data/*.js` holds the precomputed results. Each file sets `window.__DATA[name]`, which is why the pages work straight from disk.
They are generated from the analysis outputs by `scripts/build_site_data.py` (outside this folder), only when the analysis changes.

## Publish

GitHub Pages: Settings → Pages → Deploy from a branch → `main`, folder `/docs`.
