"""Column-level descriptions for every generated table.

This is the machine-readable source for docs/data_dictionary.md (built by
scripts/build_data_dictionary.py) — the intended stand-in for the client's
"General Knowledge / Data Dictionary" unstructured source. Edit the
dictionaries below and rerun that script to regenerate the doc; don't hand-edit
the generated markdown.
"""
from __future__ import annotations

import re
from typing import Dict, Optional

import pandas as pd

TABLE_DESCRIPTIONS = {
    "dim_product": "Product/material hierarchy reference (GBU -> Franchise -> Category -> Brand -> Material). Generated dimension, not a direct copy of any one source table.",
    "dim_customer": "Customer hierarchy reference (Segment -> Key Customer -> Sold-to -> Ship-to). Generated dimension.",
    "dim_location": "Plant / distribution-center reference. Generated dimension.",
    "shipments": "Live open-order snapshot. Stand-in for SAP source table rcl_lab.rcl_agent_shipments.",
    "historical": "Historical order/delivery detail used for ETD lead-time modeling. Stand-in for rcl_lab.rcl_agent_cuts_tact_attr_dtl.",
    "allocation": "Daily (AM/PM) inventory allocation snapshot. Stand-in for rcl_lab.rcl_agent_osas.",
    "vulnerability": "SKU-level vulnerability/risk report. Stand-in for rcl_lab.rcl_agent_vreport.",
}

_SHIPMENTS_COLUMNS: Dict[str, str] = {
    "Name_1": "Customer name at the sold-to level.",
    "Sold_to_pt": "Sold-to party code.",
    "Sales_Doc": "Sales order document number.",
    "Created_on": "Date the order line was created.",
    "Req_dlv_dt": "Customer-requested delivery date.",
    "Item": "Order line item number within the sales document.",
    "Material": "Material (SKU) code — joins to dim_product.material.",
    "DIBI": "Code seen in the real snapshot; business meaning not confirmed. Placeholder values only.",
    "DB": "Code seen in the real snapshot; business meaning not confirmed. Placeholder values only.",
    "ItCa": "SAP item category code.",
    "SU": "Sales unit (CS = case, EA = each).",
    "ShPt": "Shipping point — joins to dim_location.plnt_cd.",
    "MAD_Date": "Material availability date.",
    "GI_Date": "Goods issue date.",
    "Confirmed_Qty": "Quantity SAP confirmed it can ship, in Order_Quantity's unit.",
    "Order_Quantity": "Quantity the customer ordered.",
    "Rj": "Rejection reason code, if the line (or part of it) was rejected.",
    "Route": "Shipping route code.",
    "PO_number": "Customer purchase-order number.",
    "Delivery_Header_Description": "Free-text delivery header category (e.g. Manual Long Lead).",
    "Line_Block_Description": "Reason the line is blocked, if any.",
    "Rejection_Description": "Text for the Rj code.",
    "Forward_Scheduling_Flag": "True if the line used forward (vs backward) scheduling.",
    "MATL_SHRT_DESC": "Material short description.",
    "SC_GBU_DESC": "Global Business Unit description — joins to dim_product.gbu.",
    "SC_FRAN_DESC": "Franchise description — joins to dim_product.franchise.",
    "SC_CAT_DESC": "Category description — joins to dim_product.category.",
    "SC_BRND_DESC": "Brand description — joins to dim_product.brand.",
    "MATL_PARNT_CD": "Parent material code — joins to dim_product.material_parent_cd and allocation.PARENT_CODE.",
    "MATL_PARNT_DESC": "Parent material description.",
    "DSPLY_IND": "Display indicator ('X' if this is a store-display SKU).",
    "NPI_IND": "New-product-introduction indicator ('X' if NPI).",
    "Display_Line_Flag": "True if this is a display line.",
    "NPI_Line_Flag": "True if this line is a new product introduction.",
    "Future_Dated_PO_Flag": "True if the PO is dated in the future relative to entry.",
    "List_price": "List price per each — joins to dim_product.list_price.",
    "Unit_Unconfirmed": "Order_Quantity minus Confirmed_Qty.",
    "GTS_Order": "Gross trade sales value of the ordered quantity (Order_Quantity x List_price). Naming inferred from context — confirm with SME.",
    "GTS_Confirmed": "Gross trade sales value of the confirmed quantity.",
    "GTS_Unconfirmed": "Gross trade sales value of the unconfirmed (shorted) quantity.",
    "UFR": "Unit fill rate, percent (0-100) = Confirmed_Qty / Order_Quantity.",
    "FR": "Fill rate, percent (0-100). Modeled identically to UFR here — confirm the real distinction with SME.",
    "CLIENT_ITEM_NO": "Client's internal item number. Renamed from the real column name (which embedded the client's identity) — see dimensions/products.py.",
    "GBU": "Global Business Unit (duplicate of SC_GBU_DESC in the real table).",
    "NEED_STATE_DS": "Consumer 'need state' description.",
    "SALES_FRANCHISE": "Combined category/brand sales-franchise label.",
    "KEY_CUST_NUM": "Key (banner-level) customer number — joins to dim_customer.key_cust_num.",
    "KEY_CUST_NM": "Key (banner-level) customer name.",
    "CUST_MATL_NUM": "Customer's own material/SKU number for this material, if on file.",
    "DSTN_CHN_STS_CD": "Distribution channel status code — joins to dim_product.dstn_chn_sts_cd.",
    "SHIP_DT": "Actual/planned ship date for this line (mirrors GI_Date here).",
    "REPORT_REFRESHED_DT": "Timestamp this snapshot was generated.",
    "TOTAL_ATP_EA": "Available-to-promise, summed across all distribution centers, in eaches.",
    "TOTAL_ATP_CS": "Available-to-promise, summed across all distribution centers, in cases.",
    "NETWORK_IN_TRANSIT_EA": "In-transit inventory, summed across all distribution centers, in eaches.",
}

_HISTORICAL_COLUMNS: Dict[str, str] = {
    "LINE_ITEM_CAT_CD": "SAP line item category code.",
    "LATE_FL_MAD_IND": "YES/NO — whether the line shipped later than its planned goods-issue date.",
    "CUST_PO_NUM": "Customer purchase-order number.",
    "GEO_CLUS_CUST_CHNL_CD": "Geographic cluster / customer channel code.",
    "CUST_SEG_CD": "Customer segment (e.g. Mass/Club, Drug & Specialty, Ecom, FC&D, Exports & All Others, Grocery).",
    "KEY_CUST_NM": "Key (banner-level) customer name.",
    "KEY_CUST_NUM": "Key (banner-level) customer number.",
    "DELV_DOC_NUM": "Delivery document number.",
    "SHIP_TO_CUST_NM": "Ship-to location name.",
    "SHIP_TO_CUST_NUM": "Ship-to location number.",
    "SOLD_TO_CUST_NM": "Sold-to customer name.",
    "DELV_HDR_BLK_CD": "Delivery header block code, if the delivery was blocked.",
    "MAD_FISC_YR_MO_NUM": "Fiscal year_month of the material-availability date, e.g. '2023_11'.",
    "MAD_FISC_YR_NBR": "Fiscal year of the material-availability date.",
    "MAD_FISC_YR_WK_NUM": "Fiscal year_week of the material-availability date, e.g. '2023_wk47'.",
    "PGI_FISC_YR_MO_NUM": "Fiscal year_month of the planned post-goods-issue date.",
    "PGI_FISC_YR_NBR": "Fiscal year of the planned post-goods-issue date.",
    "PGI_FISC_YR_WK_NUM": "Fiscal year_week of the planned post-goods-issue date.",
    "FST_ACTL_SHIP_DT": "First actual ship date. Null if the line was still open (no actual ship yet) as of generation time.",
    "ORDR_MATL_ALLOC_DT": "Date the order/material was allocated (used here as the order-creation date).",
    "FST_DELV_CRT_DT": "First delivery-created date.",
    "DATA_PRVDR_CLS_NM": "Data-provider classification. Real sample value was literally ':' — carried over verbatim; meaning unconfirmed.",
    "TRD_CSTM_MNG_CD": "Trade customer management code.",
    "DATA_PRVDR_BRK_OUT_VAL": "Data-provider breakout value (always 'Base' in the sample).",
    "DSTN_CHN_STS_CD": "Distribution channel status, combined code-description string (e.g. '31-Active Saleable').",
    "FST_PLAN_GI_DT": "First planned goods-issue date — the ETD baseline this table exists to support.",
    "MATL_DESC": "Material description.",
    "GEO_CTRY_NM": "Country of the fulfilling plant/DC.",
    "POM_SEG_DESC": "POM segment description (always 'NA' in the sample).",
    "MFG_SITE_NM": "Manufacturing site name for this material.",
    "PLNT_CD": "Fulfilling plant/DC code — joins to dim_location.plnt_cd.",
    "PLNT_NM": "Fulfilling plant/DC name.",
    "REGN_BRND_DESC": "Brand description (regional-report naming convention; same hierarchy as SC_BRND_DESC elsewhere).",
    "REGN_CAT_DESC": "Category description (regional-report naming convention).",
    "REGN_FRAN_DESC": "Franchise description (regional-report naming convention).",
    "REGN_GLOBL_BU_DESC": "Global Business Unit description (regional-report naming convention).",
}

_ALLOCATION_COLUMNS: Dict[str, str] = {
    "SAP_MOD": "SAP module/document reference for this allocation record.",
    "PARENT_CODE": "Allocation-parent product code — joins to dim_product.material_parent_cd.",
    "ALLOCATION_LEVEL": "Allocation grouping level code (e.g. ZREDPAR = parent-level).",
    "SAP_DESC": "SAP description field (null in every sampled real row).",
    "PARENT_DESC": "Parent product description.",
    "EACH_UPC": "UPC at the each level.",
    "CASE_UPC": "UPC at the case level.",
    "SC_GBU": "Global Business Unit.",
    "SC_FRANCHISE": "Franchise.",
    "SC_BRAND": "Brand.",
    "POM_4_BOX": "POM 4-box classification (value was truncated in the real snapshot; reproduced as a generic label here).",
    "PSE": "Code seen in the real snapshot; business meaning not confirmed (always null in the sample).",
    "ALLOC_STATUS": "'On Allocation' if the parent is supply-constrained this period, else null. INVENTED domain — real values never appeared in the sample.",
    "KC": "Allocation reason code. INVENTED domain — see docs note.",
    "KC_DESC": "Text for the KC code. INVENTED domain.",
    "MONTHYEAR": "Month/year of CALENDAR_DT, e.g. '9/2026'.",
    "CALENDAR_DT": "Calendar date of this allocation snapshot.",
    "PERIOD": "AM or PM — allocation appears to be evaluated twice daily.",
}

_VULNERABILITY_COLUMNS: Dict[str, str] = {
    "WEEK_START_DATE": "Monday date of the fiscal week.",
    "CALYEAR": "Calendar year.",
    "FISCPER": "Fiscal period, compact format e.g. '2026008'.",
    "CALWEEK": "Calendar year+week, compact format e.g. '202632'.",
    "WEEK_NUM": "ISO week number.",
    "NATIONAL_CODE": "National code (null in the sample).",
    "EANUPC": "EAN/UPC of the material.",
    "MATERIAL": "Material (SKU) code — joins to dim_product.material.",
    "MATERIAL_DESC": "Material description.",
    "AS_REGION": "Region (always 'NA' in the sample).",
    "AS_COO": "Country of origin/manufacture.",
    "AS_OP_CO": "Operating company.",
    "AS_GBU": "Global Business Unit.",
    "AS_SUB_GBU": "Sub-GBU grouping. Column name inferred — the real header was truncated in the screenshot.",
    "SINGLE_SOURCE_FLAG": "INVENTED — true if the material has only one qualified supplier/site.",
    "SAFETY_STOCK_DAYS": "INVENTED — days of safety stock currently held.",
    "DAYS_OF_SUPPLY": "INVENTED — total days of supply on hand plus in transit.",
    "BACKORDER_RISK_SCORE": "INVENTED — 0-100 backorder risk score.",
    "FORECAST_ERROR_PCT": "INVENTED — recent forecast error, percent.",
    "OPEN_PO_COVERAGE_DAYS": "INVENTED — days of demand covered by open purchase orders.",
    "RISK_TIER": "INVENTED — Low/Medium/High/Critical, derived from the underlying risk index.",
}

_DIM_PRODUCT_COLUMNS: Dict[str, str] = {
    "material": "Material (SKU) code. Primary key.",
    "client_item_no": "Client's internal item number (assumed identical to material — see products.py).",
    "material_parent_cd": "Parent material code, groups variants (e.g. sizes/scents) of the same item.",
    "material_desc": "Material description.",
    "material_parent_desc": "Parent material description.",
    "gbu": "Global Business Unit.",
    "franchise": "Franchise.",
    "category": "Category.",
    "brand": "Brand (fictitious — see namers.py).",
    "each_upc": "UPC at the each level.",
    "case_upc": "UPC at the case level.",
    "case_pack_size": "Number of eaches per case — used to convert EA <-> CS everywhere.",
    "list_price": "List price per each.",
    "npi_ind": "True if this is a new product introduction.",
    "dstn_chn_sts_cd": "Distribution channel status code.",
    "dstn_chn_sts_desc": "Distribution channel status description.",
    "mfg_plnt_cd": "Manufacturing plant code — joins to dim_location.plnt_cd.",
}

_DIM_CUSTOMER_COLUMNS: Dict[str, str] = {
    "key_cust_num": "Key (banner-level) customer number.",
    "key_cust_nm": "Key (banner-level) customer name (fictitious).",
    "sold_to_pt": "Sold-to party code.",
    "sold_to_nm": "Sold-to name.",
    "ship_to_num": "Ship-to location number.",
    "ship_to_nm": "Ship-to location name.",
    "cust_seg_cd": "Customer segment.",
    "geo_clus_cust_chnl_cd": "Geographic cluster / customer channel code.",
}

_DIM_LOCATION_COLUMNS: Dict[str, str] = {
    "plnt_cd": "Plant/DC code. Primary key.",
    "plnt_nm": "Plant/DC name, incl. 3PL operator (fictitious).",
    "is_distribution_center": "True if this site holds sellable inventory (used for the shipments per-DC columns).",
    "is_manufacturing_site": "True if this site manufactures product.",
    "geo_ctry_nm": "Country.",
}

_TABLE_COLUMN_DOCS = {
    "dim_product": _DIM_PRODUCT_COLUMNS,
    "dim_customer": _DIM_CUSTOMER_COLUMNS,
    "dim_location": _DIM_LOCATION_COLUMNS,
    "shipments": _SHIPMENTS_COLUMNS,
    "historical": _HISTORICAL_COLUMNS,
    "allocation": _ALLOCATION_COLUMNS,
    "vulnerability": _VULNERABILITY_COLUMNS,
}

_DC_PIVOT_PATTERN = re.compile(
    r"^(?P<dc>[A-Za-z0-9]+)_(?P<metric>ATP|Inventory_QI_Hold|Blocked_Inventory|IN_TRANSIT)_(?P<unit>EA|CS)$"
)
_DC_METRIC_TEXT = {
    "ATP": "Available-to-promise inventory",
    "Inventory_QI_Hold": "Inventory on quality-inspection hold",
    "Blocked_Inventory": "Blocked (unavailable) inventory",
    "IN_TRANSIT": "In-transit inventory",
}


def describe_column(table: str, column: str) -> Optional[str]:
    known = _TABLE_COLUMN_DOCS.get(table, {})
    if column in known:
        return known[column]

    if table == "shipments":
        m = _DC_PIVOT_PATTERN.match(column)
        if m:
            unit = "cases" if m.group("unit") == "CS" else "eaches"
            return f"{_DC_METRIC_TEXT[m.group('metric')]} at distribution center {m.group('dc')}, in {unit}."

    return None


def build_data_dictionary(tables: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """One row per (table, column) in the ACTUAL generated tables, so the doc
    never drifts from the code that produces it."""
    rows = []
    for table, df in tables.items():
        for column in df.columns:
            example = df[column].dropna().iloc[0] if df[column].notna().any() else None
            rows.append({
                "table": table,
                "column": column,
                "dtype": str(df[column].dtype),
                "example_value": example,
                "description": describe_column(table, column) or "Not yet documented — confirm with SME.",
            })
    return pd.DataFrame(rows)
