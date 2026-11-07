"""Build one HTML data report per table in data/ (parquet; the csv.gz twin holds the same rows).

Usage:  python scripts/build_reports.py        -> writes reports/*.html and reports/index.html
"""
from __future__ import annotations

import html
import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "reports"
WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# ----------------------------------------------------------------------------- loading


def load(rel: str) -> pd.DataFrame:
    df = pd.read_parquet(DATA / rel)
    for c in df.columns:
        if df[c].dtype == object:
            v = df[c].dropna()
            tn = type(v.iloc[0]).__name__ if len(v) else ""
            if tn == "Decimal":
                df[c] = pd.to_numeric(df[c].astype(float))
            elif tn == "date":
                df[c] = pd.to_datetime(df[c])
    return df


_CACHE: dict[str, pd.DataFrame] = {}


def cached(rel: str) -> pd.DataFrame:
    if rel not in _CACHE:
        _CACHE[rel] = load(rel)
    return _CACHE[rel]


def parse_dictionary() -> dict:
    """table -> {desc, rows_key, cols:{col:(type, meaning)}}"""
    text = (ROOT / "reference" / "DATA_DICTIONARY.md").read_text(encoding="utf-8")
    out, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^### (\w+)", line)
        if m:
            cur = out.setdefault(m.group(1), {"desc": "", "rows_key": "", "cols": {}})
            continue
        if cur is None:
            continue
        m = re.match(r"^\| `(\w+)` \| ([^|]+) \| (.*) \|\s*$", line)
        if m:
            cur["cols"][m.group(1)] = (m.group(2).strip(), m.group(3).strip())
        elif line.startswith("Rows:"):
            cur["rows_key"] = line.strip()
        elif line.strip() and not line.startswith("|") and not line.startswith("#") and not cur["desc"]:
            cur["desc"] = line.strip().replace("**", "")
    return out


DICT = parse_dictionary()

# ----------------------------------------------------------------------------- formatting


def usd(v, d=1):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "–"
    a, s = abs(v), "-" if v < 0 else ""
    for lim, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= lim:
            return f"{s}${a / lim:.{d}f}{suf}"
    return f"{s}${a:,.0f}" if a >= 100 else f"{s}${a:,.2f}"


def pct(v, d=1):
    return "–" if v is None or pd.isna(v) else f"{v * 100:.{d}f}%"


def n(v, d=1):
    if v is None or pd.isna(v):
        return "–"
    a = abs(v)
    for lim, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= lim * 10 or (lim < 1e6 and a >= 1e4) or a >= 1e6 and lim == 1e6:
            if a >= lim:
                return f"{v / lim:.{d}f}{suf}"
    return f"{v:,.0f}" if a >= 100 or float(v).is_integer() else f"{v:,.2f}"


def signed_pct(v, d=0):
    return f"{'+' if v >= 0 else ''}{v * 100:.{d}f}%"


def ds(s: pd.Series) -> list:
    return [x.strftime("%Y-%m-%d") if pd.notna(x) else None for x in pd.to_datetime(s)]


def clean(o):
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return None if math.isnan(f) or math.isinf(f) else round(f, 6)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp,)):
        return o.strftime("%Y-%m-%d %H:%M")
    return o


def L(s) -> list:
    return list(s.tolist()) if hasattr(s, "tolist") else list(s)


# ----------------------------------------------------------------------------- chart specs


def line(title, x, series: dict, fmt="num", sub="", mode="lines", xfmt=None, err=None, ytitle=""):
    return dict(kind="line", title=title, sub=sub, x=L(x), fmt=fmt, mode=mode, xfmt=xfmt, ytitle=ytitle,
                series=[dict(name=k, y=L(v), err=(L(err[k]) if err and k in err else None)) for k, v in series.items()])


def bar(title, x, series: dict, fmt="num", sub="", stacked=False, horizontal=False, ytitle="", wide=False):
    return dict(kind="bar", title=title, sub=sub, x=L(x), fmt=fmt, stacked=stacked, horizontal=horizontal,
                ytitle=ytitle, wide=wide, series=[dict(name=k, y=L(v)) for k, v in series.items()])


def hbar(title, labels, values, fmt="num", sub="", name="value"):
    return bar(title, labels, {name: values}, fmt=fmt, sub=sub, horizontal=True)


def hist(title, values, fmt="num", sub="", bins=40, clip=(0.005, 0.995), log=False):
    v = pd.to_numeric(pd.Series(values), errors="coerce").dropna()
    note = ""
    if len(v) == 0:
        return None
    if log:
        v = v[v > 0]
        edges = np.logspace(np.log10(v.min()), np.log10(v.max()), bins + 1)
    else:
        lo, hi = v.quantile(clip[0]), v.quantile(clip[1])
        if lo == hi:
            lo, hi = v.min(), v.max()
        out = ((v < lo) | (v > hi)).sum()
        if out:
            note = f"{out:,} outliers beyond the {clip[0] * 100:g}th–{clip[1] * 100:g}th percentile not shown."
        v2 = v[(v >= lo) & (v <= hi)]
        if v2.nunique() <= bins and v2.nunique() > 0 and np.allclose(v2.unique(), v2.unique().round()):
            vc = v2.value_counts().sort_index()
            return dict(kind="bar", title=title, sub=(sub + " " + note).strip(), x=L(vc.index), fmt="int",
                        xfmt=fmt, series=[dict(name="rows", y=L(vc.values))], hist=True)
        edges = np.linspace(lo, hi, bins + 1)
        v = v2
    cnt, e = np.histogram(v, bins=edges)
    centers = (e[:-1] + e[1:]) / 2
    return dict(kind="bar", title=title, sub=(sub + " " + note).strip(), x=L(centers), fmt="int", xfmt=fmt,
                series=[dict(name="rows", y=L(cnt))], hist=True, logx=log,
                width=L(np.diff(e) * 0.92))


def heat(title, x, y, z, fmt="num", sub="", diverging=False, xfmt=None):
    return dict(kind="heat", title=title, sub=sub, x=L(x), y=L(y), z=[L(r) for r in np.asarray(z, dtype=float)],
                fmt=fmt, diverging=diverging, xfmt=xfmt)


def scatter(title, series: list, fx="num", fy="num", sub="", xtitle="", ytitle="", logx=False, logy=False,
            equal=False, wide=False):
    return dict(kind="scatter", title=title, sub=sub, series=series, fx=fx, fy=fy, xtitle=xtitle, ytitle=ytitle,
                logx=logx, logy=logy, equal=equal, wide=wide)


def pts(name, x, y, text=None, mode="markers", slot=None, size=8):
    return dict(name=name, x=L(x), y=L(y), text=L(text) if text is not None else None, mode=mode, slot=slot,
                size=size)


def gantt(title, labels, starts, ends, sub=""):
    return dict(kind="gantt", title=title, sub=sub, y=L(labels), start=L(starts), end=L(ends))


def table_block(title, df: pd.DataFrame, sub="", fmts: dict | None = None, maxrows=60):
    return dict(kind="table", title=title, sub=sub, html=df_html(df.head(maxrows), fmts or {}))


# ----------------------------------------------------------------------------- report object


class Report:
    def __init__(self, key, folder, df, real=False):
        self.key, self.folder, self.df, self.real = key, folder, df, real
        self.kpis, self.findings, self.sections, self.notes = [], [], [], []
        self.headline = ""

    def kpi(self, label, value, sub=""):
        self.kpis.append((label, value, sub))

    def find(self, text):
        self.findings.append(text)

    def section(self, title, intro, charts):
        self.sections.append((title, intro, [c for c in charts if c]))


# ----------------------------------------------------------------------------- html helpers


def esc(s):
    return html.escape(str(s))


def fmt_cell(v, f=None):
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return '<span class="null">null</span>'
    if f == "usd":
        return usd(v)
    if f == "pct":
        return pct(v)
    if isinstance(v, (float, np.floating)):
        return f"{v:,.4g}" if abs(v) < 1e6 else f"{v:,.0f}"
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d %H:%M") if (v.hour or v.minute) else v.strftime("%Y-%m-%d")
    s = str(v)
    return esc(s if len(s) <= 80 else s[:77] + "…")


def df_html(df, fmts):
    head = "".join(f"<th>{esc(c)}</th>" for c in df.columns)
    body = "".join("<tr>" + "".join(
        f"<td class=\"{'num' if isinstance(v, (int, float, np.number)) and not isinstance(v, bool) else ''}\">{fmt_cell(v, fmts.get(c))}</td>"
        for c, v in zip(df.columns, row)) + "</tr>" for row in df.itertuples(index=False))
    return f'<div class="tbl-wrap"><table class="data"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def column_profile(key, df):
    info = DICT.get(key, {}).get("cols", {})
    rows, charts = [], []
    nrow = len(df)
    for c in df.columns:
        s = df[c]
        nnull = s.isna().mean()
        try:
            nun = s.nunique()
        except TypeError:
            nun = s.astype(str).nunique()
        typ, meaning = info.get(c, (str(s.dtype), ""))
        summary, chart = "", None
        is_num = pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s)
        if nnull == 1:
            summary = "all null"
        elif is_num:
            v = s.dropna()
            summary = f"min {v.min():,.4g} · median {v.median():,.4g} · mean {v.mean():,.4g} · max {v.max():,.4g}"
            if nun > 1:
                chart = hist(c, v, fmt="num", bins=30)
        elif pd.api.types.is_datetime64_any_dtype(s):
            v = s.dropna()
            summary = f"{v.min():%Y-%m-%d %H:%M} → {v.max():%Y-%m-%d %H:%M}"
            if 1 < nun < len(v):
                span = (v.max() - v.min()).days
                freq = "D" if span <= 400 else "MS"
                vc = v.dt.to_period("D" if freq == "D" else "M").value_counts().sort_index()
                xs = [p.start_time.strftime("%Y-%m-%d") for p in vc.index]
                chart = bar(c, xs, {"rows": vc.values}, fmt="int", sub=f"rows per {'day' if freq == 'D' else 'month'}")
        else:
            v = s.dropna().astype(str)
            vc = v.value_counts()
            top = "; ".join(f"{esc(k[:28])} ({cnt:,})" for k, cnt in vc.head(3).items())
            summary = top
            if 1 < nun <= 40 and vc.iloc[0] > 1:
                vc2 = vc.head(12)
                chart = hbar(c, [k[:34] for k in vc2.index], vc2.values, fmt="int", name="rows",
                             sub="" if nun <= 12 else f"top 12 of {nun}")
            elif nun > 40 and nun >= 0.5 * len(v):
                summary = f"identifier-like · {nun:,} distinct · e.g. {esc(v.iloc[0][:30])}"
        if nun == 1 and nnull < 1:
            summary = f"constant: {esc(str(s.dropna().iloc[0])[:60])}"
            chart = None
        rows.append(f"<tr><td><code>{esc(c)}</code></td><td>{esc(typ)}</td><td>{esc(meaning)}</td>"
                    f"<td class='num'>{nnull * 100:.1f}%</td><td class='num'>{nun:,}</td><td class='sum'>{summary}</td></tr>")
        if chart:
            chart["small"] = True
            charts.append(chart)
    tbl = ("<div class='tbl-wrap'><table class='data profile'><thead><tr><th>Column</th><th>Type</th><th>Meaning</th>"
           "<th>Null</th><th>Distinct</th><th>Summary</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>")
    return tbl, charts


# ============================================================================= table builders


def full_weeks(x):
    return x[(x.index >= pd.Timestamp('2025-01-06')) & (x.index <= pd.Timestamp('2025-06-23'))]


def zone_names():
    v = cached("1_prepared_views/prepared_daily_view.parquet")
    m = v.dropna(subset=["zone_id"]).drop_duplicates("zone_id").set_index("zone_id")["zone_name"].to_dict()
    m.setdefault("Z-HL", "High-Limit Room")
    return m


def b_property_day(r: Report):
    d = r.df.sort_values("gaming_date").copy()
    x = ds(d.gaming_date)
    ci, hw, th = d.coin_in_usd.sum(), d.house_win_usd.sum(), d.theo_usd.sum()
    con = d.contribution_after_supplied_costs_usd.sum()
    d["month"] = d.gaming_date.dt.strftime("%Y-%m")
    mo = d.groupby("month").agg(ci=("coin_in_usd", "sum"), hw=("house_win_usd", "sum"), th=("theo_usd", "sum"),
                                pos=("pos_cash_usd", "sum"), con=("contribution_after_supplied_costs_usd", "sum"),
                                days=("gaming_date", "count"))
    mo["ci_day"] = mo.ci / mo.days
    wk = d.groupby("local_weekday").coin_in_usd.mean().reindex(WEEK)
    ev = d.assign(e=d.events_active.fillna("No event")).groupby("e").coin_in_usd.mean()
    base = ev.get("No event")
    lift = (ev.drop("No event") / base - 1).sort_values(ascending=False)
    occ = d.occupied_machine_hours / d.available_machine_hours
    r.headline = f"{usd(ci)} coin-in over 181 days at {pct(hw / ci, 2)} hold; Saturdays run {signed_pct(wk['Sat'] / wk['Tue'] - 1)} vs Tuesdays."
    r.kpi("Coin-in", usd(ci), f"{usd(ci / len(d))} per day")
    r.kpi("House win", usd(hw), f"observed hold {pct(hw / ci, 2)}")
    r.kpi("Theo win", usd(th), f"theo hold {pct(th / ci, 2)}")
    r.kpi("Contribution after supplied costs", usd(con), f"{pct(con / hw)} of house win")
    r.kpi("Seat occupancy", pct(occ.mean()), "occupied / available machine-hours")
    r.kpi("POS cash", usd(d.pos_cash_usd.sum()), f"comp cost {usd(d.comp_cost_usd.sum())}")
    best_m, worst_m = mo.ci_day.idxmax(), mo.ci_day.idxmin()
    r.find(f"Observed hold ({pct(hw / ci, 2)}) tracks theoretical hold ({pct(th / ci, 2)}) closely over the half-year; luck "
           f"nets to {usd(hw - th)}. Daily hold swings between {pct(d.observed_hold.min())} and {pct(d.observed_hold.max())}, so single days say little.")
    r.find(f"Demand is strongly weekly: average Saturday coin-in is {usd(wk['Sat'])} vs {usd(wk['Tue'])} on Tuesday "
           f"({signed_pct(wk['Sat'] / wk['Tue'] - 1)}). Friday–Sunday carry {pct(d[d.local_weekday.isin(['Fri','Sat','Sun'])].coin_in_usd.sum() / ci)} of coin-in on 43% of days.")
    r.find(f"Month-to-month the property is flat: coin-in per day ranges from {usd(mo.ci_day.min())} ({worst_m}) to {usd(mo.ci_day.max())} ({best_m}).")
    top = lift.head(3)
    r.find("Event days lift coin-in vs the no-event daily average (" + usd(base) + "): " +
           ", ".join(f"{k} {signed_pct(v)}" for k, v in top.items()) + ". "
           f"Weakest: {lift.index[-1]} ({signed_pct(lift.iloc[-1])}) — mid-week conventions bring city crowds, not necessarily players.")
    corr = np.corrcoef(d.total_zone_entries_observed, d.coin_in_usd)[0, 1]
    r.find(f"Floor traffic and play move together (correlation {corr:.2f} between daily zone entries and coin-in); "
           f"F&B cash adds {usd(d.pos_cash_usd.sum())}, small next to gaming.")
    roll = d.coin_in_usd.rolling(7, min_periods=1).mean()
    r.section("Daily trend", "Every gaming day, January 1 – June 30, 2025.", [
        line("Coin-in per day", x, {"Daily": d.coin_in_usd, "7-day average": roll}, fmt="usd",
             sub="Weekly rhythm with event spikes; 7-day average is flat."),
        line("House win vs theoretical win", x, {"House win": d.house_win_usd, "Theo win": d.theo_usd}, fmt="usd",
             sub="Gap between the lines is luck."),
        line("Observed hold per day", x, {"Observed hold": d.observed_hold, "Theo hold": d.theo_usd / d.coin_in_usd},
             fmt="pct", sub="Hold = house win / coin-in."),
        line("Seat occupancy per day", x, {"Occupied / available": occ}, fmt="pct"),
    ])
    r.section("Seasonality & drivers", "", [
        bar("Coin-in per day by month", mo.index, {"Coin-in per day": mo.ci_day}, fmt="usd"),
        bar("Average coin-in by weekday", WEEK, {"Average coin-in": wk.values}, fmt="usd"),
        hbar("Event-day lift vs no-event average", list(lift.index), lift.values, fmt="pct",
             sub=f"Baseline: {usd(base)} coin-in on days without an event."),
        scatter("Zone entries vs coin-in", [pts("Gaming day", d.total_zone_entries_observed, d.coin_in_usd, x)],
                fx="int", fy="usd", xtitle="Zone counter entries", ytitle="Coin-in",
                sub=f"Correlation {corr:.2f}."),
    ])
    r.section("Non-gaming & operations", "", [
        line("F&B cash vs comp cost per day", x, {"POS cash": d.pos_cash_usd, "Comp cost": d.comp_cost_usd},
             fmt="usd"),
        bar("Contribution after supplied costs by month", mo.index, {"Contribution": mo.con}, fmt="usd"),
        line("Machine faults opened per day", x, {"Faults": d.faults_opened,
                                                  "7-day average": d.faults_opened.rolling(7, min_periods=1).mean()},
             fmt="int"),
        line("Security incidents reported per day", x, {"Incidents": d.incidents_reported,
                                                        "7-day average": d.incidents_reported.rolling(7, min_periods=1).mean()},
             fmt="int"),
    ])


def b_prepared_daily_view(r: Report):
    v = r.df[r.df.active].copy()
    off = (~r.df.active).sum()
    zone = v.groupby("zone_name").agg(md=("machine_id", "size"), ci=("coin_in_usd", "sum"), hw=("house_win_usd", "sum"),
                                      con=("contribution_after_supplied_costs_usd", "sum"),
                                      occ=("occupancy_ratio", "mean"), card=("carded_coin_in_usd", "sum"),
                                      f=("faults_opened", "sum"))
    zone["ci_md"] = zone.ci / zone.md
    zone["con_md"] = zone.con / zone.md
    zone = zone.sort_values("ci_md", ascending=False)
    theme = v.groupby("theme").agg(ci=("coin_in_usd", "sum"), hw=("house_win_usd", "sum"), th=("theo_usd", "sum"),
                                   md=("machine_id", "size"), occ=("occupancy_ratio", "mean"),
                                   con=("contribution_after_supplied_costs_usd", "sum"))
    theme["hold"], theme["thold"] = theme.hw / theme.ci, theme.th / theme.ci
    theme["con_md"] = theme.con / theme.md
    theme = theme.sort_values("con_md", ascending=False)
    lease = v.groupby("lease_class").contribution_after_supplied_costs_usd.mean().sort_values(ascending=False)
    mfr = v.groupby("manufacturer").agg(f=("faults_opened", "sum"), md=("machine_id", "size"),
                                        av=("availability_ratio", "mean"))
    mfr["f100"] = mfr.f / mfr.md * 100
    mfr = mfr.sort_values("f100", ascending=False)
    v["week"] = v.gaming_date.dt.to_period("W-SUN").dt.start_time
    full = v.groupby("week").gaming_date.nunique()
    wz = v[v.week.isin(full[full == 7].index)].groupby(["week", "zone_name"]).coin_in_usd.mean().unstack()
    wz = wz[zone.index]
    # Back Forty closure effect
    clo = (v.gaming_date >= "2025-03-03") & (v.gaming_date < "2025-04-07")
    b40 = v[v.zone_name == "Back Forty"]
    b_in = b40[clo.loc[b40.index]].coin_in_usd.mean()
    b_out = b40[~clo.loc[b40.index]].coin_in_usd.mean()
    rest = v[v.zone_name != "Back Forty"]
    r_in, r_out = rest[clo.loc[rest.index]].coin_in_usd.mean(), rest[~clo.loc[rest.index]].coin_in_usd.mean()
    mach = v.groupby(["machine_id", "zone_name", "theme"]).agg(ci=("coin_in_usd", "mean"), occ=("occupancy_ratio", "mean"),
                                                                con=("contribution_after_supplied_costs_usd", "sum"),
                                                                days=("gaming_date", "count")).reset_index()
    mach["con_day"] = mach.con / mach.days
    hm = v.groupby(["zone_name", "local_weekday"]).occupancy_ratio.mean().unstack()[WEEK].reindex(zone.index)
    r.headline = (f"{v.machine_id.nunique()} machines × 181 days; Main Entrance and Center Pit earn the most per machine-day, "
                  f"Back Forty the least — and it lost {pct(1 - b_in / b_out, 0)} of play during the March walkway closure.")
    r.kpi("Active machine-days", f"{len(v):,}", f"{off:,} off-floor rows excluded")
    r.kpi("Coin-in per machine-day", usd(v.coin_in_usd.mean()), f"median {usd(v.coin_in_usd.median())}")
    r.kpi("House win per machine-day", usd(v.house_win_usd.mean()))
    r.kpi("Contribution per machine-day", usd(v.contribution_after_supplied_costs_usd.mean()), "after supplied costs")
    r.kpi("Seat occupancy", pct(v.occupancy_ratio.mean()), f"availability {pct(v.availability_ratio.mean(), 2)}")
    r.kpi("Carded share of coin-in", pct(v.carded_coin_in_usd.sum() / v.coin_in_usd.sum()))
    r.find(f"Location matters most. Coin-in per machine-day: {zone.index[0]} {usd(zone.ci_md.iloc[0])} vs "
           f"{zone.index[-1]} {usd(zone.ci_md.iloc[-1])} ({signed_pct(zone.ci_md.iloc[0] / zone.ci_md.iloc[-1] - 1)}).")
    r.find(f"Back Forty coin-in per machine-day fell from {usd(b_out)} to {usd(b_in)} ({signed_pct(b_in / b_out - 1)}) "
           f"while the Back Forty walkway was closed for renovation (Mar 3 – Apr 7); other zones moved "
           f"{signed_pct(r_in / r_out - 1)} over the same weeks. Access paths drive traffic.")
    r.find(f"Observed hold matches configured hold theme by theme (e.g. {theme.hold.idxmax()} {pct(theme.hold.max())} observed vs "
           f"{pct(theme.thold[theme.hold.idxmax()])} theo); low-RTP games are not losing players at the meter level. "
           f"Best contribution per machine-day: {theme.index[0]} ({usd(theme.con_md.iloc[0])}); worst: {theme.index[-1]} ({usd(theme.con_md.iloc[-1])}).")
    r.find(f"Owned machines contribute {usd(lease.get('owned'))} per day vs {usd(lease.get('leased_fixed'))} (fixed lease) and "
           f"{usd(lease.get('leased_revenue_share'))} (revenue share) once lease costs are subtracted.")
    r.find(f"{mfr.index[0]} machines open {mfr.f100.iloc[0]:.1f} faults per 100 machine-days vs {mfr.f100.iloc[-1]:.1f} for "
           f"{mfr.index[-1]} ({mfr.f100.iloc[0] / mfr.f100.iloc[-1]:.1f}×), with lower availability ({pct(mfr.av.iloc[0], 2)}).")
    r.section("Where the money is", "Per machine-day figures normalise for zone size.", [
        hbar("Coin-in per machine-day by zone", list(zone.index), zone.ci_md.values, fmt="usd"),
        hbar("Contribution per machine-day by zone", list(zone.sort_values('con_md', ascending=False).index),
             zone.sort_values('con_md', ascending=False).con_md.values, fmt="usd", sub="After lease, service, power and repair."),
        line("Weekly coin-in per machine-day by zone", ds(wz.index), {k: wz[k] for k in wz.columns}, fmt="usd",
             sub="Full Mon–Sun weeks only. Back Forty dips during the Mar 3 – Apr 7 walkway closure.", mode="lines+markers"),
        heat("Seat occupancy by zone and weekday", WEEK, list(hm.index), hm.values, fmt="pct"),
    ])
    r.section("Games, leases and manufacturers", "", [
        bar("Observed vs theoretical hold by theme", list(theme.sort_values('thold').index),
            {"Observed hold": theme.sort_values('thold').hold, "Theo hold": theme.sort_values('thold').thold}, fmt="pct"),
        hbar("Contribution per machine-day by theme", list(theme.index), theme.con_md.values, fmt="usd"),
        bar("Contribution per machine-day by lease class", list(lease.index), {"Contribution": lease.values}, fmt="usd"),
        bar("Faults per 100 machine-days by manufacturer", list(mfr.index), {"Faults / 100 machine-days": mfr.f100},
            fmt="num"),
    ])
    top = mach.sort_values("con_day", ascending=False)
    r.section("Machine-level spread", "", [
        scatter("Machines: occupancy vs coin-in per day",
                [pts("Machine", mach.occ, mach.ci, mach.machine_id + " · " + mach.zone_name + " · " + mach.theme)],
                fx="pct", fy="usd", xtitle="Mean occupancy", ytitle="Mean coin-in per day",
                sub="Each dot is one machine. Within a theme, busier seats mean more coin-in; separate bands are themes with different bet sizes."),
        hist("Daily luck residual (house win − theo)", v.luck_residual_usd, fmt="usd",
             sub="Centred near zero; the long left tail is jackpot days when the house paid far more than theo."),
        table_block("Top 10 machines by contribution per day",
                    top.head(10)[["machine_id", "zone_name", "theme", "ci", "occ", "con_day"]].rename(
                        columns={"ci": "coin_in_per_day", "occ": "occupancy", "con_day": "contribution_per_day"}),
                    fmts={"coin_in_per_day": "usd", "occupancy": "pct", "contribution_per_day": "usd"}),
        table_block("Bottom 10 machines by contribution per day",
                    top.tail(10)[["machine_id", "zone_name", "theme", "ci", "occ", "con_day"]].rename(
                        columns={"ci": "coin_in_per_day", "occ": "occupancy", "con_day": "contribution_per_day"}),
                    fmts={"coin_in_per_day": "usd", "occupancy": "pct", "contribution_per_day": "usd"}),
    ])


def b_player_period(r: Report):
    p = r.df
    t = p.groupby("player_id").theo_usd.sum().sort_values(ascending=False)
    cum = t.cumsum() / t.sum()
    share = np.arange(1, len(t) + 1) / len(t)
    idx = np.unique(np.linspace(0, len(t) - 1, 200).astype(int))
    mo = p.groupby("period_month").agg(players=("player_id", "nunique"), ci=("tracked_coin_in_usd", "sum"),
                                       th=("theo_usd", "sum"), net=("tracked_net_usd", "sum"),
                                       comp=("comp_cost_usd", "sum"), visits=("observed_visits", "sum"))
    reg = p.groupby("home_region").agg(players=("player_id", "nunique"), th=("theo_usd", "sum"),
                                       ci=("tracked_coin_in_usd", "sum"))
    reg["th_pp"] = reg.th / reg.players
    reg = reg.sort_values("th", ascending=False)
    age = p.assign(a=p.age_band.fillna("unknown")).groupby("a").agg(players=("player_id", "nunique"), th=("theo_usd", "sum"))
    age["th_pp"] = age.th / age.players
    age = age.reindex([a for a in ["21-34", "35-49", "50-64", "65+", "unknown"] if a in age.index])
    tiers = ["Base", "Gold", "Platinum"]
    last = p.sort_values("period_month").groupby("player_id").tail(1)
    tm = pd.crosstab(last.opening_tier, last.tier_end).reindex(index=tiers, columns=tiers, fill_value=0)
    tierc = p.groupby("tier_end").agg(comp=("comp_cost_usd", "sum"), th=("theo_usd", "sum")).reindex(tiers)
    tierc["reinv"] = tierc.comp / tierc.th
    ahead = (p.groupby("player_id").tracked_net_usd.sum() > 0).mean()
    played = p[p.tracked_coin_in_usd > 0]
    r.headline = (f"{p.player_id.nunique():,} tracked players; the top 10% generate {pct(cum.iloc[len(t) // 10 - 1], 0)} "
                  f"of theo and Locals produce {pct(reg.th.get('Local', 0) / reg.th.sum(), 0)}.")
    r.kpi("Tracked players", f"{p.player_id.nunique():,}", f"{len(p):,} player-months")
    r.kpi("Tracked coin-in", usd(p.tracked_coin_in_usd.sum()))
    r.kpi("Theo", usd(p.theo_usd.sum()), f"{usd(p.theo_usd.sum() / p.player_id.nunique())} per player")
    r.kpi("Players' net result", usd(p.tracked_net_usd.sum()), f"{pct(ahead)} of players ended ahead")
    r.kpi("Comp cost", usd(p.comp_cost_usd.sum()), f"reinvestment {pct(p.comp_cost_usd.sum() / p.theo_usd.sum())} of theo")
    r.kpi("Linked F&B cash", usd(p.linked_pos_cash_usd.sum()))
    r.find(f"Value is concentrated: the top 1% of players produce {pct(cum.iloc[max(len(t) // 100 - 1, 0)], 0)} of theo, "
           f"the top 10% {pct(cum.iloc[len(t) // 10 - 1], 0)}, and the bottom half just {pct(1 - cum.iloc[len(t) // 2 - 1], 1)}.")
    r.find(f"Locals are {pct(reg.players.get('Local', 0) / reg.players.sum(), 0)} of players but {pct(reg.th.get('Local', 0) / reg.th.sum(), 0)} "
           f"of theo — {usd(reg.th_pp.get('Local', 0))} per local player vs {usd(reg.th_pp.drop('Local').mean())} for the other regions on average.")
    r.find(f"{(p.tracked_coin_in_usd == 0).mean():.0%} of player-months have no carded play at all (F&B or loyalty activity only).")
    r.find(f"Tier movement: {tm.loc['Base', 'Gold'] + tm.loc['Base', 'Platinum']:,} Base players climbed a tier during the window; "
           f"comp reinvestment is {pct(tierc.reinv.get('Base'))} of theo for Base vs {pct(tierc.reinv.get('Platinum'))} for Platinum.")
    r.find(f"Monthly active players range {mo.players.min():,}–{mo.players.max():,}; March is the busiest month.")
    r.section("Monthly trend", "", [
        bar("Active tracked players per month", mo.index, {"Players": mo.players}, fmt="int"),
        bar("Tracked coin-in and theo per month", mo.index, {"Coin-in": mo.ci, "Theo": mo.th}, fmt="usd",
            sub="Same dollar scale; theo ≈ 9.5% of coin-in."),
    ])
    r.section("Concentration and segments", "", [
        line("Cumulative share of theo by player rank", list(share[idx]), {"Share of theo": cum.values[idx]},
             fmt="pct", xfmt="pct", sub="Read across: x% of players (highest first) produce y% of theo."),
        hbar("Theo by home region", list(reg.index), reg.th.values, fmt="usd"),
        bar("Theo per player by age band", list(age.index), {"Theo per player": age.th_pp}, fmt="usd"),
        heat("Tier migration: opening tier → tier at end", tiers, tiers, tm.values, fmt="int",
             sub="Rows: opening tier. Columns: tier after the last ledger event."),
        bar("Comp reinvestment by tier", tiers, {"Comp cost / theo": tierc.reinv}, fmt="pct"),
    ])
    r.section("Distributions (player-months with carded play)", "", [
        hist("Tracked net per player-month", played.tracked_net_usd, fmt="usd", sub="Player view: payout − coin-in."),
        hist("Luck residual per player-month", played.luck_residual_usd, fmt="usd", sub="Net + theo; zero = played exactly to expectation."),
        hist("Sessions per player-month", played.sessions, fmt="int"),
        hist("Carded play hours per player-month", played.carded_play_hours, fmt="num"),
    ])


def b_action_catalog(r: Report):
    a = r.df.copy()
    a["unit_cost_usd"] = a.unit_cost_cents / 100
    a["recurring_usd_30d"] = a.recurring_cost_cents_per_day * 30 / 100
    a["max_spend_usd"] = (a.unit_cost_usd + a.recurring_usd_30d) * a.quantity_limit
    s = a.sort_values("unit_cost_usd", ascending=False)
    r.headline = f"{len(a)} purchasable actions for a $100K / 30-day budget; single-unit costs range {usd(a.unit_cost_usd.min())}–{usd(a.unit_cost_usd.max())}."
    r.kpi("Actions", len(a))
    r.kpi("Cheapest unit", usd(a.unit_cost_usd.min()), a.loc[a.unit_cost_usd.idxmin(), "action_type_id"])
    r.kpi("Most expensive unit", usd(a.unit_cost_usd.max()), a.loc[a.unit_cost_usd.idxmax(), "action_type_id"])
    r.kpi("Longest lead time", f"{a.lead_days.max()} days", a.loc[a.lead_days.idxmax(), "action_type_id"])
    over = a[a.unit_cost_usd > 100000]
    r.find(f"{(a.unit_cost_usd + a.recurring_usd_30d <= 100000).sum()} of {len(a)} actions fit the $100K budget as a single unit; "
           + (f"{', '.join(over.action_type_id)} cannot be bought at all." if len(over) else "every action is affordable once."))
    r.find(f"Lead times eat into the 30-day window: {', '.join(a[a.lead_days >= 14].action_type_id)} take 14+ days before any effect.")
    r.find(f"{(a.downtime_minutes > 0).sum()} actions take machines offline (up to {a.downtime_minutes.max()} min per unit), a hidden cost in lost play.")
    r.find("Incompatibility groups (same_machine, comp_policy) mean some actions cannot be stacked on the same target.")
    r.section("Costs and constraints", "", [
        hbar("One-time cost per unit", list(s.action_type_id), s.unit_cost_usd.values, fmt="usd"),
        hbar("Lead days before effect", list(a.sort_values('lead_days', ascending=False).action_type_id),
             a.sort_values('lead_days', ascending=False).lead_days.values, fmt="int"),
        hbar("Spend if bought at the quantity limit (30 days)", list(a.sort_values('max_spend_usd', ascending=False).action_type_id),
             a.sort_values('max_spend_usd', ascending=False).max_spend_usd.values, fmt="usd",
             sub="(unit cost + 30 days recurring) × quantity limit. Budget is $100K."),
        table_block("Full catalog", a.drop(columns=["unit_cost_cents", "recurring_cost_cents_per_day"]),
                    fmts={"unit_cost_usd": "usd", "recurring_usd_30d": "usd", "max_spend_usd": "usd"}),
    ])


def b_calendar_day(r: Report):
    c = r.df.copy()
    c["hours"] = c.scheduled_seconds / 3600
    hol = c.dropna(subset=["federal_holiday"])
    dst = c[c.scheduled_seconds != 86400]
    mo = c.groupby(["month", "is_weekend"]).size().unstack(fill_value=0)
    r.headline = f"181 gaming days, {c.is_weekend.sum()} weekend days, {len(hol)} federal holidays, one 23-hour DST day."
    r.kpi("Gaming days", len(c))
    r.kpi("Weekend days", int(c.is_weekend.sum()))
    r.kpi("Federal holidays", len(hol))
    r.kpi("23-hour day", dst.gaming_date.dt.strftime("%Y-%m-%d").iloc[0] if len(dst) else "none", "spring DST")
    r.find("A gaming day runs 06:00 → 06:00 local. Its UTC start shifts from 14:00 to 13:00 once daylight saving starts — always join on gaming_date or the UTC bounds, never on calendar date.")
    r.find(f"Gaming date {dst.gaming_date.dt.strftime('%Y-%m-%d').iloc[0]} has {dst.hours.iloc[0]:.0f} scheduled hours; per-hour metrics must divide by scheduled_seconds.")
    r.find("Holidays: " + ", ".join(f"{h} ({d:%b %d})" for h, d in zip(hol.federal_holiday, hol.gaming_date)) + ".")
    r.find("Each weekday appears 25–26 times, so weekday averages are directly comparable.")
    r.section("Calendar structure", "", [
        line("Scheduled hours per gaming day", ds(c.gaming_date), {"Hours": c.hours}, fmt="num", mode="lines+markers"),
        bar("Days per month", list(mo.index), {"Weekday": mo.get(False, 0), "Weekend": mo.get(True, 0)}, fmt="int", stacked=True),
        table_block("Holidays and DST", c[c.federal_holiday.notna() | (c.scheduled_seconds != 86400)]),
    ])


def b_cost_rules(r: Report):
    c = r.df.copy()
    r.headline = f"{len(c)} supplied cost rules covering lease, service, utilities, labour, repair and cost of goods."
    r.kpi("Rules", len(c))
    r.kpi("Categories", c.cost_category.nunique())
    r.kpi("Effective", "2025-01-01 → open")
    per = c[c.calculation_basis == "per_active_machine_day"].copy()
    per["usd_per_day"] = pd.to_numeric(per.rate) / 100
    per["label"] = per.cost_category + " · " + per.entity_id.fillna("all")
    r.find("Per-machine-day costs are small next to house win (≈$420 per machine-day): " +
           ", ".join(f"{l} ${u:.0f}" for l, u in zip(per.label, per.usd_per_day)) + ".")
    share = c[c.calculation_basis.str.startswith("share_of_positive")]
    if len(share):
        r.find(f"Revenue-share leases take {float(share.rate.iloc[0]) * 100:.0f}% of positive daily house win — the costliest lease type on strong machines.")
    r.find("Repair and cost-of-goods rules point at other tables (operations.direct_cost_cents, fnb_transactions.cogs_cents) — subtract each cost exactly once.")
    r.section("Rules", "", [
        hbar("Fixed per-machine-day costs", list(per.label), per.usd_per_day.values, fmt="usd"),
        table_block("All cost rules", c),
    ])


def b_floor_locations(r: Report):
    f = r.df.copy()
    zn = zone_names()
    f["zone_name"] = f.zone_id.map(zn)
    slots = f[f.node_type == "slot"]
    zc = slots.groupby("zone_name").size().sort_values(ascending=False)
    banks = f[f.node_type == "bank"].groupby("zone_name").size().reindex(zc.index)
    others = f[f.node_type.isin(["zone", "entrance", "outlet"])]
    cent = slots.groupby("zone_name")[["x_m", "y_m"]].mean()
    r.headline = f"{len(slots)} slot positions in {len(banks)} zones / {int(banks.sum())} banks on a {f.x_m.max():.0f} × {f.y_m.max():.0f} m floor."
    r.kpi("Slot positions", len(slots))
    r.kpi("Banks", int((f.node_type == 'bank').sum()))
    r.kpi("Zones", int((f.node_type == 'zone').sum()))
    r.kpi("Entrances / outlets", f"{(f.node_type == 'entrance').sum()} / {(f.node_type == 'outlet').sum()}")
    r.find(f"{zc.index[0]} is the largest zone with {zc.iloc[0]} positions ({pct(zc.iloc[0] / zc.sum(), 0)}); {zc.index[-1]} the smallest with {zc.iloc[-1]}.")
    r.find("Three entrances (main doors, garage doors, hotel lobby) sit at the edges; zones named after them get first contact with arriving guests.")
    r.find("Coordinates are metres on a flat plan, so walking distance between zones can be estimated — see floor_walkways for the actual paths.")
    series = []
    for i, (z, g) in enumerate(slots.groupby("zone_name")):
        series.append(pts(z, g.x_m, g.y_m, g.location_id, size=7))
    series.append(pts("Entrance / outlet", others[others.node_type != 'zone'].x_m, others[others.node_type != 'zone'].y_m,
                      others[others.node_type != 'zone'].name, mode="markers+text", slot=0, size=12))
    r.section("Floor plan", "Every slot position, coloured by zone. Hover for location IDs.", [
        scatter("Floor map", series, fx="num", fy="num", xtitle="x (m)", ytitle="y (m)", equal=True, wide=True,
                sub="Zone colours repeat categorical slots; zones are also labelled on hover."),
        hbar("Slot positions by zone", list(zc.index), zc.values, fmt="int"),
        hbar("Banks by zone", list(banks.index), banks.values, fmt="int"),
        table_block("Zones, entrances and outlets", others.drop(columns=["zone_name"])),
    ])


def b_floor_walkways(r: Report):
    w = r.df.copy()
    zn = zone_names()
    f = cached("2_machine_decision/floor_locations.parquet")
    hubs = f[f.node_type == "zone"].set_index("zone_id")[["x_m", "y_m"]]
    closed = w[w.closed_from_utc.notna()]
    r.headline = f"{len(w)} walkways link the zone hubs; {', '.join(closed.walkway_id)} was closed {closed.closed_from_utc.iloc[0]:%b %d} – {closed.closed_to_utc.iloc[0]:%b %d} for renovation."
    r.kpi("Walkways", len(w))
    r.kpi("Total length", f"{w.length_m.sum():.0f} m")
    r.kpi("Closed for renovation", ", ".join(closed.walkway_id))
    v = cached("1_prepared_views/prepared_daily_view.parquet")
    b40 = v[v.active & (v.zone_id == "Z-B40")]
    clo = (b40.gaming_date >= closed.closed_from_utc.iloc[0].normalize()) & (b40.gaming_date < closed.closed_to_utc.iloc[0].normalize())
    drop = b40[clo].coin_in_usd.mean() / b40[~clo].coin_in_usd.mean() - 1
    r.find(f"The closed walkway ({closed.zone_a.map(zn).iloc[0]} ↔ {closed.zone_b.map(zn).iloc[0]}) coincides with a {signed_pct(drop)} change in Back Forty coin-in per machine-day — see prepared_daily_view.")
    deg = pd.concat([w.zone_a, w.zone_b]).map(zn).value_counts()
    r.find(f"{deg.index[0]} is the best-connected hub ({deg.iloc[0]} walkways); {', '.join(deg[deg == deg.min()].index)} have only {deg.min()}.")
    r.find(f"Walkways range {w.length_m.min():.0f}–{w.length_m.max():.0f} m; the longest is {w.loc[w.length_m.idxmax(), 'walkway_id']}.")
    ex, ey, cx, cy = [], [], [], []
    for _, row in w.iterrows():
        a, b = hubs.loc[row.zone_a], hubs.loc[row.zone_b]
        tx, ty = (cx, cy) if pd.notna(row.closed_from_utc) else (ex, ey)
        tx += [a.x_m, b.x_m, None]
        ty += [a.y_m, b.y_m, None]
    hubs2 = hubs.reset_index()
    r.section("Network", "", [
        scatter("Walkway network between zone hubs", [
            pts("Open walkway", ex, ey, mode="lines", slot=0),
            pts("Closed Mar 3 – Apr 7", cx, cy, mode="lines", slot=1),
            pts("Zone hub", hubs2.x_m, hubs2.y_m, hubs2.zone_id.map(zn), mode="markers+text", slot=2, size=12)],
            fx="num", fy="num", xtitle="x (m)", ytitle="y (m)", equal=True, wide=True),
        hbar("Walkway length", list(w.sort_values('length_m', ascending=False).walkway_id),
             w.sort_values('length_m', ascending=False).length_m.values, fmt="num", sub="metres"),
        table_block("All walkways", w),
    ])


def b_game_math(r: Report):
    g = r.df.copy().sort_values("configured_rtp")
    g["label"] = g.theme + " (" + g.config_id + ")"
    g["hold"] = 1 - g.configured_rtp
    r.headline = f"{len(g)} game configurations; RTP {pct(g.configured_rtp.min(), 0)}–{pct(g.configured_rtp.max(), 0)}, hit rates {pct(g.hit_probability.min(), 0)}–{pct(g.hit_probability.max(), 0)}."
    r.kpi("Configurations", len(g))
    r.kpi("RTP range", f"{pct(g.configured_rtp.min(), 0)} – {pct(g.configured_rtp.max(), 0)}")
    r.kpi("Max multiplier", f"{g.max_multiplier.max():,.0f}×", g.loc[g.max_multiplier.idxmax(), "theme"])
    r.kpi("Bet range", f"${g.min_bet_cents.min() / 100:.2f} – ${g.max_bet_cents.max() / 100:.0f}")
    vh = g.loc[g.payout_multiplier_variance.idxmax()]
    r.find(f"House edge (1 − RTP) runs from {pct(g.hold.min(), 0)} ({g.loc[g.hold.idxmin(), 'theme']}) to {pct(g.hold.max(), 0)} "
           f"({g.loc[g.hold.idxmax(), 'theme']}). Higher edge does not mean less play — see prepared_daily_view by theme.")
    r.find(f"Volatility spans orders of magnitude: payout variance {g.payout_multiplier_variance.min():.2f} to {vh.payout_multiplier_variance:,.0f} ({vh.theme}). "
           "High-variance games need much longer to converge to their theo hold.")
    r.find("Hit probability counts any positive payout, including ones smaller than the bet, so a 50% hit rate still loses money on average.")
    r.section("Game design", "", [
        hbar("House edge (1 − configured RTP)", list(g.sort_values('hold', ascending=False).label),
             g.sort_values('hold', ascending=False).hold.values, fmt="pct"),
        scatter("Hit probability vs payout variance", [pts("Configuration", g.payout_multiplier_variance, g.hit_probability, g.label, mode="markers+text")],
                fx="num", fy="pct", xtitle="Payout multiplier variance (log)", ytitle="Hit probability", logx=True),
        hbar("Max multiplier", list(g.sort_values('max_multiplier', ascending=False).label),
             g.sort_values('max_multiplier', ascending=False).max_multiplier.values, fmt="num"),
        table_block("All configurations", g.drop(columns=["label", "hold"])),
    ])


def b_machine_day(r: Report):
    m = r.df[r.df.active].copy()
    gm = cached("2_machine_decision/game_math.parquet").set_index("config_id")
    for c in ["coin_in_cents", "payout_cents", "house_win_cents", "theo_cents", "carded_coin_in_cents"]:
        m[c.replace("_cents", "_usd")] = m[c] / 100
    d = m.groupby("gaming_date").agg(ci=("coin_in_usd", "sum"), hw=("house_win_usd", "sum"), sp=("paid_spins", "sum"),
                                     pos=("payout_positive_spins", "sum"), card=("carded_coin_in_usd", "sum"),
                                     av=("available_seconds", "sum"), occ=("occupied_seconds", "sum"),
                                     sch=("scheduled_seconds", "sum"))
    d["bet"] = d.ci / d.sp
    d["hit"] = d.pos / d.sp
    cfg = m.groupby("config_id").agg(sp=("paid_spins", "sum"), pos=("payout_positive_spins", "sum"),
                                     ci=("coin_in_usd", "sum"), hw=("house_win_usd", "sum"))
    cfg["hit"] = cfg.pos / cfg.sp
    cfg["hit_cfg"] = gm.hit_probability.reindex(cfg.index)
    cfg["bet"] = cfg.ci / cfg.sp
    cfg = cfg.sort_values("hit")
    neg = (m.house_win_usd < 0).mean()
    negv = m.assign(vol=m.config_id.map(gm.volatility_class)).groupby("vol").house_win_usd.apply(lambda s: (s < 0).mean())
    negv = negv.reindex([v for v in ["low", "medium", "high", "very_high"] if v in negv.index])
    down = 1 - m.available_seconds.sum() / m.scheduled_seconds.sum()
    x = ds(d.index)
    r.headline = f"Raw meters in cents for every machine-day: {m.paid_spins.sum() / 1e6:.0f}M paid spins, average bet {usd(d.ci.sum() / d.sp.sum(), 2)}, {pct(neg, 0)} of machine-days lose money for the house."
    r.kpi("Paid spins", n(m.paid_spins.sum()))
    r.kpi("Average bet", f"${d.ci.sum() / d.sp.sum():.2f}")
    r.kpi("Observed hit rate", pct(d.pos.sum() / d.sp.sum()))
    r.kpi("Machine-days with negative house win", pct(neg))
    r.kpi("Downtime", pct(down, 2), "of scheduled seconds")
    r.kpi("Carded share of coin-in", pct(d.card.sum() / d.ci.sum()))
    r.find(f"Observed hit rate per configuration matches the configured hit probability within ~1 point (e.g. {cfg.index[-1]}: {pct(cfg.hit.iloc[-1])} vs {pct(cfg.hit_cfg.iloc[-1])}), so the meters are internally consistent.")
    r.find(f"Negative house-win days are normal: {pct(neg)} of machine-days pay out more than they take in, most often on the very-high-volatility game. By volatility class: "
           + ", ".join(f"{k.replace('_', ' ')} {pct(v, 0)}" for k, v in negv.items()) + ".")
    r.find(f"Average bet is stable at ${d.bet.min():.2f}–${d.bet.max():.2f} per day; volume (spins), not bet size, drives daily swings.")
    r.find(f"Machines are available {pct(1 - down, 2)} of scheduled time; seats are occupied {pct(d.occ.sum() / d.av.sum())} of available time.")
    r.section("Daily meters", "", [
        line("Coin-in and house win per day", x, {"Coin-in": d.ci, "House win": d.hw}, fmt="usd"),
        line("Paid spins per day", x, {"Paid spins": d.sp}, fmt="int"),
        line("Average bet per day", x, {"Coin-in / paid spins": d.bet}, fmt="usd"),
        line("Carded share of coin-in per day", x, {"Carded share": d.card / d.ci}, fmt="pct"),
    ])
    r.section("By configuration", "", [
        bar("Machine-days with negative house win, by volatility", [k.replace("_", " ") for k in negv.index],
            {"Share of machine-days": negv.values}, fmt="pct"),
        bar("Observed vs configured hit rate", list(cfg.index), {"Observed": cfg.hit, "Configured": cfg.hit_cfg}, fmt="pct"),
        hbar("Average bet by configuration", list(cfg.sort_values('bet', ascending=False).index),
             cfg.sort_values('bet', ascending=False).bet.values, fmt="usd"),
        hist("House win per machine-day", m.house_win_usd, fmt="usd"),
        hist("Occupied hours per machine-day", m.occupied_seconds / 3600, fmt="num"),
    ])


def b_machines(r: Report):
    m = r.df.copy()
    m["install_year"] = m.install_date.dt.year
    yr = m.groupby("install_year").size()
    mt = pd.crosstab(m.theme, m.manufacturer)
    lc = pd.crosstab(m.manufacturer, m.lease_class)
    new = m[m.install_date >= "2025-01-01"]
    r.headline = f"{len(m)} machines from {m.manufacturer.nunique()} manufacturers; {len(new)} installed during the window, {m.retire_date.notna().sum()} retired."
    r.kpi("Machines", len(m))
    r.kpi("Owned", pct((m.lease_class == 'owned').mean(), 0))
    r.kpi("Installed in 2025", len(new))
    r.kpi("Retired in 2025", int(m.retire_date.notna().sum()))
    r.kpi("Median install year", int(m.install_year.median()))
    r.find(f"Manufacturer mix: " + ", ".join(f"{k} {v}" for k, v in m.manufacturer.value_counts().items()) + ".")
    r.find(f"{m.theme.value_counts().index[0]} is the most common theme ({m.theme.value_counts().iloc[0]} machines, {pct(m.theme.value_counts().iloc[0] / len(m), 0)} of the floor).")
    r.find(f"The fleet is old: install dates go back to {m.install_date.min():%Y}; {pct((m.install_year <= 2019).mean(), 0)} were installed in 2019 or earlier.")
    r.find(f"{len(new)} machines arrived in 2025 (" + ", ".join(sorted(new.install_date.dt.strftime('%b %d').unique())) + "); retirements: " +
           ", ".join(f"{a} on {b:%b %d}" for a, b in zip(m[m.retire_date.notna()].machine_id, m[m.retire_date.notna()].retire_date)) + ".")
    r.section("Fleet composition", "", [
        bar("Machines by install year", list(yr.index), {"Machines": yr.values}, fmt="int"),
        heat("Theme × manufacturer", list(mt.columns), list(mt.index), mt.values, fmt="int"),
        bar("Lease class by manufacturer", list(lc.index), {k: lc[k] for k in lc.columns}, fmt="int", stacked=True),
        hbar("Machines by theme", list(m.theme.value_counts().index), m.theme.value_counts().values, fmt="int"),
    ])


def b_operations(r: Report):
    o = r.df.copy()
    mach = cached("2_machine_decision/machines.parquet").set_index("machine_id")
    o["manufacturer"] = o.machine_id.map(mach.manufacturer)
    o["down_h"] = (o.available_at_utc - o.opened_at_utc).dt.total_seconds() / 3600
    o["resp_min"] = (o.work_started_at_utc - o.opened_at_utc).dt.total_seconds() / 60
    o["cost_usd"] = o.direct_cost_cents / 100
    fr = o[o.event_type == "fault_repair"].copy()
    fr["week"] = fr.opened_at_local.dt.to_period("W-SUN").dt.start_time
    wk = full_weeks(fr.groupby("week").size())
    hr = fr.opened_at_local.dt.hour.value_counts().reindex(range(24), fill_value=0)
    fleet = cached("2_machine_decision/machines.parquet").manufacturer.value_counts()
    bym = fr.groupby("manufacturer").agg(n=("operation_id", "size"), down=("down_h", "median"), cost=("cost_usd", "median"))
    bym["per_machine"] = bym.n / fleet.reindex(bym.index)
    bym = bym.sort_values("per_machine", ascending=False)
    top = fr.machine_id.value_counts().head(10)
    et = o.event_type.value_counts()
    r.headline = f"{len(fr):,} fault repairs in six months; median machine downtime {fr.down_h.median():.1f} h; {bym.index[0]} machines fail {bym.per_machine.iloc[0] / bym.per_machine.iloc[-1]:.1f}× as often as {bym.index[-1]}."
    r.kpi("Tickets", f"{len(o):,}", ", ".join(f"{k} {v}" for k, v in et.items() if k != 'fault_repair'))
    r.kpi("Fault repairs", f"{len(fr):,}", f"{len(fr) / 181:.1f} per day")
    r.kpi("Median downtime", f"{fr.down_h.median():.1f} h", f"p90 {fr.down_h.quantile(.9):.1f} h")
    waited = fr[fr.resp_min > 0]
    r.kpi("Repairs that waited for a tech", pct(len(waited) / len(fr), 0), f"median wait {waited.resp_min.median():.0f} min")
    r.kpi("Direct repair cost", usd(fr.cost_usd.sum()), f"median {usd(fr.cost_usd.median())}")
    r.find(f"Fault rate per machine: " + ", ".join(f"{k} {v:.1f}" for k, v in bym.per_machine.items()) + " repairs per machine over six months.")
    r.find(f"Repair downtime is right-skewed: half are fixed within {fr.down_h.median():.1f} h but 10% take longer than {fr.down_h.quantile(.9):.1f} h — those are the costly ones in lost play.")
    r.find(f"{pct(1 - len(waited) / len(fr), 0)} of repairs start the moment the fault opens; the other {pct(len(waited) / len(fr), 0)} wait a median "
           f"{waited.resp_min.median():.0f} min (p90 {waited.resp_min.quantile(.9):.0f} min) for a free technician — the lever behind the A-TECH-SHIFT action.")
    r.find(f"Faults are reported mostly during busy hours (peak at {hr.idxmax()}:00 local), which is when downtime costs the most.")
    r.find(f"The ten most fault-prone machines account for {top.sum()} repairs ({pct(top.sum() / len(fr), 0)}); {top.index[0]} alone had {top.iloc[0]}.")
    other = o[o.event_type != "fault_repair"]
    r.find(f"Non-repair tickets: {len(other)} (installs, moves, maintenance, retirements). The largest single cost is {usd(o.cost_usd.max())} ({o.loc[o.cost_usd.idxmax(), 'event_type']}).")
    r.section("Fault volume", "", [
        line("Fault repairs per week", ds(wk.index), {"Repairs": wk.values}, fmt="int", mode="lines+markers",
             sub="Full Mon–Sun weeks only."),
        bar("Fault repairs by local hour opened", list(range(24)), {"Repairs": hr.values}, fmt="int"),
        bar("Repairs per machine by manufacturer", list(bym.index), {"Repairs per machine": bym.per_machine}, fmt="num"),
        hbar("Most fault-prone machines", list(top.index), top.values, fmt="int"),
    ])
    r.section("Repair duration and cost", "", [
        hist("Downtime per repair (hours)", fr.down_h, fmt="num"),
        hist("Wait for a technician (minutes, repairs that waited)", waited.resp_min, fmt="num"),
        hist("Direct cost per repair", fr.cost_usd, fmt="usd"),
        table_block("Non-repair tickets", other[["machine_id", "location_id", "event_type", "opened_at_local", "down_h", "cost_usd"]],
                    fmts={"cost_usd": "usd"}),
    ])


def b_placements(r: Report):
    p = r.df.copy()
    ch = p.groupby(p.effective_from_utc.dt.strftime("%Y-%m-%d")).size()
    multi = p[p.machine_id.duplicated(keep=False)].sort_values(["machine_id", "effective_from_utc"])
    cfg = p[p.effective_to_utc.isna()].config_id.value_counts()
    r.headline = f"{len(p)} placement intervals for {p.machine_id.nunique()} machines; {p.machine_id.duplicated().sum()} machines changed location during the window."
    r.kpi("Placements", len(p))
    r.kpi("Machines moved", int(p.machine_id.duplicated().sum()))
    r.kpi("Still placed at end", int(p.effective_to_utc.isna().sum()))
    r.kpi("Change dates", len(ch) - 1, "after Jan 1")
    r.find(f"{ch.iloc[0]} placements start on {ch.index[0]} (the opening state); the remaining {ch.iloc[1:].sum()} are installs and moves on {len(ch) - 1} dates.")
    r.find("Always join machine_day to placements on [effective_from_utc, effective_to_utc) — a machine's location can change mid-window.")
    r.find("Moved machines: " + ", ".join(sorted(multi.machine_id.unique())) + ".")
    r.section("Changes", "", [
        bar("New placements by start date (after Jan 1)", list(ch.index[1:]), {"Placements": ch.values[1:]}, fmt="int"),
        hbar("Current placements by configuration", list(cfg.index), cfg.values, fmt="int"),
        table_block("Machines with more than one placement", multi),
    ])


def b_fnb_transactions(r: Report):
    f = r.df.copy()
    f["cash"] = f.cash_receipt_cents / 100
    f["face"] = f.face_value_cents / 100
    f["cogs"] = f.cogs_cents / 100
    f["comp"] = f.comp_id.notna()
    f["carded"] = f.player_id.notna()
    out = {"O-BAR": "Ace Bar", "O-CAFE": "Lantern Cafe", "O-REST": "Restaurant"}
    fl = cached("2_machine_decision/floor_locations.parquet")
    out.update(fl[fl.node_type == "outlet"].set_index("outlet_id").name.dropna().to_dict())
    f["outlet"] = f.outlet_id.map(out)
    o = f.groupby("outlet").agg(tix=("transaction_id", "size"), cash=("cash", "sum"), cogs=("cogs", "sum"),
                                comp=("comp", "mean"), carded=("carded", "mean")).sort_values("cash", ascending=False)
    it = f.groupby("item").agg(tix=("transaction_id", "size"), cash=("cash", "sum"), face=("face", "mean"),
                               cogs=("cogs", "mean"), comp=("comp", "mean"))
    it["margin"] = 1 - it.cogs / it.face
    it = it.sort_values("cash", ascending=False)
    hr = f.groupby(["local_hour", "outlet"]).size().unstack(fill_value=0).reindex(range(24), fill_value=0)
    f["date"] = (f.event_at_local - pd.Timedelta(hours=6)).dt.normalize()
    d = f.groupby("date").agg(cash=("cash", "sum"), comp_face=("face", lambda s: s[f.loc[s.index, 'comp']].sum()))
    roll = d.cash.rolling(7, min_periods=1).mean()
    r.headline = f"{len(f):,} POS tickets, {usd(f.cash.sum())} cash; {pct(f.comp.mean(), 0)} of tickets are comps and {pct(1 - f.carded.mean(), 0)} are uncarded."
    r.kpi("Tickets", f"{len(f):,}", f"{len(f) / 181:,.0f} per day")
    r.kpi("Cash receipts", usd(f.cash.sum()))
    r.kpi("Cost of goods", usd(f.cogs.sum()), f"gross margin on cash {pct(1 - f[~f.comp].cogs.sum() / f.cash.sum())}")
    r.kpi("Comped tickets", pct(f.comp.mean()), f"face value {usd(f[f.comp].face.sum())}")
    r.kpi("Carded tickets", pct(f.carded.mean()))
    r.find(f"{o.index[0]} takes the most cash ({usd(o.cash.iloc[0])} from {o.tix.iloc[0]:,} tickets); "
           + ", ".join(f"{k} {usd(v)} from {t:,} tickets" for k, v, t in zip(o.index[1:], o.cash.iloc[1:], o.tix.iloc[1:])) + ".")
    r.find(f"Comps are {pct(f.comp.mean(), 0)} of tickets but zero cash; their cost of goods ({usd(f[f.comp].cogs.sum())}) is the real expense, not the {usd(f[f.comp].face.sum())} menu value.")
    r.find(f"Highest-margin items: " + ", ".join(f"{k} {pct(v, 0)}" for k, v in it.margin.sort_values(ascending=False).head(3).items())
           + f"; lowest: {it.margin.idxmin()} {pct(it.margin.min(), 0)}.")
    gd = [(h + 6) % 24 for h in range(24)]
    hours_txt = []
    for k in o.index:
        col = hr[k].reindex(gd)
        open_h = [h for h in gd if col[h] > 0]
        hours_txt.append(f"{k} {open_h[0]}:00–{(open_h[-1] + 1) % 24}:00, peak {col.idxmax()}:00")
    r.find("Each outlet keeps its own hours (gaming-day order): " + "; ".join(hours_txt) + ".")
    r.find(f"One-third of sales ({pct(1 - f.carded.mean(), 0)}) have no player card, so F&B linked to players understates total F&B.")
    r.section("Daily and hourly", "", [
        line("Cash receipts per day", ds(d.index), {"Daily": d.cash, "7-day average": roll}, fmt="usd"),
        line("Tickets by local hour and outlet", list(range(24)), {k: hr[k] for k in o.index}, fmt="int", mode="lines+markers"),
    ])
    r.section("Outlets and items", "", [
        bar("Cash by outlet", list(o.index), {"Cash": o.cash}, fmt="usd"),
        bar("Comp and carded share by outlet", list(o.index), {"Comped tickets": o.comp, "Carded tickets": o.carded}, fmt="pct"),
        hbar("Cash by item", list(it.index), it.cash.values, fmt="usd"),
        hbar("Gross margin by item (1 − cogs / menu price)", list(it.sort_values('margin', ascending=False).index),
             it.sort_values('margin', ascending=False).margin.values, fmt="pct"),
    ])


def b_loyalty_ledger(r: Report):
    l = r.df.copy()
    l["week"] = (l.event_at_utc - pd.Timedelta(hours=14)).dt.to_period("W-SUN").dt.start_time
    wk = full_weeks(l.groupby(["week", "event_type"]).points_delta.sum().unstack(fill_value=0))
    wkn = full_weeks(l.groupby(["week", "event_type"]).size().unstack(fill_value=0))
    red = l[l.event_type == "redeem"]
    ben = red.groupby("benefit_id").agg(n=("loyalty_event_id", "size"), face=("face_value_cents", "mean"),
                                        cost=("economic_cost_cents", "mean")).sort_values("n", ascending=False)
    ben["face"] /= 100
    ben["cost"] /= 100
    up = l[l.tier_before != l.tier_after]
    upm = up.assign(m=up.event_at_utc.dt.strftime("%Y-%m"), t=up.tier_before + " → " + up.tier_after).groupby(["m", "t"]).size().unstack(fill_value=0)
    aw = l[l.event_type == "award"]
    r.headline = f"{len(aw):,} point awards and {len(red):,} redemptions; members earned {n(aw.points_delta.sum())} points and spent {n(-red.points_delta.sum())} ({pct(-red.points_delta.sum() / aw.points_delta.sum())})."
    r.kpi("Ledger events", f"{len(l):,}", f"{l.player_id.nunique():,} players")
    r.kpi("Points awarded", n(aw.points_delta.sum()))
    r.kpi("Points redeemed", n(-red.points_delta.sum()), pct(-red.points_delta.sum() / aw.points_delta.sum()) + " of awarded")
    r.kpi("Redemption cost to house", usd(red.economic_cost_cents.sum() / 100), f"face value {usd(red.face_value_cents.sum() / 100)}")
    r.kpi("Tier upgrades", f"{len(up):,}")
    r.find(f"Points pile up: only {pct(-red.points_delta.sum() / aw.points_delta.sum())} of awarded points were redeemed. Balances restart at 0 each year, so most points will expire unused — comps are a light lever today.")
    r.find(f"Redemptions are all F&B comps; the most popular are {', '.join(ben.index[:3])}. Economic cost averages {pct((ben.cost * ben.n).sum() / (ben.face * ben.n).sum(), 0)} of face value.")
    r.find(f"Tier upgrades: " + ", ".join(f"{k} {v:,}" for k, v in up.assign(t=up.tier_before + ' → ' + up.tier_after).t.value_counts().items()) + ". Upgrades accumulate through the half-year because tiers use lifetime points.")
    r.find(f"Median award is {aw.points_delta.median():.0f} points per segment; a few large awards ({aw.points_delta.max():,} max) come from long, high-bet sessions.")
    r.section("Weekly flow", "Weeks are gaming weeks (UTC shifted to 06:00 local); full Mon–Sun weeks only.", [
        line("Points awarded vs redeemed per week", ds(wk.index), {"Awarded": wk.get("award"), "Redeemed": -wk.get("redeem")}, fmt="int"),
        line("Redemptions per week", ds(wkn.index), {"Redemptions": wkn.get("redeem")}, fmt="int"),
        bar("Tier upgrades per month", list(upm.index), {k: upm[k] for k in upm.columns}, fmt="int", stacked=True),
    ])
    r.section("Benefits", "", [
        hbar("Redemptions by benefit", list(ben.index), ben.n.values, fmt="int"),
        bar("Face value vs economic cost per redemption", list(ben.index), {"Face value": ben.face, "Economic cost": ben.cost}, fmt="usd"),
        hist("Points per award", aw.points_delta, fmt="int", log=True, sub="Log-scaled bins."),
    ])


def b_players(r: Report):
    p = r.df.copy()
    p["enroll_m"] = p.enrolled_at_utc.dt.to_period("M").dt.start_time
    em = p.groupby("enroll_m").size()
    new = p[p.enrolled_at_utc >= "2025-01-01"]
    reg = p.home_region.value_counts()
    age = p.age_band.fillna("unknown").value_counts().reindex(["21-34", "35-49", "50-64", "65+", "unknown"])
    rt = pd.crosstab(p.home_region, p.age_band.fillna("unknown"))
    rt = rt[[c for c in ["21-34", "35-49", "50-64", "65+", "unknown"] if c in rt.columns]]
    rt = rt.div(rt.sum(axis=1), axis=0)
    r.headline = f"{len(p):,} loyalty accounts; {pct(len(new) / len(p), 0)} enrolled during the window, and {pct((p.opening_tier == 'Base').mean(), 0)} started the year at Base tier."
    r.kpi("Accounts", f"{len(p):,}")
    r.kpi("Enrolled in 2025", f"{len(new):,}", pct(len(new) / len(p)))
    r.kpi("Opening Gold / Platinum", f"{(p.opening_tier == 'Gold').sum():,} / {(p.opening_tier == 'Platinum').sum():,}")
    r.kpi("Missing age band", pct(p.age_band.isna().mean()))
    r.find(f"The base grew fast: {len(new):,} new accounts in six months vs {len(p) - len(new):,} existing — most guests are new to the program.")
    r.find(f"Regional ({pct(reg.get('Regional') / len(p), 0)}) and Domestic ({pct(reg.get('Domestic') / len(p), 0)}) visitors dominate account counts; "
           f"Locals are only {pct(reg.get('Local') / len(p), 0)} of accounts but play far more often (see player_period).")
    r.find(f"Opening lifetime points are zero for {pct((p.opening_lifetime_points == 0).mean(), 0)} of accounts; the rest have a long-tailed history up to {p.opening_lifetime_points.max():,}.")
    r.find(f"Age is unknown for {pct(p.age_band.isna().mean(), 0)} of accounts — treat age-band analyses as partial.")
    r.section("Enrollment", "", [
        bar("Enrollments per month", ds(em.index), {"Enrollments": em.values}, fmt="int",
            sub="Pre-2025 history is accounts still active in the window.", wide=True),
    ])
    r.section("Who they are", "", [
        hbar("Accounts by home region", list(reg.index), reg.values, fmt="int"),
        bar("Accounts by age band", list(age.index), {"Accounts": age.values}, fmt="int"),
        heat("Age mix within each region", list(rt.columns), list(rt.index), rt.values, fmt="pct", sub="Row shares."),
        hist("Opening lifetime points (accounts with history)", p.opening_lifetime_points[p.opening_lifetime_points > 0], fmt="int", log=True),
    ])


def b_sessions(r: Report):
    s = r.df.copy()
    s["mins"] = (s.end_utc - s.start_utc).dt.total_seconds() / 60
    s["ci"] = s.coin_in_cents / 100
    s["net"] = (s.payout_cents - s.coin_in_cents) / 100
    d = s.groupby("gaming_date").agg(n=("session_segment_id", "size"), ci=("ci", "sum"), players=("player_id", "nunique"))
    s["wd"] = s.gaming_date.dt.strftime("%a")
    hm = s.groupby(["wd", "local_hour"]).size().unstack(fill_value=0).reindex(WEEK)
    hm = hm.div(s.groupby("wd").gaming_date.nunique().reindex(WEEK), axis=0)
    order = [(h + 6) % 24 for h in range(24)]
    hm = hm.reindex(columns=order, fill_value=0)
    bet = s.fixed_bet_cents.value_counts().sort_index()
    cfg = s.groupby("config_id").agg(n=("session_segment_id", "size"), mins=("mins", "median"), ci=("ci", "median")).sort_values("n", ascending=False)
    win = (s.net > 0).mean()
    r.headline = f"{len(s):,} carded session segments by {s.player_id.nunique():,} players; median session {s.mins.median():.0f} min at a {usd(s.fixed_bet_cents.median() / 100, 2)} bet."
    r.kpi("Session segments", f"{len(s):,}", f"{len(s) / 181:,.0f} per day")
    r.kpi("Median duration", f"{s.mins.median():.0f} min", f"p90 {s.mins.quantile(.9):.0f} min")
    r.kpi("Median coin-in", usd(s.ci.median()), f"mean {usd(s.ci.mean())}")
    r.kpi("Sessions won by player", pct(win))
    r.kpi("Median bet", f"${s.fixed_bet_cents.median() / 100:.2f}")
    r.find(f"Each session uses one fixed bet; {pct((s.fixed_bet_cents <= 100).mean(), 0)} of sessions bet $1 or less. High-limit bets ($5+) are {pct((s.fixed_bet_cents >= 500).mean(), 1)} of sessions but {pct(s[s.fixed_bet_cents >= 500].ci.sum() / s.ci.sum(), 0)} of coin-in.")
    r.find(f"Players walk away ahead in {pct(win, 0)} of sessions — the house edge shows up in totals, not in most individual sessions.")
    r.find(f"Play peaks in the evening ({hm.sum().idxmax()}:00) and on Friday/Saturday nights; the quietest hour is {hm.sum().idxmin()}:00.")
    r.find(f"Busiest days: " + ", ".join(f"{k:%a %b %d} ({v:,})" for k, v in d.n.sort_values(ascending=False).head(3).items()) + ".")
    r.find(f"{s.logical_session_id.duplicated().sum():,} logical sessions cross the 06:00 gaming-day boundary and are split into two segments.")
    r.section("When people play", "", [
        line("Sessions per gaming day", ds(d.index), {"Sessions": d.n, "7-day average": d.n.rolling(7, min_periods=1).mean()}, fmt="int"),
        heat("Average sessions started by weekday and local hour", [f"{h}:00" for h in order], WEEK, hm.values, fmt="num",
             sub="Gaming day order: 06:00 → 05:00."),
    ])
    r.section("Session shape", "", [
        hist("Session duration (minutes)", s.mins, fmt="num"),
        bar("Sessions by fixed bet", [f"${b / 100:.2f}" for b in bet.index], {"Sessions": bet.values}, fmt="int"),
        hist("Coin-in per session", s.ci, fmt="usd", log=True, sub="Log-scaled bins."),
        hist("Player net per session", s.net, fmt="usd"),
        hbar("Sessions by configuration", list(cfg.index), cfg.n.values, fmt="int"),
    ])


def b_trips(r: Report):
    t = r.df.copy()
    t["hours"] = (t.last_observed_at_utc - t.first_observed_at_utc).dt.total_seconds() / 3600
    t["date"] = (t.first_observed_local - pd.Timedelta(hours=6)).dt.normalize()
    d = t.groupby("date").size()
    vp = t.groupby("player_id").size()
    vpb = pd.cut(vp, [0, 1, 2, 3, 5, 10, 20, 50, 1000], labels=["1", "2", "3", "4–5", "6–10", "11–20", "21–50", "50+"]).value_counts().sort_index()
    hr = t.first_observed_local.dt.hour.value_counts().reindex(range(24), fill_value=0)
    wd = t.date.dt.strftime("%a").value_counts().reindex(WEEK) / t.groupby(t.date.dt.strftime("%a")).date.nunique().reindex(WEEK)
    r.headline = f"{len(t):,} observed visits by {t.player_id.nunique():,} players; {pct((vp == 1).mean(), 0)} visited once, while a core of regulars came 20+ times."
    r.kpi("Visits", f"{len(t):,}", f"{len(t) / 181:,.0f} per day")
    r.kpi("Visits per player", f"{vp.mean():.1f}", f"median {vp.median():.0f}")
    r.kpi("Median observed duration", f"{t.hours.median():.1f} h")
    r.kpi("Open at window end", int((~t.observation_complete).sum()))
    r.find(f"Visit frequency is very uneven: {pct((vp == 1).mean(), 0)} of players appear once, {pct((vp > 20).mean(), 1)} appear 20+ times and they account for {pct(vp[vp > 20].sum() / vp.sum(), 0)} of all visits.")
    r.find(f"Duration is first-to-last carded activity, not arrival-to-departure; median {t.hours.median():.1f} h, {pct((t.hours == 0).mean(), 0)} of visits are a single instant (one F&B or loyalty touch).")
    r.find(f"Visits start most often around {hr.idxmax()}:00; Saturdays average {wd['Sat']:,.0f} visits vs {wd['Tue']:,.0f} on Tuesdays.")
    r.section("Visit patterns", "", [
        line("Visits per gaming day", ds(d.index), {"Visits": d.values, "7-day average": d.rolling(7, min_periods=1).mean().values}, fmt="int"),
        bar("Average visits by weekday", WEEK, {"Visits": wd.values}, fmt="int"),
        bar("Visits by local start hour", list(range(24)), {"Visits": hr.values}, fmt="int"),
        bar("Players by number of visits", list(vpb.index.astype(str)), {"Players": vpb.values}, fmt="int"),
        hist("Observed visit duration (hours, > 0)", t.hours[t.hours > 0], fmt="num"),
    ])


def b_events(r: Report):
    e = r.df.copy().sort_values("start_date")
    pdv = cached("1_prepared_views/property_day.parquet")
    base = pdv[pdv.events_active.isna()].coin_in_usd.mean()
    lifts = []
    for _, row in e.iterrows():
        m = pdv[pdv.events_active.fillna("").str.contains(re.escape(row["name"]))]
        lifts.append(m.coin_in_usd.mean() / base - 1 if len(m) else np.nan)
    e["coin_in_lift"] = lifts
    e["days"] = (e.end_date - e.start_date).dt.days + 1
    e["lead_days"] = (e.start_date - e.announced_date).dt.days
    srt = e.sort_values("coin_in_lift", ascending=False)
    r.headline = f"{len(e)} events in the window; weekend events (Super Bowl, the slot tournament, EDC) lift daily coin-in the most."
    r.kpi("Events", len(e), ", ".join(f"{k} {v}" for k, v in e.event_type.value_counts().items()))
    r.kpi("Event days", int(e.days.sum()))
    r.kpi("Best lift", signed_pct(srt.coin_in_lift.iloc[0]), srt.name.iloc[0])
    r.find(f"Coin-in lift vs the no-event daily average ({usd(base)}): " + ", ".join(f"{a} {signed_pct(b)}" for a, b in zip(srt.name, srt.coin_in_lift)) + ".")
    r.find("Part of the lift is the weekend itself: Super Bowl, EDC and the slot tournament fall on weekends, while CES and CinemaCon are mid-week conventions. Compare against same-weekday baselines before crediting an event.")
    r.find(f"Property promotions ({', '.join(e[e.local_scope == 'property'].name)}) are fictional; citywide events have real dates. Most events were announced months ahead (median {e.lead_days.median():.0f} days), so they can be planned for.")
    r.section("Calendar and impact", "", [
        gantt("Event timeline", list(e.name), ds(e.start_date), ds(e.end_date + pd.Timedelta(days=1))),
        hbar("Coin-in lift vs no-event average", list(srt.name), srt.coin_in_lift.values, fmt="pct",
             sub="Joined with property_day on events_active."),
        table_block("All events", e.drop(columns=["source_url"]), fmts={"coin_in_lift": "pct"}),
    ])


def b_zone_traffic_hourly(r: Report):
    z = r.df.copy()
    zn = zone_names()
    z["zone"] = z.zone_id.map(zn)
    z["date"] = (z.hour_start_local - pd.Timedelta(hours=6)).dt.normalize()
    hr = z.groupby(["local_hour", "zone"]).entries_count.mean().unstack()
    d = z.groupby(["date", "zone"]).entries_count.sum().unstack()
    tot = z.groupby("zone").entries_count.sum().sort_values(ascending=False)
    d = d[tot.index]
    hr = hr[tot.index]
    st = z.counter_status.value_counts()
    z["wd"] = z.date.dt.strftime("%a")
    hm = z.groupby(["wd", "local_hour"]).entries_count.mean().unstack().reindex(WEEK)
    order = [(h + 6) % 24 for h in range(24)]
    hm = hm[order]
    off = z[z.counter_status != "ok"].groupby("zone").size().reindex(tot.index, fill_value=0)
    b40 = d["Back Forty"] if "Back Forty" in d else None
    r.headline = f"{n(z.entries_count.sum())} sensor crossings across {z.sensor_id.nunique()} zone counters; {st.get('offline', 0) + st.get('partial', 0)} sensor-hours were offline or partial."
    r.kpi("Sensor-hours", f"{len(z):,}")
    r.kpi("Crossings counted", n(z.entries_count.sum()))
    r.kpi("Offline / partial hours", f"{st.get('offline', 0)} / {st.get('partial', 0)}")
    r.kpi("Busiest zone", tot.index[0])
    r.find(f"{tot.index[0]} and {tot.index[1]} see the most crossings; {tot.index[-1]} the fewest. Counts are crossings, not unique people, and seated players don't trigger sensors.")
    r.find(f"Traffic peaks around {hm.mean().idxmax()}:00 and bottoms out near {hm.mean().idxmin()}:00 local; weekends are busier across all hours.")
    if b40 is not None:
        clo = (d.index >= "2025-03-03") & (d.index < "2025-04-07")
        r.find(f"Back Forty crossings dropped from {b40[~clo].mean():,.0f} to {b40[clo].mean():,.0f} per day ({signed_pct(b40[clo].mean() / b40[~clo].mean() - 1)}) while its walkway was closed.")
    r.find("A missing count is not zero: offline hours have null entries_count. Use coverage_minutes to scale or exclude partial hours.")
    r.section("Traffic over time", "", [
        line("Daily crossings by zone", ds(d.index), {k: d[k] for k in d.columns}, fmt="int", sub="Daily sums of hourly counts."),
        line("Average crossings by local hour", list(range(24)), {k: hr[k] for k in hr.columns}, fmt="num", mode="lines+markers"),
        heat("Average crossings per sensor-hour, weekday × hour", [f"{h}:00" for h in order], WEEK, hm.values, fmt="num"),
    ])
    r.section("Data quality", "", [
        bar("Counter status", list(st.index), {"Sensor-hours": st.values}, fmt="int"),
        hbar("Offline or partial hours by zone", list(off.index), off.values, fmt="int"),
    ])


def b_weather_daily(r: Report):
    w = r.df.copy().sort_values("source_date")
    pdv = cached("1_prepared_views/property_day.parquet").set_index("gaming_date")
    w["coin_in"] = w.source_date.map(pdv.coin_in_usd)
    rain = w[w.prcp_mm > 0]
    corr = np.corrcoef(w.tmax_c, w.coin_in)[0, 1]
    w["wd"] = w.source_date.dt.strftime("%a")
    resid = w.coin_in / w.groupby("wd").coin_in.transform("mean") - 1
    rc = np.corrcoef(w.tmax_c, resid)[0, 1]
    r.headline = f"Real NOAA data for Las Vegas airport: highs climb from ~{w.tmax_c.head(14).mean():.0f}°C in early January to ~{w.tmax_c.tail(14).mean():.0f}°C by late June; only {len(rain)} days with measurable rain."
    r.kpi("Days", len(w))
    r.kpi("Hottest day", f"{w.tmax_c.max():.1f}°C", w.loc[w.tmax_c.idxmax(), 'source_date'].strftime("%b %d"))
    r.kpi("Coldest night", f"{w.tmin_c.min():.1f}°C", w.loc[w.tmin_c.idxmin(), 'source_date'].strftime("%b %d"))
    r.kpi("Rain days", len(rain), f"{w.prcp_mm.sum():.1f} mm total")
    r.find(f"Temperature rises steadily through the window (a ~{w.tmax_c.tail(30).mean() - w.tmax_c.head(30).mean():.0f}°C increase in average highs from January to June).")
    r.find(f"Rain is rare: {len(rain)} days with any measured precipitation, {int(w.prcp_mflag.eq('T').sum())} more with only a trace.")
    r.find(f"Weather barely explains play: correlation between daily high and coin-in is {corr:.2f}, and {rc:.2f} after removing the weekday effect.")
    r.find("These are calendar dates; the gaming day runs 06:00–06:00, so overnight play maps to the previous calendar date.")
    x = ds(w.source_date)
    r.section("Weather", "", [
        line("Daily high and low temperature (°C)", x, {"High": w.tmax_c, "Low": w.tmin_c}, fmt="num"),
        bar("Daily precipitation (mm)", x, {"Precipitation": w.prcp_mm}, fmt="num"),
        scatter("Daily high vs property coin-in", [pts("Day", w.tmax_c, w.coin_in, x)], fx="num", fy="usd",
                xtitle="High (°C)", ytitle="Coin-in", sub=f"Correlation {corr:.2f}; weekday effects dominate."),
    ])


def b_city_visitation_monthly(r: Report):
    c = r.df.copy().sort_values("month")
    pdv = cached("1_prepared_views/property_day.parquet").copy()
    pdv["month"] = pdv.gaming_date.dt.strftime("%Y-%m")
    pm = pdv.groupby("month").agg(ci=("coin_in_usd", "sum"), days=("gaming_date", "count"))
    pm["ci_day"] = pm.ci / pm.days
    ga = pm.ci_day.reindex(c.month)
    idx = {"City visitors per day": c.mean_visitors_per_calendar_day.values / c.mean_visitors_per_calendar_day.iloc[0] * 100,
           "Gilded Ace coin-in per day": ga.values / ga.iloc[0] * 100}
    r.headline = f"Las Vegas visitation fell year-over-year in every month of H1 2025 ({signed_pct(c.visitor_yoy_ratio.min())} at worst, in {c.loc[c.visitor_yoy_ratio.idxmin(), 'month']})."
    r.kpi("Visitors (H1)", n(c.visitor_volume.sum()))
    r.kpi("Avg YoY change", signed_pct(c.visitor_yoy_ratio.mean(), 1))
    r.kpi("Convention attendance", n(c.convention_attendance.sum()))
    r.kpi("Hotel occupancy", f"{pct(c.hotel_occupancy_ratio.min(), 0)}–{pct(c.hotel_occupancy_ratio.max(), 0)}")
    r.find("Real LVCVA data: every month of H1 2025 had fewer visitors than the same month of 2024 — a soft citywide backdrop.")
    r.find(f"Peak visitation per day was {c.loc[c.mean_visitors_per_calendar_day.idxmax(), 'month']}; June was the weakest, also the month with the lowest convention attendance.")
    r.find(f"Convention attendance swings more than visitors: {n(c.convention_attendance.min())} to {n(c.convention_attendance.max())} per month.")
    r.find("Indexed to January = 100, the property's coin-in per day follows the city's visitors per day loosely; both dip in June. Figures were published after 2025 (as_of_limitation).")
    r.section("City indicators", "", [
        bar("Visitor volume", list(c.month), {"Visitors": c.visitor_volume}, fmt="int"),
        bar("Visitors vs same month 2024", list(c.month), {"YoY change": c.visitor_yoy_ratio}, fmt="pct"),
        bar("Convention attendance", list(c.month), {"Attendance": c.convention_attendance}, fmt="int"),
        line("Hotel occupancy", list(c.month), {"Occupancy": c.hotel_occupancy_ratio}, fmt="pct", mode="lines+markers"),
        bar("Airport passengers (enplaned + deplaned)", list(c.month), {"Passengers": c.airport_en_deplaned_passengers}, fmt="int"),
        line("City vs property, indexed (Jan = 100)", list(c.month), idx, fmt="num", mode="lines+markers",
             sub="One axis: both series indexed to their January value."),
    ])


def _vp_value(df):
    df = df.copy()
    df["v"] = pd.to_numeric(df.value, errors="coerce")
    return df


def b_visitor_profile_summary(r: Report):
    s = _vp_value(r.df)
    rat = s[(s.unit == "ratio") & (s.metric_label != "Percent of Total Visitors")]
    us = s[s.unit == "USD"]
    oth = s[~s.unit.isin(["ratio", "USD"])]
    charts = []
    for sec, g in rat.groupby("section"):
        g = g.sort_values("v", ascending=False)
        charts.append(hbar(f"{sec.capitalize().replace('Hh ', 'Household ')} (share of visitors)", [m[:48] for m in g.metric_label], g.v.values, fmt="pct"))
    us = us.sort_values("v", ascending=False)
    lab = s.set_index("metric_label").v
    r.headline = f"LVCVA 2025 Visitor Profile: {len(s)} published metrics for all Las Vegas visitors (real data)."
    r.kpi("Metrics", len(s))
    for k, short in [("Gambled During Visit", "Gambled during visit"),
                     ("Primary Purpose of Current Trip - Gambling", "Came primarily to gamble"),
                     ("Gambling Budget (among those who gambled)", "Gambling budget (gamblers)")]:
        if k in lab.index:
            r.kpi(short, usd(lab[k]) if "Budget" in k else pct(lab[k], 1))
    if "Gambled During Visit" in lab.index:
        r.find(f"{pct(lab['Gambled During Visit'], 0)} of visitors gamble, but only {pct(lab.get('Primary Purpose of Current Trip - Gambling'), 1)} "
               f"come primarily to gamble; gamblers average {lab.get('Average Hours Gambled per Day (if gambled)', float('nan')):.1f} hours per day.")
    r.find("This describes all Las Vegas visitors, not Gilded Ace guests — use it for context and segment sizing, not as property data.")
    for sec, g in rat.groupby("section"):
        top = g.sort_values("v", ascending=False).head(2)
        r.find(f"{sec.capitalize().replace('Hh ', 'Household ')}: " + ", ".join(f"{a} {pct(b, 0)}" for a, b in zip(top.metric_label, top.v)) + ".")
    if len(us):
        r.find("Spending (USD): " + ", ".join(f"{a} ${b:,.0f}" for a, b in zip(us.metric_label.head(4), us.v.head(4))) + ".")
    charts.append(hbar("Spending metrics (USD)", [m[:48] for m in us.metric_label], us.v.values, fmt="usd"))
    charts.append(table_block("Other metrics", oth.assign(value=oth.v.round(3))[["section", "metric_label", "value", "unit", "denominator_note"]]))
    r.section("Visitor profile", "", charts)


def b_visitor_profile_segments(r: Report):
    s = _vp_value(r.df)
    segs = list(dict.fromkeys(s.segment))
    rat = s[s.unit == "ratio"].copy()
    rat["lab"] = rat.section.str[:3] + " · " + rat.metric_label.str[:40]
    pv = rat.pivot_table(index="lab", columns="segment", values="v", aggfunc="first")[segs]
    us = s[s.unit == "USD"].copy()
    usp = us.pivot_table(index="metric_label", columns="segment", values="v", aggfunc="first")
    cmp = [c for c in ["All visitors", "Casino Guest"] if c in usp.columns]
    gam_rows = s[s.metric_label.str.contains("budget|gambl", case=False) & (s.unit == "USD")]
    r.headline = f"LVCVA 2025 Visitor Profile cross-tab: {s.metric_id.nunique()} metrics × {len(segs)} overlapping segments (real data)."
    r.kpi("Metrics", s.metric_id.nunique())
    r.kpi("Segments", len(segs))
    r.kpi("Segment groups", s.segment_group.nunique())
    r.find("Segments overlap across groups (a visitor can be Male, Millennial and a Strip guest), so never sum across segments.")
    if len(gam_rows):
        gp = gam_rows.pivot_table(index="metric_label", columns="segment", values="v", aggfunc="first")
        if {"All visitors", "Casino Guest"} <= set(gp.columns):
            row = gp.iloc[0]
            r.find(f"{gp.index[0]}: casino guests ${row['Casino Guest']:,.0f} vs all visitors ${row['All visitors']:,.0f}.")
        hi = gp.iloc[0].drop("All visitors", errors="ignore").sort_values(ascending=False)
        r.find(f"Highest {gp.index[0].lower()} by segment: " + ", ".join(f"{k} ${v:,.0f}" for k, v in hi.head(3).items()) + ".")
    r.find("Heatmap below shows every share metric by segment — rows are metrics, columns segments; look for columns that stand out from 'All visitors'.")
    charts = [heat("Share metrics by segment", segs, list(pv.index), pv.values, fmt="pct", sub="Cells are the published share for that segment.")]
    if len(cmp) == 2:
        u2 = usp[cmp].dropna().sort_values("All visitors", ascending=False)
        charts.append(bar("Spending: casino guests vs all visitors", [m[:30] for m in u2.index], {c: u2[c] for c in cmp}, fmt="usd", wide=True))
    r.section("Segments", "", charts)


def b_benchmark_public(r: Report):
    b = r.df[r.df.category_kind == "game_category"].copy()
    b = b.dropna(subset=["handle_usd"])
    cat = b.groupby("category").agg(h=("handle_usd", "sum"), a=("agr_usd", "sum"), u=("slot_units", "mean"))
    cat["hold"] = cat.a / cat.h

    def denom(c):
        m = re.search(r"([\d.]+)", c)
        v = float(m.group(1)) if m else 1e9
        return v / 100 if "cent" in c else v
    cat = cat.loc[sorted(cat.index, key=denom)]
    prop = b.groupby("property_id").agg(h=("handle_usd", "sum"), a=("agr_usd", "sum"))
    prop["hold"] = prop.a / prop.h
    prop = prop.sort_values("h", ascending=False)
    pc = b.pivot_table(index="property_id", columns="category", values="handle_usd", aggfunc="sum").reindex(prop.index)
    pc = pc[[c for c in cat.index if c in pc.columns]]
    pc = pc.div(pc.sum(axis=1), axis=0)
    r.headline = f"Real Missouri Gaming Commission slot detail: {b.property_id.nunique()} casinos × {cat.shape[0]} denomination categories × 6 months."
    r.kpi("Rows (game categories)", f"{len(b):,}", f"{(r.df.category_kind == 'adjustment').sum()} adjustment rows excluded")
    r.kpi("Handle", usd(b.handle_usd.sum()))
    r.kpi("AGR (house win)", usd(b.agr_usd.sum()))
    r.kpi("Hold", pct(b.agr_usd.sum() / b.handle_usd.sum(), 2))
    big = cat.h.idxmax()
    major = cat[cat.h / cat.h.sum() >= 0.02].sort_values("hold", ascending=False)
    r.find(f"Hold depends on the denomination group, not simply on size: among major categories (≥2% of handle) " +
           ", ".join(f"{k} {pct(v)}" for k, v in major.hold.items()) +
           ". Small high-denomination categories swing widely on little handle. Gilded Ace's 9.5% sits between the high-hold penny games and the ~6–7% nickel/quarter/dollar games.")
    r.find(f"{big} is the dominant category by handle ({pct(cat.h.max() / cat.h.sum(), 0)}).")
    r.find(f"Largest property by handle: {prop.index[0]} ({usd(prop.h.iloc[0])}); property hold ranges {pct(prop.hold.min())}–{pct(prop.hold.max())}.")
    r.find("Do not add these rows to benchmark_property_monthly — that file is the published totals of the same casinos.")
    r.section("Benchmarks", "", [
        bar("Hold by denomination", list(cat.index), {"Hold": cat.hold}, fmt="pct"),
        bar("Handle by denomination", list(cat.index), {"Handle": cat.h}, fmt="usd"),
        hbar("Handle by property", list(prop.index), prop.h.values, fmt="usd"),
        heat("Handle mix by property and denomination", list(pc.columns), list(pc.index), pc.values, fmt="pct", sub="Row shares."),
    ])


def b_benchmark_property_monthly(r: Report):
    b = r.df.copy()
    b["days"] = pd.to_datetime(b.month + "-01").dt.days_in_month
    b["win_unit_day"] = b.agr_usd / b.slot_units / b.days
    p = b.groupby("property_id").agg(h=("handle_usd", "sum"), a=("agr_usd", "sum"), u=("slot_units", "mean"),
                                     wud=("win_unit_day", "mean"))
    p["hold"] = p.a / p.h
    p = p.sort_values("wud", ascending=False)
    hm = b.pivot_table(index="property_id", columns="month", values="derived_hold_ratio").reindex(p.index)
    pdv = cached("1_prepared_views/property_day.parquet")
    ga_wud = (pdv.house_win_usd / pdv.active_machines).mean()
    r.headline = f"Published monthly slot totals for {b.property_id.nunique()} Missouri casinos; win per unit per day ranges {usd(p.wud.min())}–{usd(p.wud.max())} (Gilded Ace: {usd(ga_wud)})."
    r.kpi("Casinos", b.property_id.nunique())
    r.kpi("Handle (H1)", usd(b.handle_usd.sum()))
    r.kpi("Hold", pct(b.agr_usd.sum() / b.handle_usd.sum(), 2))
    r.kpi("Gilded Ace win / unit / day", usd(ga_wud), "for comparison")
    r.find(f"Best performer per machine: {p.index[0]} at {usd(p.wud.iloc[0])} win per unit per day; weakest {p.index[-1]} at {usd(p.wud.iloc[-1])}.")
    r.find(f"Gilded Ace's {usd(ga_wud)} per machine per day would rank {int((p.wud > ga_wud).sum()) + 1} of {len(p) + 1} against these real Missouri casinos.")
    r.find(f"Property hold is tight ({pct(p.hold.min())}–{pct(p.hold.max())}); month-to-month hold varies by under a point for most properties.")
    r.section("Property comparison", "", [
        hbar("Win per slot unit per day", list(p.index) + ["Gilded Ace (synthetic)"], list(p.wud.values) + [ga_wud], fmt="usd"),
        hbar("Hold by property", list(p.sort_values('hold', ascending=False).index), p.sort_values('hold', ascending=False).hold.values, fmt="pct"),
        heat("Monthly hold by property", list(hm.columns), list(hm.index), hm.values, fmt="pct"),
        hbar("Average slot units", list(p.sort_values('u', ascending=False).index), p.sort_values('u', ascending=False).u.values, fmt="int"),
    ])


def b_benchmark_state_monthly(r: Report):
    s = r.df.copy().sort_values("month")
    s["hold"] = s.agr_usd / s.handle_usd
    s["days"] = pd.to_datetime(s.month + "-01").dt.days_in_month
    s["wud"] = s.agr_usd / s.slot_units / s.days
    pdv = cached("1_prepared_views/property_day.parquet").copy()
    pdv["month"] = pdv.gaming_date.dt.strftime("%Y-%m")
    gm = pdv.groupby("month").agg(h=("coin_in_usd", "sum"), a=("house_win_usd", "sum"))
    ga_hold = (gm.a / gm.h).reindex(s.month)
    r.headline = f"Missouri statewide slots: {usd(s.handle_usd.sum())} handle and {usd(s.agr_usd.sum())} AGR in H1 2025 at {pct(s.agr_usd.sum() / s.handle_usd.sum(), 2)} hold."
    r.kpi("Handle", usd(s.handle_usd.sum()))
    r.kpi("AGR", usd(s.agr_usd.sum()))
    r.kpi("Hold", pct(s.agr_usd.sum() / s.handle_usd.sum(), 2))
    r.kpi("Slot units", f"{s.slot_units.mean():,.0f}", "average")
    r.find(f"March is the peak month ({usd(s.handle_usd.max())} handle); January the low ({usd(s.handle_usd.min())}) — the same seasonal shape as Gilded Ace.")
    r.find(f"State hold stays between {pct(s.hold.min(), 2)} and {pct(s.hold.max(), 2)}; Gilded Ace's monthly hold ({pct(ga_hold.min(), 2)}–{pct(ga_hold.max(), 2)}) sits right alongside.")
    r.find(f"Statewide win per unit per day: {usd(s.wud.min())}–{usd(s.wud.max())}.")
    r.section("Statewide trend", "", [
        bar("Handle and AGR by month", list(s.month), {"Handle": s.handle_usd, "AGR": s.agr_usd}, fmt="usd"),
        line("Hold: Missouri vs Gilded Ace", list(s.month), {"Missouri statewide": s.hold, "Gilded Ace": ga_hold.values}, fmt="pct", mode="lines+markers"),
        line("Win per unit per day", list(s.month), {"Missouri statewide": s.wud}, fmt="usd", mode="lines+markers"),
    ])


def b_machine_hour(r: Report):
    m = r.df
    g = m.groupby("local_hour").agg(ci=("coin_in_cents", "sum"), card=("carded_coin_in_cents", "sum"),
                                    occ=("occupied_seconds", "sum"), av=("available_seconds", "sum"),
                                    sp=("paid_spins", "sum"), hrs=("hour_start_utc", "nunique"))
    order = [(h + 6) % 24 for h in range(24)]
    g = g.reindex(order)
    g["ci_hr"] = g.ci / 100 / g.hrs
    g["occ_r"] = g.occ / g.av
    g["card"] = g.card / g.ci
    wd = pd.to_datetime(m.gaming_date).dt.strftime("%a")
    hm = m.assign(wd=wd).groupby(["wd", "local_hour"]).agg(o=("occupied_seconds", "sum"), a=("available_seconds", "sum"))
    hm = (hm.o / hm.a).unstack().reindex(WEEK)[order]
    peak, low = g.ci_hr.idxmax(), g.ci_hr.idxmin()
    labels = [f"{h}:00" for h in order]
    r.headline = f"{len(m) / 1e6:.2f}M machine-hours; coin-in peaks at {peak}:00 ({usd(g.ci_hr.max())}/hour property-wide) and bottoms at {low}:00 ({usd(g.ci_hr.min())})."
    r.kpi("Machine-hours", f"{len(m):,}")
    r.kpi("Peak hour", f"{peak}:00", f"{pct(g.occ_r.max())} seats occupied")
    r.kpi("Quietest hour", f"{low}:00", f"{pct(g.occ_r.min())} seats occupied")
    r.kpi("Peak / trough coin-in", f"{g.ci_hr.max() / g.ci_hr.min():.1f}×")
    r.find(f"Play follows a strong daily cycle: occupancy runs from {pct(g.occ_r.min())} at {low}:00 to {pct(g.occ_r.max())} at {peak}:00.")
    r.find(f"Carded share varies by hour ({pct(g.card.min())}–{pct(g.card.max())}): late-night play is {'more' if g.card[low] > g.card[peak] else 'less'} carded than the evening peak.")
    r.find("Friday and Saturday evenings are the busiest cells in the week; weekday early mornings the emptiest — natural windows for maintenance and moves.")
    r.find("Sums to machine_day; the 23-hour DST gaming day (Mar 8) has one fewer hour per machine.")
    r.section("Daily cycle", "Gaming-day order, 06:00 → 05:00 local.", [
        bar("Coin-in per hour (property-wide, average)", labels, {"Coin-in": g.ci_hr}, fmt="usd"),
        line("Seat occupancy and carded share by hour", labels, {"Occupancy": g.occ_r, "Carded share of coin-in": g.card}, fmt="pct", mode="lines+markers"),
        heat("Seat occupancy by weekday and hour", labels, WEEK, hm.values, fmt="pct"),
    ])


def b_security_incidents(r: Report):
    s = r.df.copy()
    zn = zone_names()
    s["zone"] = s.zone_id.map(zn)
    s["lag"] = (s.reported_at_utc - s.occurred_at_utc).dt.total_seconds() / 60
    s["week"] = (s.occurred_at_local - pd.Timedelta(hours=6)).dt.to_period("W-SUN").dt.start_time
    cat = s.category.value_counts()
    wk = full_weeks(s.groupby(["week", "category"]).size().unstack(fill_value=0)[cat.index])
    zc = s.groupby("zone").size().sort_values(ascending=False)
    hr = s.local_hour.value_counts().reindex(range(24), fill_value=0)
    sev = pd.crosstab(s.category, s.severity).reindex(cat.index)
    src = pd.crosstab(s.category, s.report_source).reindex(cat.index)
    lagc = s.groupby("category").lag.median().reindex(cat.index)
    r.headline = f"{len(s):,} reported incidents ({len(s) / 181:.0f} per day); disputes, lost property and intoxication make up {pct(cat.head(3).sum() / len(s), 0)}."
    r.kpi("Incidents", f"{len(s):,}", f"{len(s) / 181:.1f} per day")
    r.kpi("High severity (3)", pct((s.severity == 3).mean()))
    r.kpi("Median report lag", f"{s.lag.median():.0f} min")
    r.kpi("Machine-linked", f"{s.machine_id.notna().sum()}")
    r.find(f"Most common: " + ", ".join(f"{k.replace('_', ' ')} {v:,}" for k, v in cat.head(4).items()) + ".")
    r.find(f"{zc.index[0]} has the most incidents ({zc.iloc[0]:,}) — alcohol nearby; {zc.index[-1]} the fewest ({zc.iloc[-1]}).")
    r.find(f"Incidents peak late in the evening ({hr.idxmax()}:00), tracking crowd and alcohol, not machine play.")
    r.find(f"Reports arrive a median {s.lag.median():.0f} minutes after occurrence; slowest category: {lagc.idxmax().replace('_', ' ')} ({lagc.max():.0f} min).")
    r.find("These are reports, not verdicts — machine-tampering and counterfeit reports are leads only.")
    r.section("Volume", "", [
        bar("Incidents per week by category", ds(wk.index), {k: wk[k] for k in wk.columns}, fmt="int", stacked=True,
            sub="Six categories; full Mon–Sun weeks only.", wide=True),
        bar("Incidents by local hour", list(range(24)), {"Incidents": hr.values}, fmt="int"),
        hbar("Incidents by zone", list(zc.index), zc.values, fmt="int"),
    ])
    r.section("Severity and reporting", "", [
        bar("Severity by category", [c.replace("_", " ") for c in sev.index], {f"Severity {k}": sev[k] for k in sev.columns}, fmt="int", stacked=True),
        bar("Report source by category", [c.replace("_", " ") for c in src.index], {k.replace("_", " "): src[k] for k in src.columns}, fmt="int", stacked=True),
        hist("Report lag (minutes)", s.lag, fmt="num"),
    ])


def b_shift_roster(r: Report):
    s = r.df.copy()
    s["short"] = (s.planned_headcount - s.actual_headcount).clip(lower=0)
    s["month"] = s.gaming_date.dt.strftime("%Y-%m")
    role = s.groupby("role").agg(planned=("planned_headcount", "sum"), actual=("actual_headcount", "sum"),
                                 short=("short", "sum"), n=("assignment_id", "size"))
    role["fill"] = role.actual / role.planned
    role = role.sort_values("fill")
    sm = s.groupby(["month", "role"]).short.sum().unstack(fill_value=0)
    tech = s[s.role == "slot_tech"].groupby(["gaming_date", "shift"]).actual_headcount.sum().unstack().reindex(columns=["day", "swing", "grave"])
    tech_d = tech.sum(axis=1)
    pdv = cached("1_prepared_views/property_day.parquet").set_index("gaming_date")
    sh = s.groupby("shift").agg(p=("planned_headcount", "sum"), a=("actual_headcount", "sum"))
    sh["fill"] = sh.a / sh.p
    r.headline = f"{len(s):,} staff assignments; {pct(s.actual_headcount.sum() / s.planned_headcount.sum(), 1)} of planned headcount showed up, with {int(s.short.sum())} person-shifts missed."
    r.kpi("Assignments", f"{len(s):,}")
    r.kpi("Fill rate", pct(s.actual_headcount.sum() / s.planned_headcount.sum(), 1))
    r.kpi("Missed person-shifts", int(s.short.sum()))
    r.kpi("Slot techs per day", f"{tech_d.mean():.1f}", f"range {tech_d.min():.0f}–{tech_d.max():.0f}")
    r.find(f"Lowest fill rate: {role.index[0].replace('_', ' ')} ({pct(role.fill.iloc[0], 1)}); highest {role.index[-1].replace('_', ' ')} ({pct(role.fill.iloc[-1], 1)}).")
    r.find(f"Slot-tech coverage drives repair capacity: daily actual techs vary {tech_d.min():.0f}–{tech_d.max():.0f}, matching the tech_labor_cost tiers in property_day.")
    r.find(f"By shift, fill rate is " + ", ".join(f"{k} {pct(v, 1)}" for k, v in sh.fill.items()) + ".")
    r.find("Zone is blank for floor-wide roles (slot techs); others are posted to a zone.")
    r.section("Staffing", "", [
        bar("Planned vs actual headcount by role", [k.replace("_", " ") for k in role.index], {"Planned": role.planned, "Actual": role.actual}, fmt="int"),
        bar("Missed person-shifts by month and role", list(sm.index), {k.replace("_", " "): sm[k] for k in sm.columns}, fmt="int", stacked=True),
        line("Slot techs on shift per day", ds(tech_d.index), {"Actual slot techs": tech_d.values}, fmt="int"),
        scatter("Slot techs vs faults opened per day", [pts("Day", tech_d.values, pdv.faults_opened.reindex(tech_d.index).values, ds(tech_d.index))],
                fx="int", fy="int", xtitle="Slot techs (actual)", ytitle="Faults opened"),
    ])


def b_visitor_profile_monthly(r: Report):
    v = r.df.copy().sort_values("month")
    charts = []
    fmt_of = {"share": "pct", "usd": "usd", "minutes": "num"}
    for mt, g in v.groupby("survey_metric"):
        charts.append(line(mt.replace("_", " ").capitalize(), list(g.month), {"Estimate": g.estimate}, fmt=fmt_of.get(g.unit.iloc[0], "num"),
                           mode="lines+markers", err={"Estimate": g.standard_error * 1.96},
                           sub=f"±95% interval (1.96 × SE); n ≈ {int(g.sample_size.mean())} per month."))
    first, last = v.month.min(), v.month.max()
    piv = v.pivot_table(index="survey_metric", columns="month", values="estimate")
    r.headline = f"Fictional exit-intercept survey of all guests (carded or not): {v.survey_metric.nunique()} metrics, {v.month.nunique()} months, ~{int(v.sample_size.mean())} respondents per month."
    r.kpi("Metrics", v.survey_metric.nunique())
    r.kpi("Months", v.month.nunique(), f"{first} → {last}")
    r.kpi("Avg sample size", f"{v.sample_size.mean():.0f}")
    for mt in ["used_loyalty_card", "gambled_this_visit", "lives_locally"]:
        if mt in piv.index:
            r.find(f"{mt.replace('_', ' ').capitalize()}: {pct(piv.loc[mt].mean(), 0)} on average ({pct(piv.loc[mt].min(), 0)}–{pct(piv.loc[mt].max(), 0)} by month).")
    if "used_loyalty_card" in piv.index:
        r.find(f"Only ~{pct(piv.loc['used_loyalty_card'].mean(), 0)} of guests use a card, which is why tracked tables (players, sessions) cover only part of the floor.")
    r.find("Month-to-month changes are mostly within the sampling error bars; treat single-month moves with caution.")
    r.section("Survey metrics by month", "", charts)


BUILDERS = {
    "property_day": b_property_day, "prepared_daily_view": b_prepared_daily_view, "player_period": b_player_period,
    "action_catalog": b_action_catalog, "calendar_day": b_calendar_day, "cost_rules": b_cost_rules,
    "floor_locations": b_floor_locations, "floor_walkways": b_floor_walkways, "game_math": b_game_math,
    "machine_day": b_machine_day, "machines": b_machines, "operations": b_operations, "placements": b_placements,
    "fnb_transactions": b_fnb_transactions, "loyalty_ledger": b_loyalty_ledger, "players": b_players,
    "sessions": b_sessions, "trips": b_trips, "events": b_events, "zone_traffic_hourly": b_zone_traffic_hourly,
    "weather_daily": b_weather_daily, "city_visitation_monthly": b_city_visitation_monthly,
    "visitor_profile_summary": b_visitor_profile_summary, "visitor_profile_segments": b_visitor_profile_segments,
    "benchmark_public": b_benchmark_public, "benchmark_property_monthly": b_benchmark_property_monthly,
    "benchmark_state_monthly": b_benchmark_state_monthly, "machine_hour": b_machine_hour,
    "security_incidents": b_security_incidents, "shift_roster": b_shift_roster,
    "visitor_profile_monthly": b_visitor_profile_monthly,
}

# ============================================================================= page template

CSS = r"""
:root{color-scheme:light;--bg:#f6f5f2;--surface-1:#fcfcfb;--surface-2:#ffffff;--border:#e4e2dc;--grid:#ecebe6;--axis:#c9c7bf;
--text-1:#0b0b0b;--text-2:#52514e;--text-3:#7a7974;--accent:#2a78d6;--chip:#eef4fc;--chip-real:#e9f6ef;--chip-real-t:#0b6b44;
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--s5:#e87ba4;--s6:#008300;--s7:#6250d6;--s8:#e34948;}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])){color-scheme:dark;--bg:#121211;--surface-1:#1a1a19;--surface-2:#20201f;--border:#30302d;--grid:#2a2a28;--axis:#45453f;
--text-1:#f0efec;--text-2:#c3c2b7;--text-3:#94938a;--accent:#3987e5;--chip:#1b2a3d;--chip-real:#14291f;--chip-real-t:#6fd3a3;
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--s5:#d55181;--s6:#008300;--s7:#9085e9;--s8:#e66767;}}
:root[data-theme="dark"]{color-scheme:dark;--bg:#121211;--surface-1:#1a1a19;--surface-2:#20201f;--border:#30302d;--grid:#2a2a28;--axis:#45453f;
--text-1:#f0efec;--text-2:#c3c2b7;--text-3:#94938a;--accent:#3987e5;--chip:#1b2a3d;--chip-real:#14291f;--chip-real-t:#6fd3a3;
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--s5:#d55181;--s6:#008300;--s7:#9085e9;--s8:#e66767;}
*{box-sizing:border-box}html,body{margin:0}
body{background:var(--bg);color:var(--text-1);font:15px/1.55 Inter,system-ui,-apple-system,"Segoe UI",sans-serif;-webkit-font-smoothing:antialiased}
a{color:var(--accent)}code{font:12.5px ui-monospace,SFMono-Regular,Consolas,monospace}
.wrap{max-width:1200px;margin:0 auto;padding:24px 16px 64px}
header.top{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:8px}
.crumb{font-size:13px;color:var(--text-3)}.crumb a{color:var(--text-2);text-decoration:none}.crumb a:hover{text-decoration:underline}
button.theme{background:var(--surface-2);border:1px solid var(--border);color:var(--text-2);border-radius:8px;padding:6px 10px;font:inherit;font-size:13px;cursor:pointer}
h1{font-size:30px;line-height:1.2;margin:8px 0 6px;letter-spacing:-.01em}h1 code{font-size:26px;font-family:inherit;font-weight:700}
h2{font-size:19px;margin:40px 0 4px}h3{font-size:15px;margin:0}
.lede{font-size:17px;color:var(--text-2);max-width:880px;margin:0 0 14px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 22px}.chip{font-size:12.5px;padding:3px 9px;border-radius:999px;background:var(--chip);color:var(--text-2)}
.chip.real{background:var(--chip-real);color:var(--chip-real-t);font-weight:600}
.kpis{display:grid;grid-template-columns:repeat(auto-fill,minmax(176px,1fr));gap:12px;margin:0 0 8px}
.kpi{background:var(--surface-1);border:1px solid var(--border);border-radius:12px;padding:14px 16px}
.kpi .l{font-size:12.5px;color:var(--text-3)}.kpi .v{font-size:24px;font-weight:650;margin-top:2px;font-variant-numeric:tabular-nums;letter-spacing:-.01em}.kpi .s{font-size:12.5px;color:var(--text-2);margin-top:2px}
.findings{background:var(--surface-1);border:1px solid var(--border);border-radius:12px;padding:6px 22px 6px 20px;margin-top:20px}
.findings li{margin:10px 0;color:var(--text-1)}.findings h2{margin:14px 0 0;font-size:16px}
.intro{color:var(--text-2);margin:0 0 12px;font-size:14px}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.grid.small{grid-template-columns:repeat(3,minmax(0,1fr))}
.card{background:var(--surface-1);border:1px solid var(--border);border-radius:12px;padding:14px 16px 10px;min-width:0}
.card.wide{grid-column:1/-1}.card .sub{font-size:12.5px;color:var(--text-3);margin:2px 0 4px;min-height:1em}
.plot{height:300px;width:100%}.card.wide .plot{height:380px}.card.tall .plot{height:520px}.small .plot{height:190px}
.small .card h3{font-size:13px;font-family:ui-monospace,Consolas,monospace;font-weight:600}
details.data{margin-top:4px;font-size:12.5px}details.data summary{cursor:pointer;color:var(--text-3)}
.tbl-wrap{overflow:auto;max-height:420px;border:1px solid var(--border);border-radius:8px;margin-top:6px}
table.data{border-collapse:collapse;width:100%;font-size:12.5px;font-variant-numeric:tabular-nums}
table.data th{position:sticky;top:0;background:var(--surface-2);text-align:left;font-weight:600;color:var(--text-2);padding:7px 10px;border-bottom:1px solid var(--border);white-space:nowrap}
table.data td{padding:6px 10px;border-bottom:1px solid var(--grid);vertical-align:top}table.data td.num{text-align:right;white-space:nowrap}
table.profile td.sum{color:var(--text-2);min-width:260px}.null{color:var(--text-3);font-style:italic}
.foot{margin-top:48px;font-size:12.5px;color:var(--text-3)}
.idx-group{margin-top:28px}.idx{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}
.idx a.card{display:block;text-decoration:none;color:inherit;transition:border-color .15s}.idx a.card:hover{border-color:var(--accent)}
.idx .meta{font-size:12.5px;color:var(--text-3);margin:2px 0 6px}.idx .hl{font-size:13.5px;color:var(--text-2)}
@media (max-width:820px){.grid,.grid.small{grid-template-columns:minmax(0,1fr)}h1{font-size:24px}.kpi .v{font-size:20px}}
"""

JS = r"""
const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const SL=()=>[1,2,3,4,5,6,7,8].map(i=>css('--s'+i));
const TF={usd:'$~s',pct:'.0%',int:'~s',num:'~g'};
const HF={usd:'$,.0f',pct:'.1%',int:',.0f',num:',.2f'};
function hf(f,v){if(f==='usd'&&v!==undefined&&Math.abs(v)<100)return '$,.2f';return HF[f]||',.2f'}
function fmtV(v,f){if(v===null||v===undefined||Number.isNaN(v))return '–';if(typeof v==='string')return v;
 if(f==='usd'){const a=Math.abs(v);return (v<0?'-':'')+'$'+(a>=1e9?(a/1e9).toFixed(2)+'B':a>=1e6?(a/1e6).toFixed(2)+'M':a>=1e4?(a/1e3).toFixed(1)+'K':a.toFixed(2))}
 if(f==='pct')return (v*100).toFixed(2)+'%';if(f==='int')return Math.round(v).toLocaleString();return (+v).toLocaleString(undefined,{maximumFractionDigits:3})}
function base(){return{font:{family:'Inter,system-ui,Segoe UI,sans-serif',size:12,color:css('--text-2')},paper_bgcolor:'rgba(0,0,0,0)',plot_bgcolor:'rgba(0,0,0,0)',
 margin:{l:58,r:14,t:6,b:42},showlegend:false,legend:{orientation:'h',x:0,y:1.0,yanchor:'bottom',font:{size:12,color:css('--text-2')}},
 hoverlabel:{bgcolor:css('--surface-2'),bordercolor:css('--border'),font:{color:css('--text-1'),size:12}},
 xaxis:{gridcolor:css('--grid'),linecolor:css('--axis'),tickcolor:css('--axis'),zeroline:false,showgrid:false,automargin:true},
 yaxis:{gridcolor:css('--grid'),linecolor:css('--axis'),zerolinecolor:css('--axis'),automargin:true},bargap:0.18,barcornerradius:4}}
function ax(a,f,vals){if(!f)return a;a.tickformat=TF[f];a.hoverformat=HF[f];
 if((f==='int'||f==='num')&&vals){const m=Math.max(...vals.flat().filter(v=>typeof v==='number').map(Math.abs));if(m>0&&m<1000){a.tickformat=f==='int'?',d':',~g';if(f==='int'&&m<8)a.dtick=1}}return a}
const TR=s=>{s=String(s);return s.length>30?s.slice(0,29)+'…':s};
function catAxis(a,labels){a.tickmode='array';a.tickvals=labels;a.ticktext=labels.map(TR)}
function render(el,s){const L=base(),P=SL(),tr=[];const sm=!!s.small;
 if(sm){L.margin={l:44,r:8,t:4,b:30};L.font.size=11}
 if(s.kind==='line'){s.series.forEach((se,i)=>{tr.push({type:'scatter',mode:s.mode||'lines',name:se.name,x:s.x,y:se.y,line:{width:2,color:P[i%8],shape:'linear'},marker:{size:8,color:P[i%8],line:{width:2,color:css('--surface-1')}},
   error_y:se.err?{type:'data',array:se.err,visible:true,color:P[i%8],thickness:1.5,width:4}:undefined,connectgaps:false,hovertemplate:'%{y:'+hf(s.fmt)+'}<extra>'+se.name+'</extra>'})});
  if(s.series.length>1&&s.series[1].name.startsWith('7-day')){tr[0].line.color=css('--axis');tr[0].line.width=1.5;tr[0].marker.color=css('--axis');tr[1].line.color=P[0]}
  L.hovermode='x unified';ax(L.yaxis,s.fmt,s.series.map(se=>se.y));if(s.xfmt)ax(L.xaxis,s.xfmt);L.showlegend=s.series.length>1}
 else if(s.kind==='bar'){const h=s.horizontal;const n=s.series.length;
  s.series.forEach((se,i)=>{const t={type:'bar',name:se.name,orientation:h?'h':'v',marker:{color:n===1&&!s.stacked?P[0]:P[i%8],line:{width:s.stacked?1:0,color:css('--surface-1')}},
   hovertemplate:(h?'%{y}: %{x:'+hf(s.fmt)+'}':'%{x}: %{y:'+hf(s.fmt)+'}')+'<extra>'+(n>1?se.name:'')+'</extra>'};
   if(h){t.x=se.y;t.y=s.x}else{t.x=s.x;t.y=se.y}
   if(s.hist){t.hovertemplate='%{x:'+(HF[s.xfmt]||',.2f')+'}: %{y:,} rows<extra></extra>';if(s.width)t.width=s.width}
   tr.push(t)});
  L.barmode=s.stacked?'stack':'group';L.showlegend=n>1;
  const vals=s.series.map(se=>se.y);
  if(h){L.yaxis.autorange='reversed';L.yaxis.type='category';catAxis(L.yaxis,s.x);ax(L.xaxis,s.fmt,vals);L.xaxis.showgrid=true;L.yaxis.showgrid=false;L.hovermode='closest';L.margin.l=20}
  else{ax(L.yaxis,s.fmt,vals);if(s.xfmt){ax(L.xaxis,s.xfmt)}if(s.hist){L.bargap=0.04;if(s.logx){L.xaxis.type='log';if(s.xfmt==='usd')L.xaxis.tickformat='$,~g';else L.xaxis.tickformat=',~g'}}
   const allnum=s.x.every(v=>typeof v==='number');if(!allnum&&!/^\d{4}-\d\d-\d\d/.test(String(s.x[0])))L.xaxis.type='category';L.hovermode='closest'}
  if(s.stacked){L.hovermode='x unified';tr.forEach(t=>t.hovertemplate=(h?'%{x:':'%{y:')+hf(s.fmt)+'}<extra>'+t.name+'</extra>')}}
 else if(s.kind==='heat'){const dark=css('--bg').toLowerCase()<'#5';const seq=dark?[[0,'#162c4a'],[.5,'#3987e5'],[1,'#cde2fb']]:[[0,'#e9f1fb'],[.5,'#5598e7'],[1,'#0d366b']];
  tr.push({type:'heatmap',x:s.x,y:s.y,z:s.z,colorscale:seq,xgap:2,ygap:2,hoverongaps:false,colorbar:{thickness:10,outlinewidth:0,tickformat:TF[s.fmt],tickfont:{color:css('--text-2')}},
   hovertemplate:'%{y} · %{x}: %{z:'+hf(s.fmt)+'}<extra></extra>'});L.yaxis.autorange='reversed';L.yaxis.type='category';L.xaxis.type='category';catAxis(L.yaxis,s.y);L.margin.l=20;
  L.xaxis.tickangle=s.x.length>12?-45:0;L.yaxis.showgrid=false}
 else if(s.kind==='scatter'){s.series.forEach((se,i)=>{const c=P[(se.slot!==null&&se.slot!==undefined?se.slot:i)%8];
   tr.push({type:'scattergl'.slice(0,se.x.length>2000?9:7),mode:se.mode,name:se.name,x:se.x,y:se.y,text:se.text,textposition:'top center',textfont:{size:11,color:css('--text-2')},
    line:{width:2,color:c},marker:{size:se.size||8,color:c,opacity:se.mode==='markers'?.75:1,line:{width:1,color:css('--surface-1')}},
    hovertemplate:(se.text?'<b>%{text}</b><br>':'')+'%{x:'+hf(s.fx)+'}, %{y:'+hf(s.fy)+'}<extra>'+se.name+'</extra>'})});
  ax(L.xaxis,s.fx);ax(L.yaxis,s.fy);L.xaxis.showgrid=true;L.hovermode='closest';L.showlegend=s.series.length>1;
  if(s.xtitle)L.xaxis.title={text:s.xtitle,font:{size:12,color:css('--text-3')}};if(s.ytitle)L.yaxis.title={text:s.ytitle,font:{size:12,color:css('--text-3')}};
  if(s.logx)L.xaxis.type='log';if(s.logy)L.yaxis.type='log';if(s.equal){L.yaxis.scaleanchor='x';L.yaxis.scaleratio=1}}
 else if(s.kind==='gantt'){const ms=s.start.map((d,i)=>new Date(s.end[i])-new Date(d));
  tr.push({type:'bar',orientation:'h',y:s.y,x:ms,base:s.start,marker:{color:P[0]},hovertemplate:'%{y}<br>%{base|%b %d} → %{customdata}<extra></extra>',customdata:s.end.map(e=>{const d=new Date(e);d.setDate(d.getDate()-1);return d.toLocaleDateString(undefined,{month:'short',day:'numeric',timeZone:'UTC'})})});
  L.xaxis.type='date';L.xaxis.range=['2025-01-01','2025-07-01'];L.xaxis.showgrid=true;L.yaxis.autorange='reversed';catAxis(L.yaxis,s.y);L.margin.l=20;L.hovermode='closest'}
 if(s.ytitle&&s.kind!=='scatter')L.yaxis.title={text:s.ytitle,font:{size:12,color:css('--text-3')}};
 Plotly.react(el,tr,L,{displayModeBar:false,responsive:true});}
function dataTable(s){const esc=t=>String(t).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));let h='',rows=[];
 if(s.kind==='line'||s.kind==='bar'){h='<th>'+(s.hist?'bin':'x')+'</th>'+s.series.map(se=>'<th>'+esc(se.name)+'</th>').join('');
  rows=s.x.map((x,i)=>'<tr><td>'+esc(typeof x==='number'?fmtV(x,s.xfmt||'num'):x)+'</td>'+s.series.map(se=>'<td class="num">'+fmtV(se.y[i],s.fmt)+'</td>').join('')+'</tr>')}
 else if(s.kind==='heat'){h='<th></th>'+s.x.map(x=>'<th>'+esc(x)+'</th>').join('');rows=s.y.map((y,i)=>'<tr><td>'+esc(y)+'</td>'+s.z[i].map(v=>'<td class="num">'+fmtV(v,s.fmt)+'</td>').join('')+'</tr>')}
 else if(s.kind==='scatter'){h='<th>series</th><th>label</th><th>x</th><th>y</th>';s.series.forEach(se=>se.x.forEach((x,i)=>{if(x!==null&&rows.length<400)rows.push('<tr><td>'+esc(se.name)+'</td><td>'+esc(se.text?se.text[i]||'':'')+'</td><td class="num">'+fmtV(x,s.fx)+'</td><td class="num">'+fmtV(se.y[i],s.fy)+'</td></tr>')}))}
 else if(s.kind==='gantt'){h='<th>event</th><th>start</th><th>end (excl.)</th>';rows=s.y.map((y,i)=>'<tr><td>'+esc(y)+'</td><td>'+s.start[i]+'</td><td>'+s.end[i]+'</td></tr>')}
 return '<div class="tbl-wrap"><table class="data"><thead><tr>'+h+'</tr></thead><tbody>'+rows.slice(0,400).join('')+'</tbody></table></div>'}
const drawn=new Set();
function draw(el){const s=SPECS[+el.dataset.i];render(el,s);drawn.add(el)}
function boot(){document.querySelectorAll('details.data').forEach(d=>d.addEventListener('toggle',()=>{if(d.open&&!d.dataset.done){d.insertAdjacentHTML('beforeend',dataTable(SPECS[+d.dataset.i]));d.dataset.done=1}},{once:false}));
 const io=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting&&!drawn.has(e.target)){draw(e.target);io.unobserve(e.target)}}),{rootMargin:'400px'});
 document.querySelectorAll('.plot').forEach(el=>io.observe(el));
 const redraw=()=>drawn.forEach(el=>render(el,SPECS[+el.dataset.i]));
 window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change',redraw);
 const b=document.querySelector('button.theme');if(b){const st=()=>{try{return localStorage.getItem('dr-theme')}catch(e){return null}};
  const apply=t=>{if(t)document.documentElement.dataset.theme=t;else delete document.documentElement.dataset.theme;redraw()};apply(st());
  b.addEventListener('click',()=>{const cur=document.documentElement.dataset.theme||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');const nx=cur==='dark'?'light':'dark';try{localStorage.setItem('dr-theme',nx)}catch(e){};apply(nx)})}}
if(typeof Plotly==='undefined'){document.addEventListener('DOMContentLoaded',()=>document.querySelectorAll('.plot').forEach(p=>p.textContent='Charts need an internet connection to load Plotly; open "Show data" for the numbers.'))}
else document.addEventListener('DOMContentLoaded',boot);
"""

PLOTLY = "https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.35.2/plotly.min.js"


def page(title, desc, body, specs):
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(desc)}">
<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>{CSS}</style>
<script>try{{const t=localStorage.getItem('dr-theme');if(t)document.documentElement.dataset.theme=t}}catch(e){{}}</script>
<script src="{PLOTLY}"></script>
</head><body><div class="wrap">{body}</div>
<script>const SPECS={json.dumps(clean(specs), separators=(',', ':'))};</script>
<script>{JS}</script></body></html>"""


def card_html(spec, i):
    if spec["kind"] == "table":
        return f'<div class="card wide"><h3>{esc(spec["title"])}</h3><div class="sub">{esc(spec.get("sub", ""))}</div>{spec["html"]}</div>'
    cls = "card"
    if spec.get("wide") or (spec["kind"] == "line" and len(spec.get("x", [])) > 60 and not spec.get("small")):
        cls += " wide"
    if spec["kind"] == "heat" and len(spec.get("y", [])) > 14:
        cls += " wide tall"
    if spec["kind"] == "scatter" and spec.get("equal"):
        cls += " tall"
    if spec["kind"] == "bar" and spec.get("horizontal") and len(spec.get("x", [])) > 12 and not spec.get("small"):
        cls += " tall"
    return (f'<div class="{cls}"><h3>{esc(spec["title"])}</h3><div class="sub">{esc(spec.get("sub", ""))}</div>'
            f'<div class="plot" data-i="{i}" role="img" aria-label="{esc(spec["title"])}"></div>'
            f'<details class="data" data-i="{i}"><summary>Show data</summary></details></div>')


def render_report(r: Report, files):
    specs, parts = [], []
    meta = DICT.get(r.key, {})
    df = r.df
    rows_key = meta.get("rows_key", "")
    key = rows_key.split("Key:")[-1].strip() if "Key:" in rows_key else ""
    chips = [f'<span class="chip">{esc(r.folder)}/</span>', f'<span class="chip">{len(df):,} rows × {df.shape[1]} columns</span>']
    if key:
        chips.append(f'<span class="chip">key: {esc(key)}</span>')
    chips.append(f'<span class="chip real">Real public data</span>' if r.real else '<span class="chip">Synthetic (fictional casino)</span>')
    chips += [f'<span class="chip">{esc(f)}</span>' for f in files]
    parts.append(f'<header class="top"><div class="crumb"><a href="index.html">Dashboard Royale data reports</a> / {esc(r.folder)}</div>'
                 f'<button class="theme" type="button" aria-label="Toggle light or dark theme">◐ Theme</button></header>')
    parts.append(f'<h1><code>{esc(r.key)}</code></h1>')
    parts.append(f'<p class="lede">{esc(r.headline)}</p>')
    if meta.get("desc"):
        parts.append(f'<p class="intro">{esc(meta["desc"])}</p>')
    parts.append('<div class="chips">' + "".join(chips) + "</div>")
    if r.kpis:
        parts.append('<div class="kpis">' + "".join(
            f'<div class="kpi"><div class="l">{esc(a)}</div><div class="v">{esc(b)}</div><div class="s">{esc(c)}</div></div>'
            for a, b, c in r.kpis) + "</div>")
    if r.findings:
        parts.append('<section class="findings"><h2>Key findings</h2><ul>' + "".join(f"<li>{esc(t)}</li>" for t in r.findings) + "</ul></section>")
    for title, intro, charts in r.sections:
        parts.append(f"<h2>{esc(title)}</h2>")
        if intro:
            parts.append(f'<p class="intro">{esc(intro)}</p>')
        cards = []
        for c in charts:
            if c["kind"] != "table":
                specs.append(c)
                cards.append(card_html(c, len(specs) - 1))
            else:
                cards.append(card_html(c, -1))
        parts.append('<div class="grid">' + "".join(cards) + "</div>")
    prof, pcharts = column_profile(r.key, df)
    parts.append("<h2>Column profile</h2><p class='intro'>Every column with its documented meaning, missing share, distinct values and summary.</p>" + prof)
    if pcharts:
        parts.append("<h2>Column distributions</h2><p class='intro'>One small chart per non-identifier column. Numeric columns are histograms (extreme 1% trimmed); text columns show the most common values.</p>")
        cards = []
        for c in pcharts:
            specs.append(c)
            cards.append(card_html(c, len(specs) - 1))
        parts.append('<div class="grid small">' + "".join(cards) + "</div>")
    sample = df.head(10)
    parts.append(f"<h2>Sample rows</h2><p class='intro'>First {len(sample)} rows as stored.</p>" + df_html(sample, {}))
    parts.append('<p class="foot">Generated by <code>scripts/build_reports.py</code> from the parquet file. '
                 'Charts load Plotly from jsDelivr; every chart has a “Show data” table.</p>')
    return page(f"{r.key} report", r.headline, "".join(parts), specs)


def render_index(entries):
    groups = {}
    for e in entries:
        groups.setdefault(e["folder"], []).append(e)
    body = ['<header class="top"><div class="crumb">Dashboard Royale · The Gilded Ace</div><button class="theme" type="button">◐ Theme</button></header>',
            "<h1>Data reports</h1>",
            '<p class="lede">One report per table in <code>data/</code>: what each table holds, the trends inside it, and a profile of every column. '
            'Each table ships as both .parquet and .csv.gz with identical rows; the reports read the parquet.</p>']
    total = sum(e["rows"] for e in entries)
    body.append('<div class="kpis">' + "".join(
        f'<div class="kpi"><div class="l">{a}</div><div class="v">{b}</div><div class="s">{c}</div></div>' for a, b, c in [
            ("Tables", len(entries), "31 parquet + 31 csv.gz"), ("Rows", f"{total:,}", "all tables"),
            ("Window", "Jan 1 – Jun 30 2025", "181 gaming days"), ("Real-data tables", sum(e['real'] for e in entries), "4_context/real_sources")]) + "</div>")
    for folder, es in groups.items():
        body.append(f'<section class="idx-group"><h2>{esc(folder)}/</h2><div class="idx">')
        for e in es:
            body.append(f'<a class="card" href="{e["key"]}.html"><h3><code>{esc(e["key"])}</code></h3>'
                        f'<div class="meta">{e["rows"]:,} rows · {e["cols"]} columns{" · real data" if e["real"] else ""}</div>'
                        f'<div class="hl">{esc(e["headline"])}</div></a>')
        body.append("</div></section>")
    body.append('<p class="foot">Generated by <code>scripts/build_reports.py</code>.</p>')
    return page("Dashboard Royale reports", "Index of per-table data reports", "".join(body), [])


def main():
    OUT.mkdir(exist_ok=True)
    entries = []
    for p in sorted(DATA.rglob("*.parquet")):
        key = p.stem
        folder = p.parent.relative_to(DATA).as_posix()
        real = "real_sources" in folder
        df = cached(p.relative_to(DATA).as_posix())
        r = Report(key, folder, df, real)
        BUILDERS[key](r)
        files = [p.name, p.with_suffix("").name + ".csv.gz"]
        (OUT / f"{key}.html").write_text(render_report(r, files), encoding="utf-8")
        entries.append(dict(key=key, folder=folder, rows=len(df), cols=df.shape[1], real=real, headline=r.headline))
        print(f"  {folder}/{key}: {len(r.sections)} sections, {len(r.findings)} findings")
    order = ["1_prepared_views", "2_machine_decision", "3_guests", "4_context", "4_context/real_sources", "5_optional"]
    entries.sort(key=lambda e: (order.index(e["folder"]) if e["folder"] in order else 99, e["key"]))
    (OUT / "index.html").write_text(render_index(entries), encoding="utf-8")
    print(f"wrote {len(entries) + 1} files to {OUT}")


if __name__ == "__main__":
    main()
