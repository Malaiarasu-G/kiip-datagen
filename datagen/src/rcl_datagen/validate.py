"""Referential-integrity and business-rule sanity checks over the generated tables.

Run automatically at the end of scripts/generate.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd


@dataclass
class ValidationReport:
    checks: List[str] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)

    def check(self, description: str, passed: bool) -> None:
        self.checks.append(description)
        if not passed:
            self.failures.append(description)

    @property
    def ok(self) -> bool:
        return not self.failures

    def print_summary(self) -> None:
        print(f"\nValidation: {len(self.checks) - len(self.failures)}/{len(self.checks)} checks passed")
        for f in self.failures:
            print(f"  FAILED: {f}")


def validate(
    tables: Dict[str, pd.DataFrame],
    report: Optional[ValidationReport] = None,
    scenario_keys: Optional[dict] = None,
) -> ValidationReport:
    report = report or ValidationReport()

    dim_product = tables["dim_product"]
    dim_customer = tables["dim_customer"]
    dim_location = tables["dim_location"]

    shipments = tables["shipments"]
    historical = tables["historical"]
    allocation = tables["allocation"]
    vulnerability = tables["vulnerability"]
    atp_snapshot = tables.get("atp_snapshot")
    inbound_schedule = tables.get("inbound_schedule")

    report.check("shipments has rows", len(shipments) > 0)
    report.check(
        "shipments.Material all exist in dim_product",
        bool(shipments["Material"].isin(dim_product["material"]).all()),
    )
    report.check(
        "shipments.Confirmed_Qty <= Order_Quantity",
        bool((shipments["Confirmed_Qty"] <= shipments["Order_Quantity"] + 1e-6).all()),
    )
    report.check(
        "shipments date order: Created_on <= MAD_Date <= GI_Date",
        bool((shipments["Created_on"] <= shipments["MAD_Date"]).all())
        and bool((shipments["MAD_Date"] <= shipments["GI_Date"]).all()),
    )

    report.check("historical has rows", len(historical) > 0)
    report.check(
        "historical.MATL_DESC values all trace back to dim_product",
        bool(historical["MATL_DESC"].isin(dim_product["material_desc"]).all()),
    )
    report.check(
        "historical.MATERIAL all exist in dim_product",
        bool(historical["MATERIAL"].isin(dim_product["material"]).all()),
    )
    report.check(
        "historical.FST_PLAN_GI_DT >= ORDR_MATL_ALLOC_DT (order date)",
        bool((historical["FST_PLAN_GI_DT"] >= historical["ORDR_MATL_ALLOC_DT"]).all()),
    )
    non_open = historical["FST_ACTL_SHIP_DT"].notna()
    report.check(
        "historical.LATE_FL_MAD_IND agrees with actual-vs-planned date where not open",
        bool((
            (historical.loc[non_open, "LATE_FL_MAD_IND"] == "YES")
            == (historical.loc[non_open, "FST_ACTL_SHIP_DT"] > historical.loc[non_open, "FST_PLAN_GI_DT"])
        ).all()),
    )
    report.check(
        "historical.DELV_QTY <= ORDR_QTY",
        bool((historical["DELV_QTY"] <= historical["ORDR_QTY"] + 1e-6).all()),
    )
    report.check(
        "historical.CUT_QTY == ORDR_QTY - DELV_QTY",
        bool(((historical["ORDR_QTY"] - historical["DELV_QTY"] - historical["CUT_QTY"]).abs() < 1e-6).all()),
    )
    report.check(
        "historical.DELV_VAL <= ORDR_VAL",
        bool((historical["DELV_VAL"] <= historical["ORDR_VAL"] + 1e-6).all()),
    )
    report.check(
        "historical.CANCELLED_FL only YES/NO",
        bool(historical["CANCELLED_FL"].isin(["YES", "NO"]).all()),
    )
    cancelled_rows = historical["CANCELLED_FL"] == "YES"
    report.check(
        "historical.CANCELLED_RSN_CD populated iff CANCELLED_FL == 'YES'",
        bool((historical["CANCELLED_RSN_CD"].notna() == cancelled_rows).all()),
    )
    report.check(
        "historical.ORDR_TYPE_DESC only known order types",
        bool(historical["ORDR_TYPE_DESC"].isin(
            ["Standard", "Return", "Free Goods", "Sample", "Intercompany"]
        ).all()),
    )

    report.check("allocation has rows", len(allocation) > 0)
    report.check(
        "allocation.PARENT_CODE all exist in dim_product parents",
        bool(allocation["PARENT_CODE"].isin(dim_product["material_parent_cd"]).all()),
    )
    report.check("allocation.PERIOD only AM/PM", bool(allocation["PERIOD"].isin(["AM", "PM"]).all()))
    report.check(
        "allocation.CUSTOMER_GROUP only known customer segments",
        bool(allocation["CUSTOMER_GROUP"].isin(dim_customer["cust_seg_cd"]).all()),
    )
    report.check("allocation.REMAINING_QTY >= 0", bool((allocation["REMAINING_QTY"] >= 0).all()))
    report.check(
        "allocation.PCT_CONSUMED in a sane range",
        bool(((allocation["PCT_CONSUMED"] >= 0) & (allocation["PCT_CONSUMED"] <= 250)).all()),
    )
    alloc_status_uniform = (
        allocation.groupby(["PARENT_CODE", "CALENDAR_DT", "PERIOD"])["ALLOC_STATUS"]
        .transform(lambda s: s.nunique(dropna=False) == 1)
    )
    report.check(
        "allocation.ALLOC_STATUS is uniform across CUSTOMER_GROUP for a given parent/date/period",
        bool(alloc_status_uniform.all()),
    )

    report.check("vulnerability has rows", len(vulnerability) > 0)
    report.check(
        "vulnerability.MATERIAL all exist in dim_product",
        bool(vulnerability["MATERIAL"].isin(dim_product["material"]).all()),
    )
    report.check(
        "vulnerability.RISK_TIER only known values",
        bool(vulnerability["RISK_TIER"].isin(["Low", "Medium", "High", "Critical"]).all()),
    )
    report.check(
        "vulnerability.STATUS only known values",
        bool(vulnerability["STATUS"].isin(["Green", "Yellow", "Red", "Red-Black"]).all()),
    )
    report.check("vulnerability.HORIZON_OFFSET >= 0", bool((vulnerability["HORIZON_OFFSET"] >= 0).all()))
    current = vulnerability[vulnerability["HORIZON_OFFSET"] == 0]
    report.check(
        "vulnerability: HORIZON_OFFSET==0 rows have REPORT_WEEK == WEEK_START_DATE",
        bool((current["REPORT_WEEK"] == current["WEEK_START_DATE"]).all()),
    )

    if atp_snapshot is not None:
        report.check("atp_snapshot has rows", len(atp_snapshot) > 0)
        report.check(
            "atp_snapshot.material/dc referential integrity",
            bool(atp_snapshot["material"].isin(dim_product["material"]).all())
            and bool(atp_snapshot["dc"].isin(dim_location["plnt_cd"]).all()),
        )
        case_pack = atp_snapshot["material"].map(dim_product.set_index("material")["case_pack_size"])
        report.check(
            "atp_snapshot.atp_cases matches atp_eaches / case_pack_size",
            bool(((atp_snapshot["atp_cases"] - atp_snapshot["atp_eaches"] / case_pack).abs() < 1e-2).all()),
        )

    if inbound_schedule is not None:
        report.check("inbound_schedule has rows", len(inbound_schedule) > 0)
        report.check(
            "inbound_schedule.material/dc referential integrity",
            bool(inbound_schedule["material"].isin(dim_product["material"]).all())
            and bool(inbound_schedule["dc"].isin(dim_location["plnt_cd"]).all()),
        )
        report.check(
            "inbound_schedule.inbound_qty_cases >= 0",
            bool((inbound_schedule["inbound_qty_cases"] >= 0).all()),
        )

    if scenario_keys:
        _validate_scenarios(report, tables, scenario_keys)

    return report


def _validate_scenarios(report: ValidationReport, tables: Dict[str, pd.DataFrame], scenario_keys: dict) -> None:
    """Re-check each planted pattern by the exact keys scenarios.py chose, so a
    future regeneration can never silently lose one of the 5 storylines."""
    historical = tables["historical"]
    shipments = tables["shipments"]
    vulnerability = tables["vulnerability"]
    allocation = tables["allocation"]

    keys = scenario_keys.get("dc2_fill_rate_drop")
    if keys:
        gi_dates = pd.to_datetime(historical["FST_PLAN_GI_DT"]).dt.date
        bucket = historical[
            (historical["PLNT_CD"] == keys["dc"])
            & (gi_dates >= keys["last_month_start"]) & (gi_dates <= keys["last_month_end"])
        ]
        overall_fill = historical["DELV_QTY"].sum() / max(historical["ORDR_QTY"].sum(), 1)
        bucket_fill = bucket["DELV_QTY"].sum() / bucket["ORDR_QTY"].sum() if len(bucket) and bucket["ORDR_QTY"].sum() else 1.0
        report.check(
            f"planted pattern: DC2 ({keys['dc']}) fill rate in its target month is well below the table average",
            bool(len(bucket) > 0 and bucket_fill < overall_fill - 0.1),
        )
        allocation_share = (bucket["CUT_RSN_PRIM_DESC"] == "Allocation").mean() if len(bucket) else 0.0
        report.check(
            "planted pattern: DC2's target-month cuts are dominated by an 'Allocation' cut reason",
            bool(len(bucket) > 0 and allocation_share > 0.5),
        )

    keys = scenario_keys.get("banner_block")
    if keys:
        matching = shipments[
            (shipments["KEY_CUST_NUM"] == keys["banner"]) & (shipments["DELIVERY_BLOCK_CD"] == keys["block_code"])
        ]
        report.check(
            f"planted pattern: banner {keys['banner']} has a clearly elevated block rate on code {keys['block_code']}",
            bool(len(matching) >= max(5, keys.get("rows_pinned", 0) * 0.9)),
        )

    keys = scenario_keys.get("yellow_to_red")
    if keys:
        current0 = vulnerability[vulnerability["HORIZON_OFFSET"] == 0]
        prior = current0[current0["WEEK_START_DATE"].eq(keys["prior_week"]) & current0["MATERIAL"].isin(keys["materials"])]
        latest = current0[current0["WEEK_START_DATE"].eq(keys["latest_week"]) & current0["MATERIAL"].isin(keys["materials"])]
        report.check(
            "planted pattern: chosen SKUs were Yellow in the prior V-report week",
            bool(len(prior) > 0 and (prior["STATUS"] == "Yellow").all()),
        )
        report.check(
            "planted pattern: chosen SKUs are Red/Red-Black in the latest V-report week",
            bool(len(latest) > 0 and latest["STATUS"].isin(["Red", "Red-Black"]).all()),
        )

    keys = scenario_keys.get("over_allocation")
    if keys:
        bucket = allocation[
            (allocation["PARENT_CODE"] == keys["parent_code"]) & (allocation["CUSTOMER_GROUP"] == keys["customer_group"])
        ]
        report.check(
            "planted pattern: chosen parent/customer-group allocation consumption exceeds 90%",
            bool(len(bucket) > 0 and (bucket["PCT_CONSUMED"] > 90).all()),
        )

    keys = scenario_keys.get("late_gi")
    if keys:
        gi_dates = pd.to_datetime(historical["FST_PLAN_GI_DT"]).dt.date
        bucket = historical[
            (historical["PLNT_CD"] == keys["dc"]) & (gi_dates >= keys["week_start"]) & (gi_dates <= keys["week_end"])
        ]
        overall_on_time = (historical["LATE_FL_MAD_IND"] == "NO").mean()
        bucket_on_time = (bucket["LATE_FL_MAD_IND"] == "NO").mean() if len(bucket) else 1.0
        report.check(
            f"planted pattern: on-time rate at {keys['dc']} in its target week is well below the table average",
            bool(len(bucket) > 0 and bucket_on_time < overall_on_time - 0.3),
        )
