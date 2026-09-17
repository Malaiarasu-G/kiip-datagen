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
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from rcl_datagen.dimensions.locations import distribution_centers

_DELV_BLOCK_CODES = [None, None, None, "01", "02"]  # mostly unblocked


def _add_days(base: np.ndarray, days: np.ndarray) -> np.ndarray:
    return base + np.array([dt.timedelta(days=int(d)) for d in days])


def build_historical(
    rng: np.random.Generator,
    cfg,
    products: pd.DataFrame,
    customers: pd.DataFrame,
    locations: pd.DataFrame,
    risk: pd.DataFrame,  # material x week_start_date x risk_index
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
        "DELV_HDR_BLK_CD": rng.choice(_DELV_BLOCK_CODES, size=n),
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
    })
    return df
