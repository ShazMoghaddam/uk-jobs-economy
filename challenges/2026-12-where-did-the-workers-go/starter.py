"""Starter for Jobs & the Economy, December 2026: Where did the workers go?

Uses the tidy data file in this repo, so there's nothing to download first:

    pip install -r requirements.txt
    python challenges/2026-12-where-did-the-workers-go/starter.py

Want the very latest figures? Run `python data/fetch.py` first.

It prints a short summary and saves two charts, drawn with bezel-charts:

    long-term-sick.svg   long-term sickness since 1993
    reasons-now.svg      why people are inactive right now
"""

from pathlib import Path

import pandas as pd

import bezel_charts as bc

ROOT = Path(__file__).resolve().parents[2]

REASONS = {
    "inactive_long_term_sick_000s": "Long-term sick",
    "inactive_students_000s": "Studying",
    "inactive_family_000s": "Family or home",
    "inactive_retired_000s": "Retired early",
    "inactive_other_000s": "Other reason",
    "inactive_temp_sick_000s": "Temporarily sick",
}


def main() -> None:
    data = pd.read_csv(ROOT / "data" / "labour_market.csv", parse_dates=["date"]).set_index("date")
    reasons = data[list(REASONS)].dropna().rename(columns=REASONS)

    latest = reasons.index[-1]
    first = reasons.index[0]
    sick = reasons["Long-term sick"]
    print(f"Figures from {first:%b %Y} to {latest:%b %Y} (thousands of people aged 16 to 64)")
    print(f"Long-term sick now:      {sick.iloc[-1]:,.0f},000")
    print(f"Long-term sick in {first:%Y}:  {sick.iloc[0]:,.0f},000")
    print(f"Highest:                 {sick.max():,.0f},000 in {sick.idxmax():%b %Y}")

    # Beginner: one line over time. Yearly averages keep the chart readable.
    yearly = sick.groupby(sick.index.year).mean().round()
    bc.line(yearly, heading="People inactive because of long-term sickness, thousands",
            theme="light", width=720).save("long-term-sick.svg")

    # Intermediate idea: compare the reasons. Here's the latest split as a donut.
    bc.donut(reasons.iloc[-1].to_dict(), heading=f"Why people are inactive, {latest:%b %Y}",
             center_label="thousand", theme="light", width=720).save("reasons-now.svg")

    print("Saved long-term-sick.svg and reasons-now.svg. Open them in your browser.")


if __name__ == "__main__":
    main()
