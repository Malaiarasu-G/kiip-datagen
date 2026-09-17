"""Deterministic "planted pattern" pass — the 5 storylines the question bank's
Data brief calls for, guaranteed to survive generation rather than left to
chance from the shared risk_index random walk.

Runs AFTER all tables are built (see scripts/generate.py), as a post-hoc
mutation over the already-built DataFrames: pick a small, seeded, auditable
subset of existing rows and force them into the story. This is simpler and
safer than pre-biasing every fact builder's internals, and it lets
validate.py re-check by the exact keys returned here rather than needing to
reproduce a random draw.

Gated by config/config.yaml's `scenarios.enabled` — set false for pure
statistical randomness with no forced narratives.
"""
from __future__ import annotations

import datetime as dt
from typing import Dict, Optional

import numpy as np
import pandas as pd

from rcl_datagen.facts.vulnerability import score_columns
from rcl_datagen.reference_codes import DELIVERY_BLOCK_CODES


def apply_scenarios(rng: np.random.Generator, cfg, tables: Dict[str, pd.DataFrame]) -> Dict[str, Optional[dict]]:
    return {
        "dc2_fill_rate_drop": _apply_dc2_fill_rate_drop(rng, cfg, tables),
        "banner_block": _apply_banner_block(rng, tables),
        "yellow_to_red": _apply_yellow_to_red(rng, tables),
        "over_allocation": _apply_over_allocation(rng, tables),
        "late_gi": _apply_late_gi(rng, cfg, tables),
    }


def _recompute_cut_split(historical: pd.DataFrame, idx, cut_fraction: np.ndarray) -> None:
    """Redistribute DELV_QTY/CUT_QTY/DELV_VAL for `idx` so CUT_QTY == ORDR_QTY -
    DELV_VAL holds by construction — never touches ORDR_QTY/ORDR_VAL."""
    order_qty = historical.loc[idx, "ORDR_QTY"].to_numpy()
    unit_price = (historical.loc[idx, "ORDR_VAL"] / order_qty).to_numpy()
    cut_qty = np.round(order_qty * cut_fraction)
    delv_qty = order_qty - cut_qty
    historical.loc[idx, "DELV_QTY"] = delv_qty
    historical.loc[idx, "CUT_QTY"] = cut_qty
    historical.loc[idx, "DELV_VAL"] = delv_qty * unit_price
    historical.loc[idx, "CANCELLED_FL"] = "NO"
    historical.loc[idx, "CANCELLED_RSN_CD"] = None
    historical.loc[idx, "CANCELLED_RSN_DESC"] = None
    historical.loc[idx, "CUT_RSN_PRIM_CD"] = "ALOC"
    historical.loc[idx, "CUT_RSN_PRIM_DESC"] = "Allocation"


def _apply_dc2_fill_rate_drop(rng: np.random.Generator, cfg, tables: Dict[str, pd.DataFrame]) -> Optional[dict]:
    """Q6 (why did fill rate drop at DC2 last month) + Q9 (why was SKU X cut
    last week) — same underlying story, two time windows."""
    historical = tables["historical"]
    locations = tables["dim_location"]
    dcs = locations.loc[locations["is_distribution_center"], "plnt_cd"].tolist()
    if not dcs:
        return None
    dc2 = dcs[min(1, len(dcs) - 1)]  # "2nd of N" DCs — the brief's literal "DC2"
    dc2_name = locations.set_index("plnt_cd").loc[dc2, "plnt_nm"]

    as_of = cfg.dates.as_of_date
    gi_dates = pd.to_datetime(historical["FST_PLAN_GI_DT"]).dt.date

    last_month_end = as_of.replace(day=1) - dt.timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    month_idx = historical.index[(gi_dates >= last_month_start) & (gi_dates <= last_month_end)]
    if len(month_idx) == 0:
        return None
    historical.loc[month_idx, "PLNT_CD"] = dc2
    historical.loc[month_idx, "PLNT_NM"] = dc2_name
    _recompute_cut_split(historical, month_idx, rng.uniform(0.5, 0.85, size=len(month_idx)))

    last_week_start = as_of - dt.timedelta(days=7)
    week_idx = historical.index[(gi_dates >= last_week_start) & (gi_dates <= as_of)]
    chosen_sku = None
    if len(week_idx) > 0:
        chosen_sku = rng.choice(historical.loc[week_idx, "MATERIAL"].to_numpy())
        sku_week_idx = week_idx[historical.loc[week_idx, "MATERIAL"] == chosen_sku]
        historical.loc[sku_week_idx, "PLNT_CD"] = dc2
        historical.loc[sku_week_idx, "PLNT_NM"] = dc2_name
        _recompute_cut_split(historical, sku_week_idx, rng.uniform(0.5, 0.8, size=len(sku_week_idx)))

    return {
        "dc": dc2, "last_month_start": last_month_start, "last_month_end": last_month_end,
        "chosen_sku": chosen_sku, "last_week_start": last_week_start,
    }


def _apply_banner_block(rng: np.random.Generator, tables: Dict[str, pd.DataFrame]) -> Optional[dict]:
    """Q16 (block rate by code) + Q17 (customers with most blocked orders)."""
    shipments = tables["shipments"]
    banners = shipments["KEY_CUST_NUM"].unique()
    if len(banners) == 0:
        return None
    banner = rng.choice(banners)
    code, desc = DELIVERY_BLOCK_CODES[rng.integers(0, len(DELIVERY_BLOCK_CODES))]

    banner_idx = shipments.index[shipments["KEY_CUST_NUM"] == banner]
    if len(banner_idx) == 0:
        return None
    k = max(1, int(len(banner_idx) * 0.6))
    pin_idx = rng.choice(banner_idx, size=k, replace=False)
    shipments.loc[pin_idx, "DELIVERY_BLOCK_CD"] = code
    shipments.loc[pin_idx, "DELIVERY_BLOCK_DESC"] = desc
    return {"banner": banner, "block_code": code, "block_desc": desc, "rows_pinned": k}


def _apply_yellow_to_red(rng: np.random.Generator, tables: Dict[str, pd.DataFrame]) -> Optional[dict]:
    """Q24-26 — several SKUs move Yellow to Red in the latest V-report week."""
    vuln = tables["vulnerability"]
    current = vuln[vuln["HORIZON_OFFSET"] == 0]
    weeks = sorted(current["WEEK_START_DATE"].unique())
    if len(weeks) < 2:
        return None
    latest_week, prior_week = weeks[-1], weeks[-2]

    materials_pool = vuln["MATERIAL"].unique()
    num_skus = min(5, len(materials_pool))
    if num_skus == 0:
        return None
    chosen = rng.choice(materials_pool, size=num_skus, replace=False)

    prior_idx = vuln.index[(vuln["HORIZON_OFFSET"] == 0) & vuln["WEEK_START_DATE"].eq(prior_week)
                           & vuln["MATERIAL"].isin(chosen)]
    latest_idx = vuln.index[(vuln["HORIZON_OFFSET"] == 0) & vuln["WEEK_START_DATE"].eq(latest_week)
                            & vuln["MATERIAL"].isin(chosen)]
    # also propagate into the forward horizon (HORIZON_OFFSET >= 1) — otherwise a SKU
    # that just went Red this week shows no sign of it in "next two weeks" (Q24),
    # since horizon rows were built from PRE-scenario risk values.
    horizon_idx = vuln.index[(vuln["HORIZON_OFFSET"] >= 1) & vuln["MATERIAL"].isin(chosen)]
    if len(prior_idx) == 0 or len(latest_idx) == 0:
        return None

    for col, val in score_columns(rng, np.full(len(prior_idx), 0.55)).items():  # mid-Yellow
        vuln.loc[prior_idx, col] = val
    for col, val in score_columns(rng, np.full(len(latest_idx), 0.75)).items():  # mid-Red
        vuln.loc[latest_idx, col] = val
    if len(horizon_idx) > 0:  # persistence: stays Red into the near-term projection
        for col, val in score_columns(rng, np.full(len(horizon_idx), 0.75)).items():
            vuln.loc[horizon_idx, col] = val

    return {"materials": chosen.tolist(), "prior_week": prior_week, "latest_week": latest_week}


def _apply_over_allocation(rng: np.random.Generator, tables: Dict[str, pd.DataFrame]) -> Optional[dict]:
    """Q20 (customer over 90% allocation consumed) + Q23 (why customer Y got less)."""
    allocation = tables["allocation"]
    historical = tables["historical"]
    dim_product = tables["dim_product"]

    parents = allocation["PARENT_CODE"].unique()
    groups = allocation["CUSTOMER_GROUP"].unique()
    if len(parents) == 0 or len(groups) == 0:
        return None
    parent = rng.choice(parents)
    group = rng.choice(groups)

    idx = allocation.index[(allocation["PARENT_CODE"] == parent) & (allocation["CUSTOMER_GROUP"] == group)]
    if len(idx) == 0:
        return None

    # ALLOC_STATUS is a parent-level fact (see allocation.py) — validate.py checks it
    # stays uniform across every CUSTOMER_GROUP for a given parent/date/period, so the
    # "on allocation" flag must be broadcast to the whole parent, not just this group.
    parent_idx = allocation.index[allocation["PARENT_CODE"] == parent]
    allocation.loc[parent_idx, "ALLOC_STATUS"] = "On Allocation"
    allocation.loc[parent_idx, "KC"] = "SS"
    allocation.loc[parent_idx, "KC_DESC"] = "Short Supply"

    pct = rng.uniform(92, 98, size=len(idx))
    allocated = allocation.loc[idx, "ALLOCATED_QTY"].to_numpy()
    ordered = np.round(allocated * pct / 100.0)
    allocation.loc[idx, "ORDERED_QTY"] = ordered
    allocation.loc[idx, "REMAINING_QTY"] = np.clip(allocated - ordered, 0, None)
    allocation.loc[idx, "PCT_CONSUMED"] = np.round(pct, 1)

    materials_under_parent = dim_product.loc[dim_product["material_parent_cd"] == parent, "material"].tolist()
    hist_idx = pd.Index([])
    if materials_under_parent:
        hist_idx = historical.index[
            historical["MATERIAL"].isin(materials_under_parent) & (historical["CUST_SEG_CD"] == group)
        ]
    if len(hist_idx) > 0:
        k2 = min(len(hist_idx), max(1, len(hist_idx) // 3))
        pin_idx = rng.choice(hist_idx, size=k2, replace=False)
        _recompute_cut_split(historical, pin_idx, rng.uniform(0.4, 0.7, size=k2))

    return {"parent_code": parent, "customer_group": group}


def _apply_late_gi(rng: np.random.Generator, cfg, tables: Dict[str, pd.DataFrame]) -> Optional[dict]:
    """Q14 (worst on-time DC this quarter) + Q15 (why on-time fell in week N)."""
    historical = tables["historical"]
    locations = tables["dim_location"]
    dcs = locations.loc[locations["is_distribution_center"], "plnt_cd"].tolist()
    if not dcs:
        return None
    dc = rng.choice(dcs)

    as_of = cfg.dates.as_of_date
    week_start = as_of - dt.timedelta(days=21)
    week_end = as_of - dt.timedelta(days=15)
    gi_dates = pd.to_datetime(historical["FST_PLAN_GI_DT"]).dt.date
    idx = historical.index[(historical["PLNT_CD"] == dc) & (gi_dates >= week_start) & (gi_dates <= week_end)]
    if len(idx) == 0:
        return None

    existing_req = pd.to_datetime(historical.loc[idx, "CUST_REQ_DELV_DT"])
    late_ship = existing_req + pd.to_timedelta(rng.integers(5, 10, size=len(idx)), unit="D")
    historical.loc[idx, "FST_ACTL_SHIP_DT"] = late_ship
    historical.loc[idx, "LATE_FL_MAD_IND"] = "YES"

    return {"dc": dc, "week_start": week_start, "week_end": week_end}
