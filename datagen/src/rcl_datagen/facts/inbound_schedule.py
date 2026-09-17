"""Forward inbound-receipt schedule — INVENTED, not a mirror of any real table.

Grain: material x dc x inbound_week, cfg.dates.inbound_horizon_weeks weeks
ahead of the Monday of the current week. Not every (material, dc, week) has a
scheduled receipt — business_rules.inbound_receipt_probability gates whether
one exists at all; when it does, the quantity is gamma-distributed and damped
by the same current_risk used elsewhere (a material under more supply risk
tends to have thinner scheduled inbound).

Lowercase snake_case columns — same reasoning as atp_snapshot.py: this is a
generated fact, not a mirror of a specific real table.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from rcl_datagen import calendar as cal
from rcl_datagen.dimensions.locations import distribution_centers


def build_inbound_schedule(
    rng: np.random.Generator,
    cfg,
    products: pd.DataFrame,
    locations: pd.DataFrame,
    current_risk: pd.DataFrame,
) -> pd.DataFrame:
    as_of = cfg.dates.as_of_date
    anchor_monday = as_of - dt.timedelta(days=as_of.weekday())
    inbound_weeks = cal.build_forward_weeks(anchor_monday, cfg.dates.inbound_horizon_weeks)

    dcs = distribution_centers(locations)["plnt_cd"].tolist()
    grid = (
        products[["material", "case_pack_size"]]
        .merge(pd.DataFrame({"dc": dcs}), how="cross")
        .merge(inbound_weeks, how="cross")
    )
    n = len(grid)

    risk_lookup = current_risk.set_index("material")["risk_index"]
    fallback_risk = float(risk_lookup.mean()) if len(risk_lookup) else 0.1
    risk = grid["material"].map(risk_lookup).fillna(fallback_risk).to_numpy()
    risk_damp = np.clip(1.2 - risk, 0.2, 1.2)

    has_receipt = rng.random(n) < cfg.business_rules.inbound_receipt_probability
    case_pack = grid["case_pack_size"].to_numpy()
    qty_eaches = np.round(rng.gamma(shape=1.5, scale=300.0, size=n) * risk_damp, 0)
    inbound_qty_cases = np.where(has_receipt, np.round(qty_eaches / case_pack), 0.0)

    return pd.DataFrame({
        "material": grid["material"],
        "dc": grid["dc"],
        "inbound_week": grid["week_start_date"],
        "inbound_qty_cases": inbound_qty_cases,
    })
