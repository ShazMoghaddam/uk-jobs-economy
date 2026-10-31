"""Draw every chart and write the findings report from the latest data.

Run from the repository root after data/fetch.py:

    python findings/build.py

Charts go into charts/ as SVG files, made with bezel-charts (https://pypi.org/project/bezel-charts/).
The report is written to findings/README.md, with every number worked out from the data, so it
stays true when ONS publishes new figures. Nothing in the report is typed in by hand.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np
import pandas as pd

import bezel_charts as bc

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CHARTS = ROOT / "charts"
REPORT = ROOT / "findings" / "README.md"

THEME = {"theme": "light"}
WIDE = 760
PRE_PANDEMIC = "2020-01"  # LFS figures for December 2019 to February 2020


# Loading -------------------------------------------------------------------------------------

def load() -> tuple[pd.DataFrame, pd.Series, dict]:
    lm = pd.read_csv(DATA / "labour_market.csv", parse_dates=["date"]).set_index("date")
    pay = pd.read_csv(DATA / "payrolled_employees.csv", parse_dates=["date"]).set_index("date")["payrolled_employees"]
    sources = json.loads((DATA / "sources.json").read_text(encoding="utf-8"))
    return lm, pay, sources


def latest(series: pd.Series) -> tuple[pd.Timestamp, float]:
    s = series.dropna()
    return s.index[-1], float(s.iloc[-1])


def at(series: pd.Series, when: str) -> float:
    return float(series.dropna().loc[when].iloc[0])


# Words for dates and changes --------------------------------------------------------------------

def mon(t: pd.Timestamp) -> str:
    return t.strftime("%b %Y")


def window(t: pd.Timestamp, centred: bool = True) -> str:
    """The three months behind an ONS figure: LFS figures are centred, pay figures end on the month."""
    start = t - pd.DateOffset(months=1 if centred else 2)
    end = t + pd.DateOffset(months=1) if centred else t
    if start.year == end.year:
        return f"{start:%b} to {end:%b %Y}"
    return f"{start:%b %Y} to {end:%b %Y}"


def pts(change: float) -> str:
    """A change in a rate, in percentage points, as plain words."""
    change = round(change, 1)
    if change == 0:
        return "unchanged"
    return f"{'up' if change > 0 else 'down'} {abs(change):.1f} points"


def thousands(n: float) -> str:
    """People counts in thousands, written for humans: 1712 -> '1.71 million', 691 -> '691,000'."""
    n = float(n)
    return f"{n / 1000:.2f} million" if n >= 1000 else f"{n:,.0f},000"


def save(chart: bc.Chart, name: str) -> str:
    CHARTS.mkdir(exist_ok=True)
    chart.save(CHARTS / f"{name}.svg")
    return f"../charts/{name}.svg"


def axis(labels: list[str]) -> list[str]:
    """Labels for a line chart. The first one is left blank: bezel-charts 1.0 pins it to the left edge,
    where it can run into the next label on long series."""
    return [""] + labels[1:]


def annual(series: pd.Series) -> pd.Series:
    s = series.dropna()
    out = s.groupby(s.index.year).mean()
    return out.round(2)


# The findings --------------------------------------------------------------------------------

def headline_tiles(lm: pd.DataFrame) -> dict:
    """Finding 1: six small tiles with the latest figure and the last three years."""
    tiles = [
        ("unemployment", "unemployment_rate", "Unemployment", {"suffix": "%", "decimals": 1, "delta": "none"}),
        ("employment", "employment_rate", "Employment, 16 to 64", {"suffix": "%", "decimals": 1, "delta": "none"}),
        ("inactivity", "inactivity_rate", "Inactivity, 16 to 64", {"suffix": "%", "decimals": 1, "delta": "none"}),
        ("youth", "unemployment_rate_16_24", "Youth unemployment", {"suffix": "%", "decimals": 1, "delta": "none"}),
        ("vacancies", "vacancies_000s", "Job vacancies", {"suffix": "k"}),
        ("real-pay", "real_pay_growth_total", "Real pay growth", {"suffix": "%", "decimals": 1, "delta": "none"}),
    ]
    out = {}
    for slug, col, heading, opts in tiles:
        s = lm[col].dropna().iloc[-36:]
        labels = [mon(t) for t in s.index]
        extra = {"delta_label": f"since {mon(s.index[0])}"} if opts.get("delta") != "none" else {}
        chart = bc.spark(s.tolist(), labels=labels, heading=heading, width=300, **extra, **THEME, **opts)
        out[slug] = save(chart, f"tile-{slug}")
    return out


def long_run(lm: pd.DataFrame) -> dict:
    """Finding 2: unemployment since 1971, with the big recessions marked."""
    u = lm["unemployment_rate"].dropna()
    yearly = annual(u)
    peaks = {}
    for start, end, name in [("1979", "1988", "early 1980s"), ("1989", "1997", "early 1990s"),
                             ("2008", "2013", "after 2008"), ("2019", "2021", "Covid")]:
        window_ = u[start:end]
        peaks[name] = (window_.idxmax(), float(window_.max()))
    years = list(yearly.index)
    notes = {years.index(t.year): str(t.year) for t, _ in peaks.values() if t.year in years}  # keyed by position
    chart = bc.line(yearly.tolist(), labels=axis([str(y) for y in years]), heading="Unemployment rate, yearly average",
                    suffix="%", notes=notes, zero=True, width=WIDE, height=240, **THEME)
    when, now = latest(u)
    return {"chart": save(chart, "unemployment-since-1971"), "peaks": peaks, "now": now, "when": when,
            "low": (u.idxmin(), float(u.min())), "first_year": int(yearly.index[0]),
            "recent": (u["2023":].idxmax(), float(u["2023":].max())), "year_ago": float(u.iloc[-13])}


def tightness(lm: pd.DataFrame) -> dict:
    """Finding 3: vacancies for each unemployed person."""
    ratio = (lm["vacancies_000s"] / lm["unemployed_000s"]).dropna()
    yearly = annual(ratio)
    chart = bc.line(yearly.tolist(), labels=axis([str(y) for y in yearly.index]), heading="Job vacancies per unemployed person",
                    decimals=2, goal=1, goal_label="One vacancy each:", zero=True, width=WIDE, height=220, **THEME)
    when, now = latest(ratio)
    return {"chart": save(chart, "vacancies-per-unemployed"), "now": now, "when": when,
            "peak": (ratio.idxmax(), float(ratio.max())),
            "above_one": ratio[ratio >= 1].index.min() if (ratio >= 1).any() else None,
            "first": int(ratio.index[0].year), "low": (ratio.idxmin(), float(ratio.min())),
            "pre": at(ratio, PRE_PANDEMIC), "unemployed": latest(lm["unemployed_000s"])[1],
            "vacancies": latest(lm["vacancies_000s"])[1], "vac_when": latest(lm["vacancies_000s"])[0]}


REASONS = [
    ("inactive_long_term_sick_000s", "Long-term sick"),
    ("inactive_students_000s", "Studying"),
    ("inactive_family_000s", "Family or home"),
    ("inactive_retired_000s", "Retired early"),
    ("inactive_other_000s", "Other reason"),
    ("inactive_temp_sick_000s", "Temporarily sick"),
]


def inactivity(lm: pd.DataFrame) -> dict:
    """Finding 4: why people are out of work and not looking."""
    when = lm[REASONS[0][0]].dropna().index[-1]
    now = {label: float(lm.loc[when, col]) for col, label in REASONS}
    pre = {label: at(lm[col], PRE_PANDEMIC) for col, label in REASONS}
    donut = bc.donut(now, heading=f"Why people aged 16 to 64 are inactive, {window(when)}", center_label="thousand",
                     compact=True, width=WIDE, height=200, **THEME)
    compare = bc.bars({f"Before Covid ({window(pd.Timestamp(PRE_PANDEMIC))})": list(pre.values()),
                       f"Now ({window(when)})": list(now.values())},
                      labels=list(now), horizontal=True, heading="Inactive people by reason, thousands",
                      width=WIDE, **THEME)
    lts = lm["inactive_long_term_sick_000s"].dropna()
    return {"donut": save(donut, "inactivity-reasons"), "compare": save(compare, "inactivity-then-and-now"),
            "now": now, "pre": pre, "when": when, "total": float(lm.loc[when, "inactive_000s"]),
            "lts_peak": (lts.idxmax(), float(lts.max())), "lts_first": (lts.index[0], float(lts.iloc[0]))}


def real_pay(lm: pd.DataFrame) -> dict:
    """Finding 5: is pay beating prices?"""
    r = lm["real_pay_growth_total"].dropna()
    yearly = annual(r)
    chart = bc.line(yearly.tolist(), labels=axis([str(y) for y in yearly.index]),
                    heading="Pay growth after inflation, total pay, yearly average", suffix="%", decimals=1,
                    goal=0, goal_label="Pay matching prices:", width=WIDE, height=230, **THEME)
    when, now = latest(r)
    nominal = latest(lm["pay_growth_total"])[1]
    falling = (r < 0)
    runs, start = [], None
    for t, neg in falling.items():
        if neg and start is None:
            start = t
        if not neg and start is not None:
            runs.append((start, prev))
            start = None
        prev = t
    if start is not None:
        runs.append((start, r.index[-1]))
    longest = max(runs, key=lambda ab: (ab[1] - ab[0]).days) if runs else None
    return {"chart": save(chart, "real-pay-growth"), "now": now, "when": when, "nominal": nominal,
            "worst": (r.idxmin(), float(r.min())), "neg_months": int(falling.sum()), "longest": longest,
            "first_year": int(yearly.index[0])}


REGIONS = {
    "north_east": "North East", "north_west": "North West", "yorkshire": "Yorkshire and The Humber",
    "east_midlands": "East Midlands", "west_midlands": "West Midlands", "east": "East of England",
    "london": "London", "south_east": "South East", "south_west": "South West", "wales": "Wales",
    "scotland": "Scotland", "northern_ireland": "Northern Ireland",
}


def regions(lm: pd.DataFrame) -> dict:
    """Finding 6: where unemployment is highest and lowest."""
    cols = {f"unemployment_rate_{k}": v for k, v in REGIONS.items()}
    when = lm[list(cols)].dropna().index[-1]
    rates = pd.Series({name: float(lm.loc[when, col]) for col, name in cols.items()}).sort_values(ascending=False)
    uk = float(lm.loc[when, "unemployment_rate"])
    chart = bc.bars(rates, horizontal=True, heading=f"Unemployment rate by nation and region, {window(when)}",
                    suffix="%", decimals=1, goal=uk, width=WIDE, **THEME)
    return {"chart": save(chart, "unemployment-by-region"), "rates": rates, "uk": uk, "when": when}


AGES = [("unemployment_rate_16_24", "16 to 24"), ("unemployment_rate_25_34", "25 to 34"),
        ("unemployment_rate_35_49", "35 to 49"), ("unemployment_rate_50_64", "50 to 64")]


def ages(lm: pd.DataFrame) -> dict:
    """Finding 7: how young people are doing."""
    when = lm[AGES[0][0]].dropna().index[-1]
    now = [float(lm.loc[when, c]) for c, _ in AGES]
    pre = [at(lm[c], PRE_PANDEMIC) for c, _ in AGES]
    chart = bc.bars({f"Before Covid ({window(pd.Timestamp(PRE_PANDEMIC))})": pre, f"Now ({window(when)})": now},
                    labels=[name for _, name in AGES], heading="Unemployment rate by age", suffix="%", decimals=1,
                    show_values=True, width=WIDE, height=200, **THEME)
    youth = lm["unemployment_rate_16_24"].dropna()
    now_y, i = youth.iloc[-1], len(youth) - 1
    while i > 0 and youth.iloc[i - 1] >= now_y:  # step back over the current run of high months
        i -= 1
    earlier = youth.iloc[:i]
    earlier = earlier[earlier >= now_y]
    last_as_high = earlier.index[-1] if len(earlier) and (youth.index[i] - earlier.index[-1]).days > 365 else None
    return {"chart": save(chart, "unemployment-by-age"), "now": dict(zip([n for _, n in AGES], now)),
            "pre": dict(zip([n for _, n in AGES], pre)), "when": when, "year_ago": float(youth.iloc[-13]),
            "last_as_high": last_as_high}


def phillips(lm: pd.DataFrame) -> dict:
    """Finding 8: do low unemployment and fast pay rises go together?"""
    both = pd.concat({"u": annual(lm["unemployment_rate"]), "w": annual(lm["pay_growth_regular"])}, axis=1).dropna()
    last_full = pd.Timestamp.today().year - 1
    both = both[both.index <= min(last_full, int(lm["pay_growth_regular"].dropna().index[-1].year) - 1)]
    r = float(np.corrcoef(both["u"], both["w"])[0, 1])
    years = list(both.index)
    notes = {years.index(y): str(y) for y in (2009, 2019, 2023) if y in years}  # keyed by position
    chart = bc.scatter(x=both["u"].tolist(), y=both["w"].tolist(), labels=[str(y) for y in both.index], notes=notes,
                       trend=True, x_label="Unemployment rate, %", y_label="Regular pay growth, %",
                       heading=f"Each dot is a year, {both.index[0]} to {both.index[-1]}", suffix="%", decimals=1,
                       width=WIDE, height=280, **THEME)
    return {"chart": save(chart, "unemployment-vs-pay"), "r": r, "years": (int(both.index[0]), int(both.index[-1])),
            "table": both}


def trust(lm: pd.DataFrame, pay: pd.Series) -> dict:
    """Bonus: the survey and the payroll records tell different stories."""
    lfs = lm["employed_000s"].dropna() * 1000
    joined = pd.concat({"lfs": lfs, "pay": pay}, axis=1).dropna()
    base = joined.loc[PRE_PANDEMIC].iloc[0]
    index = (joined / base * 100).round(2)
    index = index[index.index >= "2017-01-01"]
    chart = bc.line({"Labour Force Survey (people in work)": index["lfs"].tolist(),
                     "HMRC payroll (employees paid)": index["pay"].tolist()},
                    labels=axis([mon(t) for t in index.index]), heading="Two measures of jobs, Dec 2019 to Feb 2020 = 100",
                    decimals=1, width=WIDE, height=240, **THEME)
    pay_when, pay_now = latest(pay)
    return {"chart": save(chart, "survey-vs-payroll"), "pay_peak": (pay.idxmax(), float(pay.max())),
            "pay_now": pay_now, "pay_when": pay_when, "lfs_change": float(lfs.iloc[-1] - at(lfs, PRE_PANDEMIC)),
            "pay_change": float(pay_now - at(pay, PRE_PANDEMIC)), "lfs_when": lfs.index[-1],
            "since_peak": float(pay_now - pay.max())}


# The report ----------------------------------------------------------------------------------

def write_report(f: dict, sources: dict) -> str:
    h, lr, t, ina, rp, rg, ag, ph, tr = (f[k] for k in
                                         ("tiles", "long", "tight", "inactive", "pay", "regions", "ages", "phillips", "trust"))
    u_when = lr["when"]
    peak80 = lr["peaks"]["early 1980s"]
    peak90 = lr["peaks"]["early 1990s"]
    peak08 = lr["peaks"]["after 2008"]
    covid = lr["peaks"]["Covid"]
    lts_now, lts_pre = ina["now"]["Long-term sick"], ina["pre"]["Long-term sick"]
    share_lts = lts_now / sum(ina["now"].values()) * 100
    rates = rg["rates"]
    young_now, young_pre = ag["now"]["16 to 24"], ag["pre"]["16 to 24"]
    others_now = [v for k, v in ag["now"].items() if k != "16 to 24"]
    longest = rp["longest"]
    def moved(label: str) -> str:
        diff = ina["now"][label] - ina["pre"][label]
        return f"{label.lower()} is {'up' if diff > 0 else 'down'} {abs(diff):,.0f},000"
    changes_line = "- Among the other reasons, " + ", ".join(moved(k) for k in ("Studying", "Family or home", "Retired early")) + "."
    london_rank = list(rates.index).index("London")
    london_line = (
        "London surprises many people. It has lots of well-paid jobs, but also many people looking for work, high living\n"
        "costs and a young, fast-moving population, so its rate is often above average.\n\n"
        if london_rank < 3 else ""
    )
    recent = lr["recent"]
    recent_line = (
        f"More recently it climbed to **{recent[1]:.1f}%** in {window(recent[0])}, and was {lr['now']:.1f}% in {window(u_when)}.\n\n"
        if recent[0] != u_when and recent[1] - lr["now"] >= 0.2 else ""
    )
    if t["above_one"] is not None:
        peak_line = (f"- In {mon(t['above_one'])} vacancies outnumbered unemployed people for the first time since the figures began in\n"
                     f"  {t['first']}. The ratio peaked at **{t['peak'][1]:.2f}** in {mon(t['peak'][0])}.")
    else:
        peak_line = f"- The highest it has been was **{t['peak'][1]:.2f}**, in {mon(t['peak'][0])}."
    biggest = max(ina["now"], key=ina["now"].get)
    biggest_intro = "The biggest group, though, is people who are" if biggest == "Long-term sick" else "A large group is people who are"
    gap_now = young_now - sum(others_now) / len(others_now)
    others_pre = [v for k, v in ag["pre"].items() if k != "16 to 24"]
    gap_pre = young_pre - sum(others_pre) / len(others_pre)
    gap_line = "But the gap has grown since Covid." if gap_now > gap_pre + 0.3 else (
        "The gap has narrowed since Covid." if gap_now < gap_pre - 0.3 else "The gap is about the same as before Covid.")
    tile = lambda key, alt: f'<img src="{h[key]}" width="32%" alt="{alt}">'  # noqa: E731

    lines = f"""# State of UK jobs

**Latest data: {window(u_when)}.** Every number and chart on this page is worked out from ONS data by
[`build.py`](build.py), and redrawn automatically when ONS publishes new figures. Charts are made with
[bezel-charts](https://pypi.org/project/bezel-charts/).

Data last downloaded: {sources['fetched']}.

## 1. The headline numbers

{tile('unemployment', 'Unemployment rate over the last three years')}
{tile('employment', 'Employment rate over the last three years')}
{tile('inactivity', 'Economic inactivity rate over the last three years')}
{tile('youth', 'Youth unemployment rate over the last three years')}
{tile('vacancies', 'Job vacancies over the last three years')}
{tile('real-pay', 'Real pay growth over the last three years')}

Each tile shows the last three years. The big number is the latest figure.

- **{lr['now']:.1f}%** of people who are working or looking for work are unemployed. That's
  {pts(lr['now'] - lr['year_ago'])} on a year earlier.
- **{thousands(t['vacancies'])}** jobs were waiting to be filled in {window(t['vac_when'])}, against
  **{thousands(t['unemployed'])}** unemployed people.
- Pay rose **{rp['nominal']:.1f}%** on a year earlier, in {window(rp['when'], centred=False)}. After rising prices are taken
  off, that's **{rp['now']:.1f}%**.

## 2. Unemployment since {lr['first_year']}

![Unemployment rate since {lr['first_year']}]({lr['chart']})

Unemployment has risen sharply in every big downturn, then taken years to come back down.

- **The early 1980s** were the worst: unemployment peaked at **{peak80[1]:.1f}%** in {window(peak80[0])}, as factories and mines closed.
- **The early 1990s** recession pushed it to **{peak90[1]:.1f}%** in {window(peak90[0])}.
- **After the 2008 financial crisis** it rose more slowly but stayed high for years, reaching **{peak08[1]:.1f}%** in {window(peak08[0])}.
- **Covid** was a much smaller bump than many feared, peaking at **{covid[1]:.1f}%** in {window(covid[0])}.
  Government furlough paid wages for millions of people, so most kept their jobs.

{recent_line}The lowest rate on record was **{lr['low'][1]:.1f}%**, in {window(lr['low'][0])}.

## 3. How many jobs are there for each unemployed person?

![Vacancies per unemployed person]({t['chart']})

When there are lots of vacancies for each unemployed person, it's easier to find work and employers have
to compete for staff, often by paying more. Economists call this a **tight** labour market.

- Right now there are **{t['now']:.2f}** vacancies for every unemployed person, against **{t['pre']:.2f}** just before Covid.
{peak_line}
- At the low point, in {mon(t['low'][0])}, there were only **{t['low'][1]:.2f}**: about one vacancy for every
  {1 / t['low'][1]:.0f} unemployed people.

## 4. Why are people out of work and not looking?

![Why people are economically inactive]({ina['donut']})

**Economically inactive** means not working and not looking for work. In {window(ina['when'])},
**{thousands(ina['total'])}** people aged 16 to 64 were inactive. Many have good reasons: they're studying,
caring for family or have retired early.

{biggest_intro} **long-term sick**: **{thousands(lts_now)}**, or about {share_lts:.0f}% of everyone
inactive for a stated reason.

![Inactive people by reason, then and now]({ina['compare']})

- Long-term sickness is {'up' if lts_now >= lts_pre else 'down'} **{abs(lts_now - lts_pre):,.0f},000** since just before Covid.
- When these figures began, in {window(ina['lts_first'][0])}, the number was {thousands(ina['lts_first'][1])}. It peaked at
  **{thousands(ina['lts_peak'][1])}** in {window(ina['lts_peak'][0])}.
{changes_line}

This matters for the whole economy. Fewer people working means fewer people paying tax and more pressure on
benefits and the NHS.

## 5. Is pay beating prices?

![Pay growth after inflation]({rp['chart']})

**Real pay** is pay growth with rising prices taken off. If your pay rises 5% but prices rise 6%, your real pay
has fallen 1%.

- Right now real pay is growing **{rp['now']:.1f}%** a year, in the three months to {mon(rp['when'])}.
- The worst point was **{rp['worst'][1]:.1f}%** in the three months to {mon(rp['worst'][0])}, during the financial crisis.
- Since {rp['first_year']}, real pay was falling in **{rp['neg_months']}** of the monthly figures.
  The longest unbroken run of falls lasted from {mon(longest[0])} to {mon(longest[1])}.
- The 2021 jump is partly a quirk: pay was being compared with 2020, when many furloughed workers were on reduced pay.
- In 2022 and early 2023 pay rose fast, but prices rose even faster, so most people were still worse off.

## 6. Which places are doing best and worst?

![Unemployment by nation and region]({rg['chart']})

In {window(rg['when'])}, unemployment was highest in **{rates.index[0]} ({rates.iloc[0]:.1f}%)** and lowest in
**{rates.index[-1]} ({rates.iloc[-1]:.1f}%)**. The UK average was {rg['uk']:.1f}%, shown by the line.

{london_line}These regional figures come from smaller samples, so they jump around more from month to month. Look at the
trend over several months before reading too much into one figure.

## 7. How are young people doing?

![Unemployment by age]({ag['chart']})

Young people always have higher unemployment: they're new to work, change jobs more and are often the first
to go when firms cut back. {gap_line}

- Among 16 to 24 year olds who are working or looking for work, **{young_now:.1f}%** are unemployed, against
  **{young_pre:.1f}%** just before Covid.
- For older age groups the rate is between {min(others_now):.1f}% and {max(others_now):.1f}%.
- Youth unemployment is {pts(young_now - ag['year_ago'])} on a year earlier."""
    if ag["last_as_high"] is not None:
        lines += f"\n  The last time it was this high was {window(ag['last_as_high'])}."
    lines += f"""

## 8. Do low unemployment and fast pay rises go together?

![Unemployment against pay growth]({ph['chart']})

Economists have long noticed that when unemployment is low, pay tends to rise faster, because employers have to
compete for workers. This is called the **Phillips curve**, after the economist Bill Phillips, who spotted it in UK
data in 1958.

Each dot is a year from {ph['years'][0]} to {ph['years'][1]}. The dashed line is the best straight-line fit, and
**r = {ph['r']:.2f}** measures how closely the dots follow it (−1 would be a perfect downward line, 0 no pattern at all).

- The pattern is real but loose. Years after the 2008 crash sit bottom right: high unemployment, slow pay growth.
- 2022 to 2024 sit top left, but low unemployment wasn't the only reason. Prices were rising fast, and people
  pushed for pay rises to keep up.

## Can we trust the numbers?

![Survey against payroll]({tr['chart']})

Most of the figures above come from the **Labour Force Survey**, which asks a sample of households about work.
In 2023 so few people were answering it that ONS paused some of its figures for a while. Responses have since
recovered, but ONS still warns that some figures, especially smaller breakdowns like regions, jump around more
than they used to. It has also said survey changes made since 2024 may be making recent employment growth look
stronger than it really is. ONS is moving to a new online version, the Transformed Labour Force Survey.

There's a second source. **HMRC payroll records** count everyone paid through PAYE, so they're based on real pay
slips, not answers to a survey. They miss self-employed people, but they're a useful check.

- Since just before Covid, the survey says the number of people in work rose by **{tr['lfs_change'] / 1e6:.2f} million**,
  to {mon(tr['lfs_when'])}.
- Payroll records peaked at **{tr['pay_peak'][1] / 1e6:.2f} million** employees in {mon(tr['pay_peak'][0])}. By {mon(tr['pay_when'])}
  the figure was {abs(tr['since_peak']) / 1000:,.0f},000 {'lower' if tr['since_peak'] < 0 else 'higher'}.
- So the two sources have been pointing in different directions. The truth is probably somewhere in between, and
  that's a good reminder to check more than one source before drawing big conclusions.

The latest payroll month is a first estimate and often changes.

---

**Sources:** Office for National Statistics, Labour market overview and Average weekly earnings, and HMRC PAYE Real
Time Information, all under the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).
Series IDs and links are in [`data/sources.json`](../data/sources.json).
"""
    return lines


def main() -> None:
    # bezel-charts gives each gradient a random id so charts can share a page. A fixed seed keeps the
    # files identical from one run to the next, so only real changes in the data show up in git.
    random.seed(2026)
    lm, pay, sources = load()
    findings = {
        "lm": lm,
        "tiles": headline_tiles(lm),
        "long": long_run(lm),
        "tight": tightness(lm),
        "inactive": inactivity(lm),
        "pay": real_pay(lm),
        "regions": regions(lm),
        "ages": ages(lm),
        "phillips": phillips(lm),
        "trust": trust(lm, pay),
    }
    REPORT.write_text(write_report(findings, sources), encoding="utf-8")
    print(f"Saved {len(list(CHARTS.glob('*.svg')))} charts to {CHARTS} and the report to {REPORT}")


if __name__ == "__main__":
    main()
