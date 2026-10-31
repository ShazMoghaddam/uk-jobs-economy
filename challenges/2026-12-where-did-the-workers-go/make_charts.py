"""How the charts in this brief were made. They're a snapshot of the data at launch, so the brief and its
numbers always agree. Run from the repository root:

    python challenges/2026-12-where-did-the-workers-go/make_charts.py
"""

import math
import random
from pathlib import Path

import pandas as pd

import bezel_charts as bc

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

random.seed(2026)  # stable gradient ids, so rerunning gives identical files
data = pd.read_csv(ROOT / "data" / "labour_market.csv", parse_dates=["date"], date_format="%Y-%m").set_index("date")


def yearly(column: str) -> pd.Series:
    """Yearly averages, summed exactly so every computer draws the same chart."""
    s = data[column].dropna()
    years = {}
    for t, v in s.items():
        years.setdefault(t.year, []).append(float(v))
    return pd.Series({y: round(math.fsum(vs) / len(vs), 1) for y, vs in years.items()})


def axis(years) -> list[str]:
    return [""] + [str(y) for y in list(years)[1:]]


rate = yearly("inactivity_rate")
bc.line(rate.tolist(), labels=axis(rate.index), heading="Share of 16 to 64 year olds who are inactive, yearly average",
        suffix="%", decimals=1, theme="light", width=760, height=220).save(HERE / "inactivity-rate.svg")

sick = yearly("inactive_long_term_sick_000s")
students = yearly("inactive_students_000s")
family = yearly("inactive_family_000s")
bc.line({"Long-term sick": sick.tolist(), "Studying": students.tolist(), "Family or home": family.tolist()},
        labels=axis(sick.index), heading="The three biggest reasons, thousands of people, yearly average",
        theme="light", width=760, height=240).save(HERE / "three-reasons.svg")

print("Saved the brief's charts to", HERE)
