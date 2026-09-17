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


def validate(tables: Dict[str, pd.DataFrame], report: Optional[ValidationReport] = None) -> ValidationReport:
    report = report or ValidationReport()

    dim_product = tables["dim_product"]

    shipments = tables["shipments"]
    historical = tables["historical"]
    allocation = tables["allocation"]
    vulnerability = tables["vulnerability"]

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

    report.check("allocation has rows", len(allocation) > 0)
    report.check(
        "allocation.PARENT_CODE all exist in dim_product parents",
        bool(allocation["PARENT_CODE"].isin(dim_product["material_parent_cd"]).all()),
    )
    report.check("allocation.PERIOD only AM/PM", bool(allocation["PERIOD"].isin(["AM", "PM"]).all()))

    report.check("vulnerability has rows", len(vulnerability) > 0)
    report.check(
        "vulnerability.MATERIAL all exist in dim_product",
        bool(vulnerability["MATERIAL"].isin(dim_product["material"]).all()),
    )
    report.check(
        "vulnerability.RISK_TIER only known values",
        bool(vulnerability["RISK_TIER"].isin(["Low", "Medium", "High", "Critical"]).all()),
    )

    return report
