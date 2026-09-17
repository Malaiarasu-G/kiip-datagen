"""Shared per-material, per-week 'supply risk' latent value.

This is the one thing that ties the four generated tables into one coherent
story instead of four independently-random ones: the same risk_index feeds
- vulnerability.py   -> risk fields / risk tier
- allocation.py      -> probability a material is on allocation
- shipments.py       -> probability / severity of an order-line cut

so a chatbot answering "why was this order short" and "why is this SKU on
allocation" can trace both back to the same elevated risk_index for that
material in that week, instead of two unrelated coincidences.

It is intentionally NOT written out as its own table — it is generation-time
machinery, not a source-system table we observed in the snapshot.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def build_material_week_risk(
    rng: np.random.Generator,
    materials: pd.Series,
    week_start_dates: pd.Series,
) -> pd.DataFrame:
    """Mean-reverting (AR(1)-like) risk index in [0, 1] per material, over time.

    Most materials sit low (baseline drawn from a right-skewed Beta(2, 8)) with
    occasional multi-week elevated stretches, rather than pure iid noise, so a
    "why is this risky" story holds together across consecutive weeks.
    """
    materials = pd.Index(materials).unique()
    weeks = pd.Index(week_start_dates).unique().sort_values()
    n_weeks = len(weeks)

    rows = []
    for material in materials:
        baseline = rng.beta(2, 8)
        level = baseline
        series = np.empty(n_weeks)
        for i in range(n_weeks):
            shock = rng.normal(0, 0.04)
            level = float(np.clip(0.85 * level + 0.15 * baseline + shock, 0.0, 1.0))
            series[i] = level
        rows.append(pd.DataFrame({
            "material": material,
            "week_start_date": weeks,
            "risk_index": series,
        }))

    return pd.concat(rows, ignore_index=True)


def risk_tier(risk_index: pd.Series) -> pd.Series:
    return pd.cut(
        risk_index,
        bins=[-0.01, 0.25, 0.5, 0.75, 1.01],
        labels=["Low", "Medium", "High", "Critical"],
    ).astype(str)


def vreport_status(risk_index: pd.Series) -> pd.Series:
    """Green/Yellow/Red/Red-Black — the V-report's own vocabulary.

    Distinct from risk_tier's Low/Medium/High/Critical (a different table's
    labeling convention over the same underlying risk_index) — kept as a
    separate function rather than relabeling risk_tier's output so the two
    tables' domains don't silently drift into meaning the same thresholds.
    """
    return pd.cut(
        risk_index,
        bins=[-0.01, 0.4, 0.65, 0.85, 1.01],
        labels=["Green", "Yellow", "Red", "Red-Black"],
    ).astype(str)
