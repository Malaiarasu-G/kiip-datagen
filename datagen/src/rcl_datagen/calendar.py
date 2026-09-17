"""Calendar dimension: one row per day, with fiscal week/month/year labels.

ASSUMPTION (documented in config/config.yaml too): fiscal year/month/week are
simplified to the ISO calendar — Monday-start weeks, fiscal period = calendar
month. The source screenshots show two different label styles depending on
the table, both produced here:
  - "underscore" style, e.g. "2023_wk47" / "2023_11"  (shipments, historical)
  - "compact" style,    e.g. "202347"    / "2023011"  (vulnerability)
Swap in the client's real 4-4-5 retail fiscal calendar here once confirmed —
this is the only module that would need to change.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd


def build_daily_calendar(start: dt.date, end: dt.date) -> pd.DataFrame:
    """One row per calendar day from `start` to `end` inclusive."""
    dates = pd.date_range(start, end, freq="D")
    iso = dates.isocalendar()

    df = pd.DataFrame({
        "cal_date": dates.date,
        "cal_year": dates.year,
        "cal_month": dates.month,
        "day_of_week": dates.day_name(),
        "iso_year": iso["year"].to_numpy(),
        "iso_week": iso["week"].to_numpy(),
    })

    iso_week_str = df["iso_week"].astype(str).str.zfill(2)
    cal_month_str = df["cal_month"].astype(str).str.zfill(2)

    df["fisc_yr_wk_num"] = df["iso_year"].astype(str) + "_wk" + iso_week_str      # "2023_wk47"
    df["fisc_yr_mo_num"] = df["cal_year"].astype(str) + "_" + cal_month_str       # "2023_11"
    df["calweek"] = df["iso_year"].astype(str) + iso_week_str                     # "202347"
    df["fiscper"] = df["cal_year"].astype(str) + df["cal_month"].astype(str).str.zfill(3)  # "2023011"
    return df


def build_weekly_calendar(daily: pd.DataFrame) -> pd.DataFrame:
    """One row per ISO week (Monday date as week_start_date) — matches the
    vulnerability report's grain."""
    weekly = (
        daily.groupby(["iso_year", "iso_week"], as_index=False)
        .agg(
            week_start_date=("cal_date", "min"),
            cal_year=("cal_year", "first"),
            fisc_yr_wk_num=("fisc_yr_wk_num", "first"),
            calweek=("calweek", "first"),
            fiscper=("fiscper", "first"),
        )
        .rename(columns={"iso_week": "week_num"})
        .sort_values("week_start_date")
        .reset_index(drop=True)
    )
    return weekly
