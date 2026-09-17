"""Plant / distribution-center dimension.

Maps to PLNT_CD / PLNT_NM / MFG_SITE_NM seen in the historical-data snapshot,
and the per-DC columns (US16/US19/UD20/UD30-style codes) seen in shipments.
Codes follow the observed 2-letter-prefix + 2-digit pattern; the prefixes and
numbers themselves are reassigned, not copied from the client's real sites.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from rcl_datagen.namers import new_logistics_site_name_pool

_COUNTRY_PREFIXES = {"US": "United States", "UD": "United States", "CA": "Canada", "MX": "Mexico"}


def build_locations(rng: np.random.Generator, num_plants: int, num_distribution_centers: int) -> pd.DataFrame:
    num_distribution_centers = min(num_distribution_centers, num_plants)
    name_pool = new_logistics_site_name_pool()

    prefixes = list(_COUNTRY_PREFIXES)
    used_codes = set()
    rows = []
    for i in range(num_plants):
        prefix = rng.choice(prefixes)
        code = f"{prefix}{rng.integers(10, 99)}"
        while code in used_codes:
            code = f"{prefix}{rng.integers(10, 99)}"
        used_codes.add(code)

        is_dc = i < num_distribution_centers
        rows.append({
            "plnt_cd": code,
            "plnt_nm": name_pool.next(rng),
            "is_distribution_center": is_dc,
            # DCs are mostly pure distribution; a few also do light manufacturing.
            "is_manufacturing_site": (not is_dc) or bool(rng.random() < 0.3),
            "geo_ctry_nm": _COUNTRY_PREFIXES[prefix],
        })

    return pd.DataFrame(rows)


def distribution_centers(locations: pd.DataFrame) -> pd.DataFrame:
    return locations.loc[locations["is_distribution_center"]].reset_index(drop=True)
