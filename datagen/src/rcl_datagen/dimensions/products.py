"""Product / material dimension: GBU -> Franchise -> Category -> Brand -> Material.

Built once with canonical column names; each fact-table generator renames/
selects from this into that source table's own naming convention — the real
snapshots show the *same* hierarchy named differently in different tables
(e.g. SC_GBU_DESC/SC_FRAN_DESC/... in shipments+allocation vs
REGN_GLOBL_BU_DESC/REGN_FRAN_DESC/... in historical).

NOTE: the real shipments snapshot has a `JNJ_ITEM_NO` column — the client's
initials are baked into that column *name* (not just a data value), so unlike
every other observed column name it is renamed here to `CLIENT_ITEM_NO`
rather than reproduced verbatim. Everything else keeps the observed naming.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from rcl_datagen.namers import (
    CATEGORY_WORDS, DISTRIBUTION_CHANNEL_STATUS, FRANCHISE_THEMES, GBU_NAMES,
    new_brand_name_pool,
)

_CASE_PACK_SIZES = [6, 8, 12, 18, 24, 36, 48]
_DSTN_STATUS_WEIGHTS = [0.82, 0.06, 0.06, 0.06]  # mostly Active Saleable


def build_products(
    rng: np.random.Generator,
    locations: pd.DataFrame,
    num_gbus: int,
    num_franchises_per_gbu: int,
    num_categories_per_franchise: int,
    num_brands_per_category: int,
    num_materials_per_brand: int,
    npi_rate: float,
) -> pd.DataFrame:
    gbus = list(GBU_NAMES)[:num_gbus]
    brand_pool = new_brand_name_pool()
    mfg_sites = (
        locations.loc[locations["is_manufacturing_site"], "plnt_cd"].tolist()
        or locations["plnt_cd"].tolist()
    )

    rows = []
    material_seq = 100000
    parent_seq = 900000

    for gbu in gbus:
        franchises = rng.choice(FRANCHISE_THEMES, size=num_franchises_per_gbu, replace=False)
        for franchise in franchises:
            categories = rng.choice(CATEGORY_WORDS, size=num_categories_per_franchise, replace=False)
            for category in categories:
                for _ in range(num_brands_per_category):
                    brand = brand_pool.next(rng)
                    parent_seq += 1
                    parent_code = str(parent_seq)
                    parent_desc = f"{brand.upper()} {category.upper()} PARENT"
                    case_pack = int(rng.choice(_CASE_PACK_SIZES))
                    status_idx = int(rng.choice(len(DISTRIBUTION_CHANNEL_STATUS), p=_DSTN_STATUS_WEIGHTS))
                    dstn_code, dstn_desc = DISTRIBUTION_CHANNEL_STATUS[status_idx]
                    mfg_plnt_cd = rng.choice(mfg_sites)

                    for variant in range(num_materials_per_brand):
                        material_seq += 1
                        list_price = round(float(np.clip(rng.lognormal(mean=np.log(12.0), sigma=0.6), 3.0, 300.0)), 2)
                        rows.append({
                            "material": str(material_seq),
                            "client_item_no": str(material_seq),
                            "material_parent_cd": parent_code,
                            "material_desc": f"{brand.upper()} {category.upper()} VARIANT {variant + 1}",
                            "material_parent_desc": parent_desc,
                            "gbu": gbu,
                            "franchise": franchise,
                            "category": category,
                            "brand": brand,
                            "each_upc": str(rng.integers(10 ** 11, 10 ** 12 - 1)),
                            "case_upc": str(rng.integers(10 ** 13, 10 ** 14 - 1)),
                            "case_pack_size": case_pack,
                            "list_price": list_price,
                            "npi_ind": bool(rng.random() < npi_rate),
                            "dstn_chn_sts_cd": dstn_code,
                            "dstn_chn_sts_desc": dstn_desc,
                            "mfg_plnt_cd": mfg_plnt_cd,
                        })

    return pd.DataFrame(rows)
