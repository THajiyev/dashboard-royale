# UPDATE.md: refreshing the website's text after a data update

**Audience:** a Claude Code agent (or a person) asked to update the dashboard after the data in `data/`
or the analysis code has changed. Follow the steps in order and do not skip the checks.

**The short version.** `python scripts/rebuild_dashboard.py` refreshes every chart, table and
generated number on the site. It does **not** refresh the sentences people wrote by hand: headings,
paragraphs, notes and the claim wording. Those still contain figures and conclusions from the old
data. Your job is to find every hand-written statement that the new data changed and correct it,
without changing anything else.

---

## 0. Ground rules

1. **Change words and numbers only.** Do not change layout, CSS, chart code, page structure,
   navigation or styling. If a fix seems to need one of those, list it in your report instead.
2. **Never invent a number.** Every figure you write must come from a generated file (`docs/data/*.js`,
   `outputs/*.csv`), from `scripts/reproduce_claims.py` output, or from a calculation you ran on `data/`.
   If you cannot find where a hand-written number comes from, leave it as it is and flag it (see step 9).
3. **Do not quietly reverse a conclusion.** Some sentences state a decision ("No.", "brought in no extra
   play", "downtime isn't why the bottom 10 are low"). If the new numbers no longer support one, **stop
   and ask the user**. If you cannot ask, leave the sentence unchanged and list it under *Needs a decision*
   in your report. See step 6.
4. **Keep the house style** (section 11): the same rounding, the same words ("about", "a third"), the
   same characters (− minus, – en dash).
5. **Do not commit or push** unless the user asks. Give them the diff summary instead.
6. Put scratch files (claim tables, notes) in your scratchpad directory, not in the repo.

---

## 1. What is already automatic (do not edit by hand)

| What | How it updates | Files |
| --- | --- | --- |
| All chart and table data | `rebuild_dashboard.py` regenerates it | `docs/data/*.js` (generated, never hand-edit) |
| Figures inside `<span data-claim="C#"></span>` | Filled in the browser from `docs/data/claims.js` | `docs/*.html`, the `C.QUESTIONS` answers in `docs/assets/core.js` |
| Values written as `${...}` inside JavaScript template strings, e.g. `` `${C.pct(s.top1, 1)}` `` | Computed from data when the page loads | `docs/assets/*.js` |
| The home-page plan summary and the two "findings you can check" numbers | Computed in `docs/assets/brief.js` | `docs/index.html` (`#plan-summary`, `#f1`, `#f2`) |
| The Evidence page | Rendered from `claims.js` | `docs/evidence.html`, `docs/assets/evidence.js` |

**Watch out:** the claims are only half automatic. In `scripts/reproduce_claims.py` each claim has a
hand-written `text`, `alternative` and `limitation` (which often contain numbers) and a hand-typed
`expected` value. The script recalculates `value`, but you must update the rest yourself (step 4).

## 2. What is hand-written (this is your job)

1. **Claim definitions** in `scripts/reproduce_claims.py`: the `text`, `expected`, `tol` (rarely),
   `alternative` and `limitation` arguments of each `claim(...)` call.
2. **Plain text in the HTML pages** in `docs/*.html`: `<h1>`, `<h2>`, `<h3>`, `<p>`, `<li>`, notes,
   legends, `aria-label`s, and the `<meta name="description">` / `og:description` tags.
3. **Plain text inside JavaScript** in `docs/assets/*.js`: words and numbers typed straight into strings,
   for example `"About $2,900 a month more than Jan–Apr (+9%)."` in `comps.js`. The test: if a number is
   **not** inside `${...}`, it is hard-coded.
4. **Write-ups the site cites as sources**, such as `analysis/models.md` and `analysis/impact.md`
   (the Models page says "Source: analysis/models.md"). Optional; see step 7.

Section 10 lists every place found when this guide was written. Use it as a checklist, but still run
the searches in step 5, because text gets added over time.

---

## 3. Rebuild and record what changed

```bash
# 1. Note the commit you are starting from. Everything is compared against it.
git status                       # should be clean apart from the new data
BASE=$(git rev-parse HEAD)       # write this hash down in your notes

# 2. Rebuild everything (takes several minutes)
python scripts/rebuild_dashboard.py
```

The last step of the rebuild runs `reproduce_claims.py --check`. **After a data change, expect it to fail
with an error at the end.** That is normal: the claims' `expected` values are still the old ones.
`docs/data/claims.js` is written before the check fails, so the new values are already there.
Any **other** error (an analysis script crashes) is a real problem: stop and report it.

Next, build the old-versus-new claim table. Save its output in your scratchpad; you will use it
throughout:

```bash
python - <<'EOF'
import json, subprocess, sys
sys.stdout.reconfigure(encoding="utf-8")
BASE = "HEAD"   # replace with the hash you noted, if you have committed since
def load(s):
    s = s.split('["claims"] = ', 1)[1].strip().rstrip(";")
    return {c["id"]: c for c in json.loads(s)["claims"]}
old = load(subprocess.run(["git", "show", f"{BASE}:docs/data/claims.js"], capture_output=True, check=True).stdout.decode("utf-8"))
new = load(open("docs/data/claims.js", encoding="utf-8").read())
print(f"{'id':<5}{'was shown':>12}{'now':>12}  {'pass':<5} text")
for cid, c in sorted(new.items(), key=lambda kv: int(kv[0][1:])):
    o = old.get(cid, {})
    flag = "" if o.get("shown") == c["shown"] else "  <-- CHANGED"
    print(f"{cid:<5}{o.get('shown','(new)'):>12}{c['shown']:>12}  {str(c['pass']):<5} {c['text'][:70]}{flag}")
for cid in sorted(set(old) - set(new)):
    print(f"{cid:<5} REMOVED: {old[cid]['text'][:70]}")
EOF
```

Then see which analysis outputs changed, because many hand-written figures come from them:

```bash
git diff --stat "$BASE" -- outputs/ docs/data/
git diff "$BASE" -- outputs/*.csv | head -200     # look at the changed rows
```

**If nothing in the claim table changed and `outputs/` has no diff**, the text does not need updating.
Run the checks in step 8, report that, and stop.

---

## 4. Update the claims in `scripts/reproduce_claims.py`

Every claim is one `claim(...)` call. Its arguments are, in order:

```
claim(id, question, text, value, expected, tol, fmt, source, method, alternative, limitation, page, original=False)
```

For **each claim marked FAIL or CHANGED** in your table:

1. **`expected`**: set it to the new value, rounded the way the old one was (e.g. `-30.9`, `4290`, `3.64`).
   Leave `value` alone (it is code that computes the number).
2. **`text`**: rewrite every number in the sentence to match the new value, **including numbers written
   as words or approximations**. Examples from the current claims:
   - C1 "**Nine** of the GM's bottom 10..." is the integer value 9 in words.
   - C12 "about **four times** as often" stands for 3.64×. At 2.4× it becomes "about two and a half times".
   - C13 "**two thirds** of all coin-in" stands for 66%.
   - C14 "about **half** of all losses" stands for 53%.
   - C17 "**9%** more ... about **$2,900** a month": two numbers, possibly from two calculations; check both.
   - C21 has two figures (Locals Week and the tournament); the claim's value is only one of them.
   When a sentence contains a second number that the claim does not compute, find its source in the same
   block of code above the `claim(...)` call (print the variable if needed). Do not guess.
3. **`alternative` and `limitation`**: these often quote numbers from **other** claims or calculations
   (C1's alternative quotes "31%" from C3; C2 quotes "z of +124" and "310 machines"; C20 quotes "3.6%").
   Update each one.
4. **Cross-references between claims**: C8's text repeats C7 (6.5%) and C22 (4.7%). Search the file for
   each old number you change (step 5 shows how) so no copy is missed.
5. **`tol`**: leave it unless the size of the value changed a lot (e.g. a $ value that doubled). Then keep
   `tol` at roughly the same share of the value as before.

Rerun until everything passes:

```bash
python scripts/reproduce_claims.py --check     # every line PASS, exit code 0
```

The script also reports `FAIL site reference C# is missing` if a page uses a claim ID that no longer
exists. Fix the page reference; do not delete a claim to make the check pass.

---

## 5. Sweep the hand-written page text

Work through the pages **one file at a time**, in this order: `index.html`, then the six question pages
(`machines`, `forecast`, `downtime`, `players`, `comps`, `actions`), then `evidence`, `models`, `floor`,
`weekly`, `correlations`, `context`, `streaks`. For each page, check both the `.html` file and its script
in `docs/assets/` (same name; `actions.html` also uses `benefits.js` and `moves.js`, and `index.html`
uses `brief.js`). Also check the `C.QUESTIONS` block in `docs/assets/core.js`, which supplies each
question page's question and the home page's answers.

### 5a. Find candidate text

Visible numbers in an HTML page, with tags removed:

```bash
f=docs/comps.html
sed -e 's/<[^>]*>//g' "$f" | grep -n -E '[0-9]' | grep -v -E 'charset|viewport|wght|#[0-9a-f]{6}'
```

Hard-coded figures in a script (anything matched here that is **not** inside `${...}`):

```bash
grep -n -E '(\$[0-9]|[0-9]+(\.[0-9]+)?(%|K\b|×| days| hours| machines| players))' docs/assets/comps.js
```

Every place an old figure still appears, using numbers from your claim table ("was shown") and from the
changed `outputs/` rows:

```bash
grep -rn --include=*.html --include=*.js --include=*.py -F '6.5%' docs/ scripts/reproduce_claims.py
```

Also search for each old figure **in its other spellings**: `-30.9%`, `−31%`, `31%`, `30.9` are
the same finding. Remember that a number in text may be written as a word ("nine", "a third", "half",
"four times", "two thirds").

### 5b. Decide what each figure is

For each hard-coded number you find, put it in one of these groups:

| Kind | Example | What to do |
| --- | --- | --- |
| **Finding**: a result of the analysis | "Comps cost $191K over six months", "+$342/day", "148 ordinary days" | Find its new value (5c) and update it |
| **Fixed fact about the set-up** that only changes if the data period or design changes | "Jan 1 – Apr 30", "61 days", "Mar 3 – Apr 6", "$100,000", "Up to 3 action types", "at most 24 machine moves" | Leave it, unless the data covers different dates (step 6b) or `data/2_machine_decision/action_catalog` / `cost_rules` changed. Then take it from the data |
| **Statistical convention** | "95%", "±1.96", "90% interval", "5% false discovery rate", "2,000 resamples", "80% power" | Leave it, unless the analysis code changed it |
| **Historical record** of a modelling experiment | Models page iterations ("LightGBM came 7th"), "150 fake changes were planted" | Leave it. `rebuild_dashboard.py` does not rerun `analysis/experiments/`. Only update it if files under `analysis/experiments/` changed in `git diff "$BASE"` |
| **Assumption / default** shown to the user | "move-cost setting (default $1,800 per machine)", "at a 40% fault cut" | Leave it unless the matching default in the JS changed (e.g. `DEFAULTS` in `actions.js`) |

### 5c. Find the new value of a finding

Try these sources in order:

1. **A claim.** If the figure is a claim's value, use the new `shown` value from your table, or better,
   replace the hand-typed number with `<span data-claim="C#"></span>`, **but only if** the claim's format
   matches what the sentence needs (`shown` for C3 is "-30.9%"; a sentence reading "cut play by 31%" does
   not fit, so keep it as text).
2. **A generated site data file.** Search `docs/data/<page>.js` for the old value or a nearby key. The page's
   script shows which key it reads, e.g. `D.costRatio` in `comps.js` comes from `docs/data/comps.js`.
   ```bash
   python -c "import json,sys;s=open('docs/data/comps.js',encoding='utf-8').read();d=json.loads(s.split('] = ',1)[1].rstrip().rstrip(';'));print(json.dumps(d,indent=1)[:3000])"
   ```
3. **An analysis output.** Search `outputs/*.csv` and `outputs/*.json` for the old number, find the column
   that held it, and read the new value from the same row.
4. **The site builder that writes the page's data file**: `scripts/build_site_<page>.py` or
   `scripts/build_site_data.py` (comps and players are built from `build_site_data.py`). Read how the
   nearest related number is computed and compute the missing one the same way on `data/`, using pandas,
   in a scratch script.
5. **Not found.** Leave the text unchanged and record it under *Could not verify* in your report, with the
   file, the sentence and what you searched.

When you change a number, re-read the whole sentence and the sentences around it. Comparisons
("larger than", "more than a 30-day test can detect"), directions ("rose", "fell", "below") and counts
("both rain episodes", "All nine 40°C days") must still be true.

---

## 6. Check that the conclusions still hold

### 6a. Decision sentences

These sentences carry the site's argument. After the numbers are updated, confirm each one is still
supported. If any is no longer true, follow ground rule 3: stop and ask.

| Page | Statement | Supported by |
| --- | --- | --- |
| `index.html` h1 | "Should the GM replace the ten lowest earners? **No.**" | C1, C2, C3; Machines page verdicts |
| `index.html` | "Weekday norms would call a no-action July a failure"; "June ran … below them, more than a 30-day test can detect" | C7 > C22 (C8 positive) |
| `core.js` Q1 answer | "M-1158 … so inspect it before replacing machines" | C2 (still the only flagged machine?) |
| `core.js` Q3 answer, C11 | "repair time, not waiting, is the main staffing constraint" | C11 ratio > 1 |
| `downtime.html` | "Back Forty loses little, so downtime isn't why the bottom 10 are low" | `docs/data/downtime.js` by zone |
| `comps.html` h1 / `comps.js` | "brought in no extra play"; "What it bought. Nothing visible." | C18 ≤ 0 |
| `comps.js` | "Run the $4,000 pilot in August … save about $35K a year" | pilot cost from `action_catalog`; saving ≈ 12 × C17's monthly amount |
| `models.html` | "No machine in the GM's bottom 10 has a credibly negative effect" | `analysis/models.md` Phase 3 / `outputs/` impact files |
| `models.html` | "The 90% band should catch about 55 of 61 days; most catch fewer, so the bands are too narrow" | coverage column on the Models page |
| `machines.html` | "about four drift alarms happen" by chance across 310 machines | machine count in `docs/data/machines.js` |
| `context.html` | "The rain effect passed a placebo test …"; "heat can't be separated from it" | `docs/data/context.js` |
| `actions.html` / C19 | What the plan funds and how much it keeps | C19, and `brief.js`'s live plan summary |

The plan on the Actions page is chosen live by the optimiser, so it can change on its own after a data
update. If C19's text (what the plan funds) no longer matches what `#plan-summary` on the home page shows,
the claim text is the thing to fix.

### 6b. If the date range of the data changed

Many pages are written around fixed periods: Jan–Jun 2025, the Jan 1 – Apr 30 training window,
the May 1 – Jun 30 test (61 days), the July plan, the May 1 comp change, the Mar 3 – Apr 6 closure.
These dates are also built into the analysis code (`CLOSED` in `reproduce_claims.py`, the model
split in `analysis/`). If the new data covers **different dates**, this is not a text update. Stop and
tell the user which pages and scripts assume the old period. Do not rewrite the dates yourself.

---

## 7. Optional: write-ups cited by the site

The Models and Context pages cite `analysis/models.md`, `analysis/impact.md` and
`analysis/FORECAST_SUMMARY.md`. If `git diff "$BASE" -- outputs/` touched the results they describe,
check that the figures **the site quotes** from them still match. Update those figures the same way
(step 5c). Do not rewrite the rest of a write-up; list anything else stale in your report.

`GUIDE.md`, `reference/` and `README.md` describe the challenge, not the results. Leave them alone.

---

## 8. Verify

Run all of these. Each one must pass before you report the work as done.

```bash
# 1. Claims reproduce and every data-claim reference exists
python scripts/reproduce_claims.py --check

# 2. Site data is current (fast; reuses outputs/)
python scripts/rebuild_dashboard.py --site-only

# 3. No old figure survives. Run this for EVERY old value you replaced (claim table + outputs diff)
grep -rn -F 'OLD_VALUE' docs/ scripts/reproduce_claims.py

# 4. Review your own diff: only text should have changed
git diff --stat
git diff -- docs/*.html docs/assets/*.js scripts/reproduce_claims.py
```

In the diff, check that you changed **no** CSS, no markup structure, no logic, and no generated
`docs/data/*.js` by hand.

**Look at the pages in a browser if you have one available:**

```bash
python -m http.server 8000 --directory docs
# open http://localhost:8000/index.html and each page in the nav
```

On every page, check:
- no text reads "Missing claim C#" or "Claim data unavailable";
- the browser console has no errors;
- every sentence you edited reads naturally and agrees with the chart next to it.

If you have no browser, say so in your report. Do not claim you checked the pages.

---

## 9. Report back to the user

End with a short report in this shape:

```
Data update text refresh, compared against <BASE hash>

Claims: N changed, all PASS. (list: C# old → new)
Page text updated: (file, what changed, old → new, source of the new value)
Left unchanged on purpose: (fixed facts / historical records you reviewed, one line each)
Needs a decision: (conclusions the new data may no longer support, with the numbers)
Could not verify: (hard-coded figures whose source you could not find)
Checks: reproduce_claims --check PASS | old-value grep clean | browser check done / not possible
```

Do not commit unless asked. Never push.

---

## 10. Checklist: hand-written figures as of this guide (2026-11-08)

Line numbers drift, so search for the quoted words. **(C#)** marks a figure a claim also computes, so use
that claim's new value. Anything not listed but found by step 5a still counts.

### `scripts/reproduce_claims.py`
- C1–C25: `text`, `expected`, `alternative`, `limitation` (step 4). Known numbers in the side fields:
  C1 "fell 31%" (C3); C2 "z of +124", "310 machines", "10.0%"; C3 "−1.8% per 30 days, p = 0.08";
  C3's alternative "-2% to +3%" (placebo range); C20 "3.6% gap", "$7,500", "20 days".

### `docs/index.html` and `docs/assets/brief.js`
- h1 "… ten lowest earners? No." (decision, 6a).
- "Closing one walkway cut Back Forty's play" (number filled by `#f1`); "June ran … below them" (`#f2`).
- `brief.js` code samples in `#f1-code` / `#f2-code`: check that the dates still match the data.

### `docs/assets/core.js` (`C.QUESTIONS`)
- Q1–Q6 `a:` answers: the words around each `data-claim` ("of the bottom 10", "top 10% of losing players",
  "monthly comp cost was", etc.) must still fit the new values.
- Footer: "Weather, LVCVA and Missouri benchmarks are real public data". Leave it.

### `docs/machines.html` / `machines.js`
- "about one machine in twenty"; "Across 310 fair machines about four drift alarms happen" (machine count).

### `docs/forecast.html` / `forecast.js`
- "compared with the weekday baseline (B1) on the 61 days neither had seen".
- "a floor-wide 30-day test detects changes around" (C22, filled), "Locals dipped a little; visitors fell
  further, in a month when Las Vegas visitation ran below 2024" (direction words).

### `docs/downtime.html` / `downtime.js`
- "Back Forty loses little, so downtime isn't why the bottom 10 are low" (6a).
- `downtime.js`: "Ridgeline maintenance sweep, at a 40% fault cut" (assumption).

### `docs/players.html` / `players.js`
- "about two thirds of all coin-in (66%, Jan–Jun)" (C13).
- "All 96,559 card holders who played. The file is large (7.5 MB)": count from `docs/data/players_all.js`,
  size from `ls -l docs/data/players_all.js`.

### `docs/comps.html` / `comps.js`
- h1 lede: "Comps cost $191K over six months", "halved the points", "raised the bill 9%" (C17),
  "brought in no extra play" (C18).
- "set from 15 to 7" (base rate before / after).
- `comps.js` chart label "May 1: −53%" and "−53% at every tier" (C15).
- "Gold still pays 80% of the Base price and Platinum 60%".
- "About $2,900 a month more than Jan–Apr (+9%). Redemptions rose about 6% …" (C17 + data).
- "Locals who already used comps played 2.5% less … locals overall, 1.2% less" (C18 + data).
- "Run the $4,000 pilot in August … save about $35K a year".
- "A floor-wide rate change ($1,500) can't be combined with the pilot" (`action_catalog`).

### `docs/actions.html` / `actions.js` / `benefits.js`
- Question text and "$100,000", "Up to 3 action types" (fixed by the challenge).
- `benefits.js` notes: "Measured at L-38-5, where M-1120 was replaced like-for-like in May (49 days, 90%
  interval)"; "±20% for how a down hour is valued"; "Two weekends, from Jul 18" / "One weekend, from Jul 18";
  "over the 28 days after the lead" / "25 days after the lead".

### `docs/floor.html` / `floor.js`
- "default $1,800 per machine", "three hours of estimated lost theo per move", "2-day lead time",
  "28 days in July", "at most 24 machine moves", "B-51 … its eight machines went in on Mar 24".
- `floor.js`: "measured +$342/day (90% CI +$188 to +$497)": a finding: the "Move M-1152 … NET (direct + spillover)" row of
  `outputs/model_change_impacts.csv` (estimate, low, high columns).

### `docs/context.html` / `context.js`
- "148 ordinary days"; "4 random days never came close (p < 0.001)"; "both rain episodes, Feb 13 and May 4–6";
  "All nine 40°C days fall in June"; "cut the May–Jun error by about 5%" (also in `context.js`).
- `context.js`: "New Center Pit bank B-51 … since Mar 24".

### `docs/models.html` / `models.js`
- "The 90% band should catch about 55 of 61 days; most catch fewer" (6a).
- "No machine in the GM's bottom 10 has a credibly negative effect" (6a).
- "+10% is caught a third of the time"; "Intervals widened by ×1.25".
- Iteration notes and "LightGBM came 7th … about $500 a day": historical (5b), leave them unless
  `analysis/experiments/` changed.

### `docs/weekly.html` / `weekly.js`, `docs/correlations.html`, `docs/streaks.html`
- Mostly method descriptions and conventions (95%, Tukey's 21 pairs, 7-point profiles). Check the
  direction words in the subtitles ("Visitors lean harder on Saturday and Sunday", "The two halves sit on top
  of each other") against the new charts.

### `<meta name="description">` / `og:description` on every page
- Usually figure-free. If one quotes a finding, update it like any other sentence.

---

## 11. House style

- Minus sign is `−` (U+2212) in text ("−53%"); a plain hyphen-minus only inside code or `C.pct` output.
- Ranges and periods use an en dash `–`: "Jan–Jun", "Mar 3 – Apr 6" (spaced when the ends contain spaces).
- Money: "$33K", "$2,900", "$48,300", "$100,000". Use K for rounded thousands in prose, full figures in
  claim values. Thousands separators always.
- Percentages: whole numbers in prose ("9%") unless the decimal matters; claims keep their `fmt`.
- Approximations stay approximations: if the old text said "about a third", the new text should also use
  a plain fraction or rounded number, not "34.27%".
- Short, plain sentences, in the same voice. Do not add adjectives, hedges or new claims.

---

## 12. Making the next update easier (only with the user's agreement)

If the same hand-typed figure has to change on every update, it is a candidate for automation:
- if a claim already computes it in a fitting format, replace the number with
  `<span data-claim="C#"></span>`;
- if it is a figure already in `docs/data/<page>.js`, have the page script write it with `${...}`.

Propose these to the user as a list at the end of your report; do not make them as part of a text
refresh.
