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

CUSTOMER_GROUP / ALLOCATED_QTY / ORDERED_QTY / REMAINING_QTY / PCT_CONSUMED
are INVENTED — the real snapshot never showed customer or quantity fields on
this table (it's parent-product x date x period only). Added because
allocation-consumption questions need them; grain is customer *segment*, not
ship-to (nothing needs per-ship-to allocation, and it would multiply row
count for no benefit), and deliberately NOT further split by DC (the real
table never showed DC either, and no question needs allocation sliced by
DC — see datagen/docs planning notes).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from rcl_datagen.reference_codes import KC_CODES, KC_WEIGHTS

_KC_CODES = KC_CODES
_KC_WEIGHTS = KC_WEIGHTS


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
    customers: pd.DataFrame,
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
    grid["_RISK_IDX"] = risk_idx  # carried through the segment cross-join below, then dropped

    grid = grid.rename(columns={
        "material_parent_cd": "PARENT_CODE",
        "material_parent_desc": "PARENT_DESC",
        "each_upc": "EACH_UPC",
        "case_upc": "CASE_UPC",
        "gbu": "SC_GBU",
        "franchise": "SC_FRANCHISE",
        "brand": "SC_BRAND",
    })

    # --- customer-group consumption (INVENTED — see module docstring) ---------
    # Broadcast across segments AFTER on-allocation/KC are decided at the
    # parent x date x period grain: being "on allocation" is a parent-level
    # fact, not a per-segment one — drawing it independently per segment would
    # let one segment show "On Allocation" while another doesn't for the same
    # parent/day/period, which would break the cross-table "why" story.
    segments = pd.DataFrame({"CUSTOMER_GROUP": customers["cust_seg_cd"].unique()})
    grid = grid.merge(segments, how="cross")
    n2 = len(grid)
    risk_idx2 = grid["_RISK_IDX"].to_numpy()

    ordered_qty = np.round(rng.gamma(shape=2.5, scale=40.0, size=n2))
    # headroom shrinks as risk rises: most (low-risk) rows sit comfortably under
    # 100% consumed; only the higher-risk tail approaches or exceeds it.
    tightness = np.clip(2.2 - risk_idx2 * cfg.business_rules.allocation_tightness_risk_weight, 0.4, 2.2)
    allocated_qty = np.clip(np.round(ordered_qty * tightness * rng.uniform(0.85, 1.05, size=n2)), 1, None)
    pct_consumed = np.clip(np.round(100.0 * ordered_qty / allocated_qty, 1), 0, 250)  # >100 allowed (over-consumed)
    remaining_qty = np.clip(np.round(allocated_qty - ordered_qty), 0, None)

    grid["ALLOCATED_QTY"] = allocated_qty
    grid["ORDERED_QTY"] = ordered_qty
    grid["REMAINING_QTY"] = remaining_qty
    grid["PCT_CONSUMED"] = pct_consumed
    grid = grid.drop(columns="_RISK_IDX")

    ordered_cols = [
        "SAP_MOD", "PARENT_CODE", "ALLOCATION_LEVEL", "SAP_DESC", "PARENT_DESC",
        "EACH_UPC", "CASE_UPC", "SC_GBU", "SC_FRANCHISE", "SC_BRAND",
        "POM_4_BOX", "PSE", "ALLOC_STATUS", "KC", "KC_DESC",
        "MONTHYEAR", "CALENDAR_DT", "PERIOD",
        "CUSTOMER_GROUP", "ALLOCATED_QTY", "ORDERED_QTY", "REMAINING_QTY", "PCT_CONSUMED",
    ]
    return grid[ordered_cols]
