"""Historical order/delivery detail: `rcl_agent_cuts_tact_attr_dtl` equivalent.

Grain: one row per historical order/delivery line, spanning
dates.history_start..dates.history_end (2-3 years / ~30M rows in the real
table). This generator produces a much smaller, stratified stand-in sized by
volumes.historical_rows — see README for why full production volume isn't
replicated for a PoC.

The planned-vs-actual date triple (FST_PLAN_GI_DT / FST_ACTL_SHIP_DT /
FST_DELV_CRT_DT) is what an ETD model would learn from, so lead times are
drawn from a per-lane (customer segment x plant/DC) baseline plus noise
rather than being independently random per row — that is what makes "similar
order items" produce a coherent estimated-delivery pattern instead of noise.
The same material-week risk_index used by allocation/vulnerability nudges
lead time and lateness here too, for the same cross-table-consistency reason.

MATERIAL / ORDR_QTY / DELV_QTY / CUT_QTY / cut+rejection reasons /
CANCELLED_FL / ORDR_TYPE / ORDR_VAL / DELV_VAL / CUST_REQ_DELV_DT are
INVENTED — the real snapshot never showed any quantity, value, or reason
field on this table (only dates, IDs and descriptions), even though its name
("cuts_tact_attr_dtl") implies cuts belong here. Added because fill-rate/cut/
rejection/cancellation questions need them. The primary cut reason is biased
toward "Allocation" when the material's parent was realized on-allocation
that week (see the allocation-linkage below) so the cut genuinely traces
back to a cause instead of being a coincidental correlation.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from rcl_datagen.dimensions.locations import distribution_centers
from rcl_datagen.reference_codes import (
    CANCELLATION_REASON_CODES, CANCELLATION_REASON_WEIGHTS,
    CUT_REASON_CODES, CUT_REASON_WEIGHTS,
    DELIVERY_BLOCK_CODES, DELIVERY_BLOCK_WEIGHTS,
    ORDER_TYPE_CODES, ORDER_TYPE_WEIGHTS,
    REJECTION_CODES,
    gated_code_draw,
)

# Non-None rejection codes only, re-weighted — historical gates "does a
# rejection apply at all" via its own cfg-driven rate rather than reusing
# shipments.py's baked-in None-heavy weights.
_REJECTION_CODES_ONLY = [c for c in REJECTION_CODES if c[0] is not None]
_REJECTION_WEIGHTS_ONLY = [0.6, 0.25, 0.15]


def _add_days(base: np.ndarray, days: np.ndarray) -> np.ndarray:
    return base + np.array([dt.timedelta(days=int(d)) for d in days])


def build_historical(
    rng: np.random.Generator,
    cfg,
    products: pd.DataFrame,
    customers: pd.DataFrame,
    locations: pd.DataFrame,
    risk: pd.DataFrame,  # material x week_start_date x risk_index
    allocation: pd.DataFrame,
) -> pd.DataFrame:
    n = cfg.volumes.historical_rows
    start, end = cfg.dates.history_start, cfg.dates.history_end
    span_days = (end - start).days

    lines = products.iloc[rng.integers(0, len(products), size=n)].reset_index(drop=True)
    cust = customers.iloc[rng.integers(0, len(customers), size=n)].reset_index(drop=True)
    dcs = distribution_centers(locations).reset_index(drop=True)
    dc_for_line = dcs.iloc[rng.integers(0, len(dcs), size=n)].reset_index(drop=True)

    order_created = _add_days(np.full(n, start), rng.integers(0, span_days + 1, size=n))

    # per-lane (segment x plant) baseline lead time, so similar lanes behave alike
    lane_df = pd.DataFrame(
        [(seg, plnt, rng.uniform(2.0, 10.0)) for seg in cust["cust_seg_cd"].unique() for plnt in dcs["plnt_cd"]],
        columns=["cust_seg_cd", "plnt_cd", "lane_base_lead"],
    )
    lane_lookup = pd.DataFrame({
        "cust_seg_cd": cust["cust_seg_cd"].to_numpy(),
        "plnt_cd": dc_for_line["plnt_cd"].to_numpy(),
    }).merge(lane_df, on=["cust_seg_cd", "plnt_cd"], how="left")
    base_lead = lane_lookup["lane_base_lead"].to_numpy()

    # fold in material risk at the order's week (vectorized left-join; misses default to a low baseline)
    week_of = pd.to_datetime(order_created).to_period("W-SUN").start_time.date
    risk_lookup = pd.DataFrame({
        "material": lines["material"].to_numpy(),
        "week_start_date": week_of,
    }).merge(risk, on=["material", "week_start_date"], how="left")
    material_risk = risk_lookup["risk_index"].fillna(0.15).to_numpy()

    plan_lead_days = np.clip(rng.normal(base_lead + material_risk * 6, 1.5), 1, None)
    plan_gi_date = _add_days(order_created, plan_lead_days.astype(int))
    delv_created = _add_days(order_created, np.clip(plan_lead_days - rng.integers(0, 3, size=n), 0, None).astype(int))

    is_open = rng.random(n) < cfg.business_rules.historical_open_rate
    actual_noise_days = rng.normal(material_risk * 4, 2.0).astype(int)
    actual_ship_date = _add_days(plan_gi_date, actual_noise_days)
    late_flag = np.where(~is_open & (actual_ship_date > plan_gi_date), "YES", "NO")

    actual_ship_dt = pd.to_datetime(pd.Series(actual_ship_date))
    actual_ship_dt = actual_ship_dt.where(~is_open)  # NaT while still "open" (no actual ship yet)

    mad_week = pd.to_datetime(order_created).isocalendar()
    pgi_week = pd.to_datetime(plan_gi_date).isocalendar()

    # --- allocation linkage: was this line's material's parent flagged --------
    # "on allocation" during the week its planned GI date falls in? Makes
    # cut_reason "Allocation" a real, joinable answer (see module docstring).
    alloc_week = (
        allocation.assign(
            week_start_date=pd.to_datetime(allocation["CALENDAR_DT"])
            .dt.to_period("W-SUN").dt.start_time.dt.date
        )
        .groupby(["PARENT_CODE", "week_start_date"])["ALLOC_STATUS"]
        .apply(lambda s: bool((s == "On Allocation").any()))
        .reset_index(name="parent_on_allocation")
    )
    pgi_week_of = pd.to_datetime(plan_gi_date).to_period("W-SUN").start_time.date
    parent_on_allocation = (
        pd.DataFrame({"PARENT_CODE": lines["material_parent_cd"].to_numpy(), "week_start_date": pgi_week_of})
        .merge(alloc_week, on=["PARENT_CODE", "week_start_date"], how="left")["parent_on_allocation"]
        .infer_objects(copy=False)
        .fillna(False)
        .astype(bool)
        .to_numpy()
    )

    # --- order type, cancellation, rejection -----------------------------------
    order_qty = rng.integers(4, 200, size=n).astype(float)  # cases
    type_idx = rng.choice(len(ORDER_TYPE_CODES), size=n, p=ORDER_TYPE_WEIGHTS)
    ordr_type_cd = np.array([ORDER_TYPE_CODES[i][0] for i in type_idx])
    ordr_type_desc = np.array([ORDER_TYPE_CODES[i][1] for i in type_idx])

    cancelled = rng.random(n) < cfg.business_rules.historical_cancellation_rate
    cancelled_fl = np.where(cancelled, "YES", "NO")
    cancel_rsn_idx = rng.choice(len(CANCELLATION_REASON_CODES), size=n, p=CANCELLATION_REASON_WEIGHTS)
    cancelled_rsn_cd = np.where(cancelled, [CANCELLATION_REASON_CODES[i][0] for i in cancel_rsn_idx], None)
    cancelled_rsn_desc = np.where(cancelled, [CANCELLATION_REASON_CODES[i][1] for i in cancel_rsn_idx], None)

    rejected = ~cancelled & (rng.random(n) < cfg.business_rules.historical_rejection_rate)
    rej_prim_idx = rng.choice(len(_REJECTION_CODES_ONLY), size=n, p=_REJECTION_WEIGHTS_ONLY)
    rjctn_rsn_prim_cd = np.where(rejected, [_REJECTION_CODES_ONLY[i][0] for i in rej_prim_idx], None)
    rjctn_rsn_prim_desc = np.where(rejected, [_REJECTION_CODES_ONLY[i][1] for i in rej_prim_idx], None)
    has_seco_rej = rejected & (rng.random(n) < 0.25)
    rej_seco_idx = rng.choice(len(_REJECTION_CODES_ONLY), size=n, p=_REJECTION_WEIGHTS_ONLY)
    rjctn_rsn_seco_cd = np.where(has_seco_rej, [_REJECTION_CODES_ONLY[i][0] for i in rej_seco_idx], None)
    rjctn_rsn_seco_desc = np.where(has_seco_rej, [_REJECTION_CODES_ONLY[i][1] for i in rej_seco_idx], None)

    # --- cuts, biased toward "Allocation" when the parent was on-allocation ----
    cut_probability = np.clip(cfg.business_rules.historical_cut_probability * (0.5 + material_risk), 0.0, 0.9)
    is_cut = ~cancelled & ~rejected & (rng.random(n) < cut_probability)

    cats = len(CUT_REASON_CODES)
    alloc_cat_idx = next(i for i, c in enumerate(CUT_REASON_CODES) if c[1] == "Allocation")
    base_w = np.array(CUT_REASON_WEIGHTS, dtype=float)
    other_idx = [i for i in range(cats) if i != alloc_cat_idx]
    boosted_w = base_w.copy()
    boosted_w[alloc_cat_idx] = cfg.business_rules.allocation_cut_bias
    boosted_w[other_idx] = (
        (1.0 - cfg.business_rules.allocation_cut_bias) * (base_w[other_idx] / base_w[other_idx].sum())
    )

    row_w = np.where(parent_on_allocation[:, None], boosted_w[None, :], base_w[None, :])
    cum_w = np.cumsum(row_w, axis=1)
    u = rng.random(n) * cum_w[:, -1]
    cut_rsn_idx = np.clip((u[:, None] > cum_w).sum(axis=1), 0, cats - 1)
    cut_rsn_prim_cd = np.where(is_cut, [CUT_REASON_CODES[i][0] for i in cut_rsn_idx], None)
    cut_rsn_prim_desc = np.where(is_cut, [CUT_REASON_CODES[i][1] for i in cut_rsn_idx], None)

    has_seco_cut = is_cut & (rng.random(n) < 0.25)
    cut_seco_idx = rng.choice(cats, size=n, p=CUT_REASON_WEIGHTS)
    cut_rsn_seco_cd = np.where(has_seco_cut, [CUT_REASON_CODES[i][0] for i in cut_seco_idx], None)
    cut_rsn_seco_desc = np.where(has_seco_cut, [CUT_REASON_CODES[i][1] for i in cut_seco_idx], None)

    # --- quantities/values — DELV_QTY defined first so CUT_QTY == ORDR_QTY - DELV_QTY holds exactly ---
    cancel_or_reject = cancelled | rejected
    cut_fraction = rng.uniform(0.05, 0.85, size=n)
    delv_qty = np.where(
        cancel_or_reject, 0.0,
        np.where(is_cut, np.round(order_qty * (1 - cut_fraction)), order_qty),
    )
    cut_qty = order_qty - delv_qty
    list_price = lines["list_price"].to_numpy()
    ordr_val = order_qty * list_price
    delv_val = delv_qty * list_price

    cust_req_delv_dt = _add_days(plan_gi_date, rng.integers(-3, 5, size=n))

    delv_hdr_blk_cd, delv_hdr_blk_desc = gated_code_draw(
        rng, n, cfg.business_rules.delivery_block_rate, DELIVERY_BLOCK_CODES, DELIVERY_BLOCK_WEIGHTS)

    df = pd.DataFrame({
        "LINE_ITEM_CAT_CD": rng.choice(["TAN", "ZTAN", "REN"], size=n, p=[0.8, 0.15, 0.05]),
        "LATE_FL_MAD_IND": late_flag,
        "CUST_PO_NUM": rng.integers(1000000, 9999999, size=n).astype(str),
        "GEO_CLUS_CUST_CHNL_CD": cust["geo_clus_cust_chnl_cd"].to_numpy(),
        "CUST_SEG_CD": cust["cust_seg_cd"].to_numpy(),
        "KEY_CUST_NM": cust["key_cust_nm"].to_numpy(),
        "KEY_CUST_NUM": cust["key_cust_num"].to_numpy(),
        "DELV_DOC_NUM": (800000000 + rng.integers(0, 99999999, size=n)).astype(str),
        "SHIP_TO_CUST_NM": cust["ship_to_nm"].to_numpy(),
        "SHIP_TO_CUST_NUM": cust["ship_to_num"].to_numpy(),
        "SOLD_TO_CUST_NM": cust["sold_to_nm"].to_numpy(),
        "DELV_HDR_BLK_CD": delv_hdr_blk_cd,
        "DELV_HDR_BLK_DESC": delv_hdr_blk_desc,
        "MAD_FISC_YR_MO_NUM": [f"{d.year}_{d.month:02d}" for d in order_created],
        "MAD_FISC_YR_NBR": mad_week["year"].to_numpy(),
        "MAD_FISC_YR_WK_NUM": [f"{y}_wk{w:02d}" for y, w in zip(mad_week["year"], mad_week["week"])],
        "PGI_FISC_YR_MO_NUM": [f"{d.year}_{d.month:02d}" for d in plan_gi_date],
        "PGI_FISC_YR_NBR": pgi_week["year"].to_numpy(),
        "PGI_FISC_YR_WK_NUM": [f"{y}_wk{w:02d}" for y, w in zip(pgi_week["year"], pgi_week["week"])],
        "FST_ACTL_SHIP_DT": actual_ship_dt.to_numpy(),
        "ORDR_MATL_ALLOC_DT": pd.to_datetime(order_created),
        "FST_DELV_CRT_DT": pd.to_datetime(delv_created),
        "DATA_PRVDR_CLS_NM": ":",  # verbatim odd placeholder seen in the sample — meaning unconfirmed
        "TRD_CSTM_MNG_CD": np.where(rng.random(n) < 0.1, "N", None),
        "DATA_PRVDR_BRK_OUT_VAL": "Base",
        "DSTN_CHN_STS_CD": lines["dstn_chn_sts_cd"].to_numpy() + "-" + lines["dstn_chn_sts_desc"].to_numpy(),
        "FST_PLAN_GI_DT": pd.to_datetime(plan_gi_date),
        "MATL_DESC": lines["material_desc"].to_numpy(),
        "GEO_CTRY_NM": dc_for_line["geo_ctry_nm"].to_numpy(),
        "POM_SEG_DESC": "NA",
        "MFG_SITE_NM": lines["mfg_plnt_cd"].map(locations.set_index("plnt_cd")["plnt_nm"]).to_numpy(),
        "PLNT_CD": dc_for_line["plnt_cd"].to_numpy(),
        "PLNT_NM": dc_for_line["plnt_nm"].to_numpy(),
        "REGN_BRND_DESC": lines["brand"].to_numpy(),
        "REGN_CAT_DESC": lines["category"].to_numpy(),
        "REGN_FRAN_DESC": lines["franchise"].to_numpy(),
        "REGN_GLOBL_BU_DESC": lines["gbu"].to_numpy(),
        "MATERIAL": lines["material"].to_numpy(),
        "ORDR_QTY": order_qty,
        "DELV_QTY": delv_qty,
        "CUT_QTY": cut_qty,
        "ORDR_VAL": ordr_val,
        "DELV_VAL": delv_val,
        "ORDR_TYPE_CD": ordr_type_cd,
        "ORDR_TYPE_DESC": ordr_type_desc,
        "CANCELLED_FL": cancelled_fl,
        "CANCELLED_RSN_CD": cancelled_rsn_cd,
        "CANCELLED_RSN_DESC": cancelled_rsn_desc,
        "CUT_RSN_PRIM_CD": cut_rsn_prim_cd,
        "CUT_RSN_PRIM_DESC": cut_rsn_prim_desc,
        "CUT_RSN_SECO_CD": cut_rsn_seco_cd,
        "CUT_RSN_SECO_DESC": cut_rsn_seco_desc,
        "RJCTN_RSN_PRIM_CD": rjctn_rsn_prim_cd,
        "RJCTN_RSN_PRIM_DESC": rjctn_rsn_prim_desc,
        "RJCTN_RSN_SECO_CD": rjctn_rsn_seco_cd,
        "RJCTN_RSN_SECO_DESC": rjctn_rsn_seco_desc,
        "CUST_REQ_DELV_DT": pd.to_datetime(cust_req_delv_dt),
    })
    return df
