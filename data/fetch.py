"""Download the UK labour market data this project uses, straight from the ONS.

Run from the repository root:

    python data/fetch.py

It writes three files into data/:

    labour_market.csv        one row per month, one column per series (wide, easy to use)
    labour_market_long.csv   the same figures in long format, with ONS's own period labels
    payrolled_employees.csv  monthly payrolled employees from HMRC PAYE Real Time Information
    sources.json             what each column is, where it came from and when ONS released it

Everything is free under the Open Government Licence v3.0. Only the Python standard library,
pandas and openpyxl are needed.

A note on dates. Most Labour Force Survey figures are averages over three months. ONS labels
them by the middle month, so "2026-07" means June to August 2026. Pay figures are labelled by
the last of their three months. The long file keeps ONS's exact period label for every value.
"""

from __future__ import annotations

import io
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ONS = "https://www.ons.gov.uk"
HERE = Path(__file__).resolve().parent
USER_AGENT = "uk-jobs-economy (+https://github.com/ShazMoghaddam/uk-jobs-economy)"

# column name: (ONS series ID, path to the series on ons.gov.uk, short description)
UNEMP = "/employmentandlabourmarket/peoplenotinwork/unemployment/timeseries"
INACT = "/employmentandlabourmarket/peoplenotinwork/economicinactivity/timeseries"
EMPLOY = "/employmentandlabourmarket/peopleinwork/employmentandemployeetypes/timeseries"
EARN = "/employmentandlabourmarket/peopleinwork/earningsandworkinghours/timeseries"

SERIES = {
    # The headline three
    "unemployment_rate": ("MGSX", UNEMP, "Unemployment rate, aged 16+, %"),
    "employment_rate": ("LF24", EMPLOY, "Employment rate, aged 16 to 64, %"),
    "inactivity_rate": ("LF2S", INACT, "Economic inactivity rate, aged 16 to 64, %"),
    # Levels, in thousands of people
    "unemployed_000s": ("MGSC", UNEMP, "People unemployed, aged 16+, thousands"),
    "employed_000s": ("MGRZ", EMPLOY, "People in employment, aged 16+, thousands"),
    "inactive_000s": ("LF2M", INACT, "People economically inactive, aged 16 to 64, thousands"),
    "vacancies_000s": ("AP2Y", EMPLOY, "Job vacancies, UK, thousands"),
    # Pay
    "pay_growth_total": ("KAC3", EARN, "Average weekly earnings growth, total pay, % on a year earlier"),
    "pay_growth_regular": ("KAI9", EARN, "Average weekly earnings growth, regular pay, % on a year earlier"),
    "real_pay_growth_total": ("A3WW", EARN, "Real average weekly earnings growth, total pay, % on a year earlier"),
    "real_pay_growth_regular": ("A2FA", EARN, "Real average weekly earnings growth, regular pay, % on a year earlier"),
    # Why people are economically inactive, aged 16 to 64, thousands
    "inactive_students_000s": ("LF63", INACT, "Inactive because studying, thousands"),
    "inactive_family_000s": ("LF65", INACT, "Inactive because looking after family or home, thousands"),
    "inactive_temp_sick_000s": ("LF67", INACT, "Inactive because temporarily sick, thousands"),
    "inactive_long_term_sick_000s": ("LF69", INACT, "Inactive because long-term sick, thousands"),
    "inactive_retired_000s": ("LF6B", INACT, "Inactive because retired (under 65), thousands"),
    "inactive_other_000s": ("LF6D", INACT, "Inactive for another reason, thousands"),
    # Unemployment by age, %
    "unemployment_rate_16_24": ("MGWY", UNEMP, "Unemployment rate, aged 16 to 24, %"),
    "unemployment_rate_25_34": ("YCGP", UNEMP, "Unemployment rate, aged 25 to 34, %"),
    "unemployment_rate_35_49": ("YCGV", UNEMP, "Unemployment rate, aged 35 to 49, %"),
    "unemployment_rate_50_64": ("LF2E", UNEMP, "Unemployment rate, aged 50 to 64, %"),
    # Unemployment by nation and region, aged 16+, %
    "unemployment_rate_north_east": ("YCNC", UNEMP, "Unemployment rate, North East, %"),
    "unemployment_rate_north_west": ("YCND", UNEMP, "Unemployment rate, North West, %"),
    "unemployment_rate_yorkshire": ("YCNE", UNEMP, "Unemployment rate, Yorkshire and The Humber, %"),
    "unemployment_rate_east_midlands": ("YCNF", UNEMP, "Unemployment rate, East Midlands, %"),
    "unemployment_rate_west_midlands": ("YCNG", UNEMP, "Unemployment rate, West Midlands, %"),
    "unemployment_rate_east": ("YCNH", UNEMP, "Unemployment rate, East of England, %"),
    "unemployment_rate_london": ("YCNI", UNEMP, "Unemployment rate, London, %"),
    "unemployment_rate_south_east": ("YCNJ", UNEMP, "Unemployment rate, South East, %"),
    "unemployment_rate_south_west": ("YCNK", UNEMP, "Unemployment rate, South West, %"),
    "unemployment_rate_wales": ("YCNM", UNEMP, "Unemployment rate, Wales, %"),
    "unemployment_rate_scotland": ("YCNN", UNEMP, "Unemployment rate, Scotland, %"),
    "unemployment_rate_northern_ireland": ("ZSFB", UNEMP, "Unemployment rate, Northern Ireland, %"),
}

RTI_PAGE = (
    "/employmentandlabourmarket/peopleinwork/earningsandworkinghours/datasets/"
    "realtimeinformationstatisticsreferencetableseasonallyadjusted"
)
MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], start=1)}


def get(url: str, retries: int = 3) -> bytes:
    """Fetch a URL politely, retrying a couple of times if ONS is busy."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except Exception:  # noqa: BLE001 - any network hiccup gets a retry
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("unreachable")


def month(label: str) -> str:
    """'2026 JUL' -> '2026-07'."""
    year, mon = label.split()
    return f"{int(year):04d}-{MONTHS[mon[:3].upper()]:02d}"


def fetch_series(name: str, cdid: str, path: str) -> tuple[pd.DataFrame, dict]:
    data = json.loads(get(f"{ONS}{path}/{cdid.lower()}/lms/data"))
    rows = [
        {"series": name, "cdid": cdid, "date": month(m["date"]), "period": m.get("label") or m["date"],
         "value": float(m["value"])}
        for m in data.get("months", [])
        if m.get("value") not in (None, "")
    ]
    desc = data["description"]
    meta = {
        "cdid": cdid,
        "ons_title": desc["title"].strip(),
        "url": f"{ONS}{path}/{cdid.lower()}/lms",
        "released": desc.get("releaseDate", "")[:10],
        "next_release": desc.get("nextRelease", ""),
    }
    return pd.DataFrame(rows), meta


def fetch_payroll() -> tuple[pd.DataFrame, dict]:
    page = get(ONS + RTI_PAGE).decode("utf-8", "replace")
    link = re.search(r'href="(/file\?uri=[^"]+\.xlsx)"', page)
    if not link:
        raise RuntimeError("Could not find the PAYE RTI spreadsheet on the ONS dataset page.")
    book = pd.read_excel(io.BytesIO(get(ONS + link.group(1))), sheet_name="1. Payrolled employees (UK)", header=None)
    start = book.index[book[0].astype(str).str.strip().eq("Date")][0] + 1
    table = book.iloc[start:, :2].dropna()
    table.columns = ["month", "payrolled_employees"]
    table["date"] = pd.to_datetime(table["month"].astype(str), format="%B %Y").dt.strftime("%Y-%m")
    table["payrolled_employees"] = table["payrolled_employees"].astype(int)
    meta = {"source": "HMRC PAYE Real Time Information, via ONS", "url": ONS + RTI_PAGE, "file": ONS + link.group(1),
            "note": "The latest month is a flash estimate and is often revised."}
    return table[["date", "payrolled_employees"]].reset_index(drop=True), meta


def main() -> None:
    frames, sources = [], {}
    for i, (name, (cdid, path, description)) in enumerate(SERIES.items(), start=1):
        print(f"[{i:2}/{len(SERIES)}] {cdid} {description}")
        frame, meta = fetch_series(name, cdid, path)
        frames.append(frame)
        sources[name] = {"description": description, **meta, "first": frame["date"].min(), "last": frame["date"].max()}
        time.sleep(0.3)

    long = pd.concat(frames, ignore_index=True)
    long.to_csv(HERE / "labour_market_long.csv", index=False)
    wide = long.pivot(index="date", columns="series", values="value").reindex(columns=list(SERIES)).reset_index()
    wide.to_csv(HERE / "labour_market.csv", index=False)

    print("[RTI] Payrolled employees")
    payroll, payroll_meta = fetch_payroll()
    payroll.to_csv(HERE / "payrolled_employees.csv", index=False)
    sources["payrolled_employees"] = {"description": "Payrolled employees, UK, people", **payroll_meta,
                                      "first": payroll["date"].min(), "last": payroll["date"].max()}

    manifest = {
        "fetched": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "licence": "Open Government Licence v3.0",
        "credit": "Source: Office for National Statistics licensed under the Open Government Licence v3.0.",
        "series": sources,
    }
    (HERE / "sources.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(wide)} months x {len(SERIES)} series, and {len(payroll)} months of payroll data, to {HERE}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        sys.exit(f"Download failed: {exc}\nONS may be busy. Wait a minute and run it again.")
