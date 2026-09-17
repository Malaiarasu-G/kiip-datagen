"""Inventory allocation snapshot: `rcl_agent_osas` equivalent.

Grain: allocation-parent product x calendar date x AM/PM period (allocation
appears to run twice daily in the source). Rolls a window of
dates.allocation_lookback_days ending at as_of_date.

ALLOC_STATUS / KC / KC_DESC were null in every sampled row of the real
snapshot, so their real domain of values is unconfirmed — populated here
from a small placeholder lookup (see docs/data_dictionary). The probability
a parent is on allocation is driven by the shared material-week risk_index
(see risk.py), aggregated up from material to parent, so it lines up with
the vulnerability and shipment-cut stories for the same product family.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

_KC_CODES = [(None, None), ("SS", "Short Supply"), ("NC", "New Capacity Ramp"), ("QH", "Quality Hold")]
_KC_WEIGHTS = [0.5, 0.3, 0.2]


def _parent_level(products: pd.DataFrame) -> pd.DataFrame:
    return (
        products.sort_values("material")
        .groupby("material_parent_cd", as_index=False)
        .first()[["material_parent_cd", "material_parent_desc", "each_upc", "case_upc", "gbu", "franchise", "brand"]]
    )


def _parent_week_risk(products: pd.DataFrame, risk: pd.DataFrame) -> pd.DataFrame:
    mat_to_parent = products.set_index("material")["material_parent_cd"]
    r = risk.copy()
    r["material_parent_cd"] = r["material"].map(mat_to_parent)
    return r.groupby(["material_parent_cd", "week_start_date"], as_index=False)["risk_index"].mean()


def build_allocation(
    rng: np.random.Generator,
    cfg,
    products: pd.DataFrame,
    risk: pd.DataFrame,
) -> pd.DataFrame:
    parents = _parent_level(products)
    as_of = cfg.dates.as_of_date
    lookback = cfg.dates.allocation_lookback_days
    dates = pd.date_range(end=as_of, periods=lookback, freq="D")

    grid = parents.merge(pd.DataFrame({"CALENDAR_DT": dates}), how="cross")
    grid = grid.merge(pd.DataFrame({"PERIOD": ["AM", "PM"]}), how="cross")
    n = len(grid)

    parent_risk = _parent_week_risk(products, risk)
    week_of = grid["CALENDAR_DT"].dt.to_period("W-SUN").dt.start_time.dt.date
    risk_joined = pd.DataFrame({
        "material_parent_cd": grid["material_parent_cd"].to_numpy(),
        "week_start_date": week_of,
    }).merge(parent_risk, on=["material_parent_cd", "week_start_date"], how="left")
    risk_idx = risk_joined["risk_index"].fillna(0.1).to_numpy()

    alloc_probability = np.clip(cfg.business_rules.allocation_rate_base + risk_idx * 0.6, 0.0, 0.95)
    on_allocation = rng.random(n) < alloc_probability

    kc_idx = np.where(on_allocation, rng.choice([1, 2, 3], size=n, p=_KC_WEIGHTS), 0)
    grid["SAP_MOD"] = (5000000 + rng.integers(0, 999999, size=n)).astype(str)
    grid["ALLOCATION_LEVEL"] = "ZREDPAR"
    grid["SAP_DESC"] = None
    grid["ALLOC_STATUS"] = np.where(on_allocation, "On Allocation", None)
    grid["KC"] = [_KC_CODES[i][0] for i in kc_idx]
    grid["KC_DESC"] = [_KC_CODES[i][1] for i in kc_idx]
    grid["POM_4_BOX"] = rng.choice(["Box 1", "Box 2", "Box 3", "Box 4"], size=n)
    grid["PSE"] = None
    # "%-m" (no leading zero) isn't portable to Windows strftime, so build MONTHYEAR by hand.
    grid["MONTHYEAR"] = grid["CALENDAR_DT"].dt.month.astype(str) + "/" + grid["CALENDAR_DT"].dt.year.astype(str)

    grid = grid.rename(columns={
        "material_parent_cd": "PARENT_CODE",
        "material_parent_desc": "PARENT_DESC",
        "each_upc": "EACH_UPC",
        "case_upc": "CASE_UPC",
        "gbu": "SC_GBU",
        "franchise": "SC_FRANCHISE",
        "brand": "SC_BRAND",
    })

    ordered_cols = [
        "SAP_MOD", "PARENT_CODE", "ALLOCATION_LEVEL", "SAP_DESC", "PARENT_DESC",
        "EACH_UPC", "CASE_UPC", "SC_GBU", "SC_FRANCHISE", "SC_BRAND",
        "POM_4_BOX", "PSE", "ALLOC_STATUS", "KC", "KC_DESC",
        "MONTHYEAR", "CALENDAR_DT", "PERIOD",
    ]
    return grid[ordered_cols]
