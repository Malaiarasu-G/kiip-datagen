"""Customer hierarchy: Segment -> Key Customer -> Sold-to -> Ship-to.

Fictitious retailer names (see namers.py). The segment labels themselves
(Mass/Club, Drug & Specialty, Ecom, FC&D, Exports & All Others, Grocery) are
generic retail-industry classification terms, not client-specific, so they
are reused as observed — note the real snapshot's segment list also included
"Walmart" as its own segment (a real named company gets its own code when
it's big enough); that is replaced here with the generic "Grocery" /
"Mass/Club" segments rather than naming any real retailer.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from rcl_datagen.namers import CUSTOMER_SEGMENTS, new_retailer_name_pool

_GEO_CLUSTERS = ["Unknown", "Northeast", "Midwest", "South", "West"]
_GEO_CLUSTER_WEIGHTS = [0.55, 0.15, 0.12, 0.10, 0.08]


def build_customers(
    rng: np.random.Generator,
    num_customers: int,
    num_ship_to_per_customer_max: int,
) -> pd.DataFrame:
    name_pool = new_retailer_name_pool()
    rows = []
    key_cust_seq = 48000000

    for _ in range(num_customers):
        key_cust_seq += rng.integers(1, 25)
        key_cust_num = f"00{key_cust_seq}"
        key_cust_nm = name_pool.next(rng)
        segment = rng.choice(CUSTOMER_SEGMENTS)
        geo_cluster = rng.choice(_GEO_CLUSTERS, p=_GEO_CLUSTER_WEIGHTS)

        sold_to_pt = str(40000000 + rng.integers(0, 999999))
        num_ship_tos = int(rng.integers(1, num_ship_to_per_customer_max + 1))

        for ship_idx in range(num_ship_tos):
            ship_to_num = str(int(sold_to_pt) + ship_idx)
            ship_to_nm = key_cust_nm if num_ship_tos == 1 else f"{key_cust_nm} DC #{ship_idx + 1}"
            rows.append({
                "key_cust_num": key_cust_num,
                "key_cust_nm": key_cust_nm,
                "sold_to_pt": sold_to_pt,
                "sold_to_nm": key_cust_nm,
                "ship_to_num": ship_to_num,
                "ship_to_nm": ship_to_nm,
                "cust_seg_cd": segment,
                "geo_clus_cust_chnl_cd": geo_cluster,
            })

    return pd.DataFrame(rows)
