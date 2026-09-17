"""Available-to-promise snapshot — INVENTED, not a mirror of any real table.

shipments.py already carries per-DC ATP columns, but they're randomized PER
ORDER LINE (kept that way for width-fidelity to the real table's shape), so
the same (material, dc) can show a different "ATP" depending which row you
read — not useful for a clean "what is ATP for SKU X at DC Y" answer. This
table gives exactly one row per (material, dc), consistent and de-duplicated,
using the same gamma-distribution formula as shipments.py's per-line columns
(driven by the same current_risk) for behavioral consistency between the two.

Grain: material x dc, as of cfg.dates.as_of_date. No history — none of the
question-bank questions ask for ATP-over-time, only a current value.

Column names are lowercase snake_case (not the SAP ALL_CAPS style of
shipments/historical/allocation/vulnerability) since this is a generated
dimension-style fact, not mirroring a specific real table — same convention
as dim_product/dim_customer/dim_location.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from rcl_datagen.dimensions.locations import distribution_centers


def build_atp_snapshot(
    rng: np.random.Generator,
    cfg,
    products: pd.DataFrame,
    locations: pd.DataFrame,
    current_risk: pd.DataFrame,
) -> pd.DataFrame:
    dcs = distribution_centers(locations)["plnt_cd"].tolist()
    grid = products[["material", "case_pack_size"]].merge(pd.DataFrame({"dc": dcs}), how="cross")
    n = len(grid)

    risk_lookup = current_risk.set_index("material")["risk_index"]
    fallback_risk = float(risk_lookup.mean()) if len(risk_lookup) else 0.1
    risk = grid["material"].map(risk_lookup).fillna(fallback_risk).to_numpy()
    dc_risk_damp = np.clip(1.2 - risk, 0.2, 1.2)  # higher risk -> less available inventory

    atp_eaches = np.round(rng.gamma(shape=2.0, scale=150.0, size=n) * dc_risk_damp, 0)
    case_pack = grid["case_pack_size"].to_numpy()

    return pd.DataFrame({
        "as_of_date": cfg.dates.as_of_date,
        "material": grid["material"],
        "dc": grid["dc"],
        "atp_eaches": atp_eaches,
        "atp_cases": np.round(atp_eaches / case_pack, 4),
    })
