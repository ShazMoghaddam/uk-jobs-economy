"""Checks that the data is complete and the report says nothing silly.

Run from the repository root with `pytest`. The refresh workflow runs these before opening a pull request,
so a broken download or an odd ONS release never reaches the README unnoticed.
"""

import json
import re
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


@pytest.fixture(scope="module")
def lm() -> pd.DataFrame:
    return pd.read_csv(DATA / "labour_market.csv", parse_dates=["date"], date_format="%Y-%m").set_index("date")


@pytest.fixture(scope="module")
def report() -> str:
    return (ROOT / "findings" / "README.md").read_text(encoding="utf-8")


def test_every_series_is_present_and_recent(lm):
    sources = json.loads((DATA / "sources.json").read_text(encoding="utf-8"))["series"]
    for name in sources:
        if name == "payrolled_employees":
            continue
        assert name in lm.columns, name
        last = lm[name].dropna().index[-1]
        assert last >= lm.index[-1] - pd.DateOffset(months=4), f"{name} stops at {last:%b %Y}"


def test_values_are_in_sensible_ranges(lm):
    rates = [c for c in lm.columns if c.endswith("_rate") or "_rate_" in c]
    for col in rates:
        s = lm[col].dropna()
        assert s.between(0, 100).all(), col
    assert lm["unemployment_rate"].dropna().between(1, 15).all()
    assert lm["vacancies_000s"].dropna().between(100, 2000).all()
    assert lm["real_pay_growth_total"].dropna().between(-15, 15).all()


def test_reasons_add_up_to_nearly_all_inactive_people(lm):
    reasons = [c for c in lm.columns if c.startswith("inactive_") and c.endswith("_000s") and c != "inactive_000s"]
    both = lm[reasons + ["inactive_000s"]].dropna()
    share = both[reasons].sum(axis=1) / both["inactive_000s"]
    # Discouraged workers are left out, and they're well under 1% of inactive people.
    assert share.between(0.97, 1.001).all()


def test_payroll_file_is_complete():
    pay = pd.read_csv(DATA / "payrolled_employees.csv")
    assert pay["payrolled_employees"].between(20_000_000, 40_000_000).all()
    assert pay["date"].is_monotonic_increasing and pay["date"].is_unique


def test_report_is_fully_filled_in(report):
    assert "{" not in report and "}" not in report, "a placeholder was left unfilled"
    for bad in ("nan", "NaN", "None", "inf", "NaT"):
        assert not re.search(rf"\b{bad}\b", report), f"report contains {bad!r}"
    assert "—" not in report, "no em dashes in the report"


def test_every_chart_in_the_report_exists(report):
    charts = re.findall(r"\.\./charts/([\w-]+\.svg)", report)
    assert len(charts) >= 12
    for name in charts:
        svg = (ROOT / "charts" / name).read_text(encoding="utf-8")
        assert svg.startswith("<svg") and "No data yet" not in svg, name


def test_readme_generated_blocks_are_filled_in():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for name in ("tiles", "key-findings"):
        block = readme.split(f"<!-- {name}:start -->")[1].split(f"<!-- {name}:end -->")[0]
        assert len(block.strip()) > 100, f"the {name} block in README.md is empty"
        assert "{" not in block and not re.search(r"\b(nan|None|NaT)\b", block), name
    for name in re.findall(r"\(charts/([\w-]+\.svg)\)|src=\"charts/([\w-]+\.svg)\"", readme):
        assert (ROOT / "charts" / (name[0] or name[1])).exists(), name
