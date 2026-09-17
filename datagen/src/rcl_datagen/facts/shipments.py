"""Live open-order snapshot: `rcl_agent_shipments` equivalent.

Grain: one row per order line (SALES_DOC + ITEM). Wide, because inventory is
pivoted per distribution center (ATP / QI-hold / blocked / in-transit, each
in EA and CS) — that DC x metric x unit fan-out is what drives the ~130
columns in the real table. Column casing intentionally mirrors the observed
mix (Title_Case order fields, ALL_CAPS derived/BI fields) rather than being
cleaned up — the chatbot's context-engineering layer needs to cope with the
real, messy schema, not a tidied-up one.

Two columns (`DIBI`, `DB`) were visible in the snapshot but their business
meaning was never confirmed — they're populated with small placeholder codes
here; see docs/data_dictionary and flag them with the client SME.

`JNJ_ITEM_NO` in the real table is renamed to `CLIENT_ITEM_NO` (see
dimensions/products.py docstring) since that name itself encodes the client's
identity, unlike every other observed column name.

The per-DC ATP/QI-hold/blocked/in-transit columns below are independently
randomized PER ORDER LINE (kept that way for width-fidelity to the real
table's shape) — the same SKU/DC can show a different "ATP" on different
rows. For one consistent (material, dc) ATP value, use `atp_snapshot`
(facts/atp_snapshot.py) instead.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from rcl_datagen.dimensions.locations import distribution_centers
from rcl_datagen.reference_codes import (
    BILLING_BLOCK_CODES, BILLING_BLOCK_WEIGHTS,
    CREDIT_BLOCK_CODES, CREDIT_BLOCK_WEIGHTS,
    DELIVERY_BLOCK_CODES, DELIVERY_BLOCK_WEIGHTS,
    REJECTION_CODES, REJECTION_WEIGHTS,
    gated_code_draw,
)

_HEADER_DESCRIPTIONS = ["Standard", "Manual Long Lead", "Auto Release", "Exclusion"]
_HEADER_DESC_WEIGHTS = [0.55, 0.25, 0.15, 0.05]


def _add_days(base: np.ndarray, days: np.ndarray) -> np.ndarray:
    return base + np.array([dt.timedelta(days=int(d)) for d in days])


def build_shipments(
    rng: np.random.Generator,
    cfg,
    products: pd.DataFrame,
    customers: pd.DataFrame,
    locations: pd.DataFrame,
    current_risk: pd.DataFrame,
) -> pd.DataFrame:
    n = cfg.volumes.open_order_lines
    as_of = cfg.dates.as_of_date
    dcs = distribution_centers(locations)["plnt_cd"].tolist()

    lines = products.iloc[rng.integers(0, len(products), size=n)].reset_index(drop=True)
    cust = customers.iloc[rng.integers(0, len(customers), size=n)].reset_index(drop=True)

    risk_lookup = current_risk.set_index("material")["risk_index"]
    fallback_risk = float(risk_lookup.mean()) if len(risk_lookup) else 0.1
    risk = lines["material"].map(risk_lookup).fillna(fallback_risk).to_numpy()

    # --- order identity ---------------------------------------------------
    n_docs = max(1, n // 4)
    doc_ids = (100000000 + rng.integers(0, 90000000, size=n_docs) * 10).astype(str)
    doc_for_line = doc_ids[rng.integers(0, n_docs, size=n)]
    item_for_line = rng.integers(1, 10, size=n) * 10
    item_str = np.char.zfill(item_for_line.astype(str), 6)

    # --- dates --------------------------------------------------------------
    lookback = cfg.dates.open_order_lookback_days
    created_on = _add_days(np.full(n, as_of), -rng.integers(0, lookback + 1, size=n))
    lead_days = np.clip(rng.normal(3 + risk * 10, 2.0), 1, None).astype(int)
    mad_date = _add_days(created_on, lead_days)
    gi_date = _add_days(mad_date, rng.integers(0, 3, size=n))
    req_dlv_dt = _add_days(gi_date, rng.integers(-3, 5, size=n))

    # --- quantities & cuts ----------------------------------------------------
    case_pack = lines["case_pack_size"].to_numpy()
    order_quantity = (rng.integers(1, 25, size=n) * case_pack).astype(float)

    cut_probability = np.clip(cfg.business_rules.cut_probability * (0.5 + risk), 0.0, 0.9)
    is_cut = rng.random(n) < cut_probability
    cut_fraction = rng.uniform(0.0, 0.85, size=n)
    cut_qty = np.round(order_quantity * cut_fraction / case_pack) * case_pack
    confirmed_qty = np.clip(np.where(is_cut, cut_qty, order_quantity), 0, order_quantity)

    rej_idx = np.where(is_cut, rng.choice(len(REJECTION_CODES), size=n, p=REJECTION_WEIGHTS), 0)
    rj_code = [REJECTION_CODES[i][0] for i in rej_idx]
    rj_desc = [REJECTION_CODES[i][1] for i in rej_idx]

    delv_block_cd, delv_block_desc = gated_code_draw(
        rng, n, cfg.business_rules.delivery_block_rate, DELIVERY_BLOCK_CODES, DELIVERY_BLOCK_WEIGHTS)
    bill_block_cd, bill_block_desc = gated_code_draw(
        rng, n, cfg.business_rules.billing_block_rate, BILLING_BLOCK_CODES, BILLING_BLOCK_WEIGHTS)
    cred_block_cd, cred_block_desc = gated_code_draw(
        rng, n, cfg.business_rules.credit_block_rate, CREDIT_BLOCK_CODES, CREDIT_BLOCK_WEIGHTS)

    unit_unconfirmed = order_quantity - confirmed_qty
    ufr_pct = np.where(order_quantity > 0, 100.0 * confirmed_qty / order_quantity, 0.0)

    list_price = lines["list_price"].to_numpy()
    gts_order = order_quantity * list_price
    gts_confirmed = confirmed_qty * list_price

    ship_pt = rng.choice(dcs, size=n) if dcs else np.array(["NA"] * n)
    route = np.array([f"{sp[:2]}7D{rng.integers(1, 6):02d}" for sp in ship_pt])

    df = pd.DataFrame({
        "Name_1": cust["key_cust_nm"].to_numpy(),
        "Sold_to_pt": cust["sold_to_pt"].to_numpy(),
        "Sales_Doc": doc_for_line,
        "Created_on": created_on,
        "Req_dlv_dt": req_dlv_dt,
        "Item": item_str,
        "Material": lines["material"].to_numpy(),
        "DIBI": rng.choice([12, 22, 32, 42], size=n),          # meaning unconfirmed — see docstring
        "DB": rng.choice([11, 17, 23], size=n),                 # meaning unconfirmed — see docstring
        "ItCa": rng.choice(["ZTAQ", "ZTAE"], size=n),
        "SU": rng.choice(["CS", "EA"], size=n, p=[0.7, 0.3]),
        "ShPt": ship_pt,
        "MAD_Date": mad_date,
        "GI_Date": gi_date,
        "Confirmed_Qty": confirmed_qty,
        "Order_Quantity": order_quantity,
        "Rj": rj_code,
        "Route": route,
        "PO_number": (800000 + rng.integers(0, 199999, size=n)).astype(str),
        "Delivery_Header_Description": rng.choice(_HEADER_DESCRIPTIONS, size=n, p=_HEADER_DESC_WEIGHTS),
        "Line_Block_Description": np.where(rng.random(n) < 0.04, "Exclusion", None),
        "DELIVERY_BLOCK_CD": delv_block_cd,
        "DELIVERY_BLOCK_DESC": delv_block_desc,
        "BILLING_BLOCK_CD": bill_block_cd,
        "BILLING_BLOCK_DESC": bill_block_desc,
        "CREDIT_BLOCK_CD": cred_block_cd,
        "CREDIT_BLOCK_DESC": cred_block_desc,
        "Rejection_Description": rj_desc,
        "Forward_Scheduling_Flag": rng.random(n) < 0.03,
        "MATL_SHRT_DESC": lines["material_desc"].to_numpy(),
        "SC_GBU_DESC": lines["gbu"].to_numpy(),
        "SC_FRAN_DESC": lines["franchise"].to_numpy(),
        "SC_CAT_DESC": lines["category"].to_numpy(),
        "SC_BRND_DESC": lines["brand"].to_numpy(),
        "MATL_PARNT_CD": lines["material_parent_cd"].to_numpy(),
        "MATL_PARNT_DESC": lines["material_parent_desc"].to_numpy(),
        "DSPLY_IND": np.where(rng.random(n) < 0.3, "X", None),
        "NPI_IND": np.where(lines["npi_ind"].to_numpy(), "X", None),
        "Display_Line_Flag": rng.random(n) < 0.9,
        "NPI_Line_Flag": lines["npi_ind"].to_numpy(),
        "Future_Dated_PO_Flag": rng.random(n) < cfg.business_rules.future_dated_po_rate,
        "List_price": list_price,
        "Unit_Unconfirmed": unit_unconfirmed,
        "GTS_Order": gts_order,
        "GTS_Confirmed": gts_confirmed,
        "GTS_Unconfirmed": gts_order - gts_confirmed,
        "UFR": ufr_pct,
        "FR": ufr_pct,
        "CLIENT_ITEM_NO": lines["client_item_no"].to_numpy(),
        "GBU": lines["gbu"].to_numpy(),
        "NEED_STATE_DS": lines["brand"].to_numpy() + " NS",
        "SALES_FRANCHISE": lines["category"].to_numpy() + " - " + lines["brand"].to_numpy(),
        "KEY_CUST_NUM": cust["key_cust_num"].to_numpy(),
        "KEY_CUST_NM": cust["key_cust_nm"].to_numpy(),
        "CUST_MATL_NUM": np.where(rng.random(n) < 0.6, rng.integers(500000, 599999, size=n).astype(str), None),
        "DSTN_CHN_STS_CD": lines["dstn_chn_sts_cd"].to_numpy(),
        "SHIP_DT": gi_date,
        "REPORT_REFRESHED_DT": pd.Timestamp.now(),
    })
    for col in ("Created_on", "Req_dlv_dt", "MAD_Date", "GI_Date", "SHIP_DT"):
        df[col] = pd.to_datetime(df[col])

    # --- per-DC pivoted inventory metrics --------------------------------------
    dc_risk_damp = np.clip(1.2 - risk, 0.2, 1.2)  # higher risk -> less available inventory
    network_in_transit = np.zeros(n)
    for dc in dcs:
        atp_ea = np.round(rng.gamma(shape=2.0, scale=150.0, size=n) * dc_risk_damp, 0)
        qi_hold_ea = np.round(rng.gamma(shape=0.4, scale=80.0, size=n) * (rng.random(n) < 0.2), 0)
        blocked_ea = np.round(rng.gamma(shape=0.4, scale=40.0, size=n) * (rng.random(n) < 0.15), 0)
        in_transit_ea = np.round(rng.gamma(shape=1.0, scale=200.0, size=n) * dc_risk_damp, 0)
        network_in_transit += in_transit_ea

        df[f"{dc}_ATP_EA"] = atp_ea
        df[f"{dc}_ATP_CS"] = np.round(atp_ea / case_pack, 4)
        df[f"{dc}_Inventory_QI_Hold_EA"] = qi_hold_ea
        df[f"{dc}_Inventory_QI_Hold_CS"] = np.round(qi_hold_ea / case_pack, 4)
        df[f"{dc}_Blocked_Inventory_EA"] = blocked_ea
        df[f"{dc}_Blocked_Inventory_CS"] = np.round(blocked_ea / case_pack, 4)
        df[f"{dc}_IN_TRANSIT_EA"] = in_transit_ea
        df[f"{dc}_IN_TRANSIT_CS"] = np.round(in_transit_ea / case_pack, 4)

    dc_atp_cols = [f"{dc}_ATP_EA" for dc in dcs]
    df["TOTAL_ATP_EA"] = df[dc_atp_cols].sum(axis=1) if dc_atp_cols else 0.0
    df["TOTAL_ATP_CS"] = np.round(df["TOTAL_ATP_EA"] / case_pack, 4)
    df["NETWORK_IN_TRANSIT_EA"] = network_in_transit

    return df
