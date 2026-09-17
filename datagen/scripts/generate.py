"""CLI entrypoint: generate the full synthetic RCL PoC dataset.

Usage:
    python scripts/generate.py --scale dev
    python scripts/generate.py --scale poc --config config/config.yaml

Edit config/config.yaml (volumes, date ranges, probabilities) and rerun this
script to regenerate — the generator code itself should rarely need to change
for that kind of adjustment.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))

from rcl_datagen import calendar as cal  # noqa: E402
from rcl_datagen.config import load_config  # noqa: E402
from rcl_datagen.dimensions.customers import build_customers  # noqa: E402
from rcl_datagen.dimensions.locations import build_locations  # noqa: E402
from rcl_datagen.dimensions.products import build_products  # noqa: E402
from rcl_datagen.facts.allocation import build_allocation  # noqa: E402
from rcl_datagen.facts.historical import build_historical  # noqa: E402
from rcl_datagen.facts.shipments import build_shipments  # noqa: E402
from rcl_datagen.facts.vulnerability import build_vulnerability  # noqa: E402
from rcl_datagen.risk import build_material_week_risk  # noqa: E402
from rcl_datagen.validate import validate  # noqa: E402
from rcl_datagen.writer import write_tables  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scale", default="dev", choices=["dev", "poc", "stress"], help="volume preset from config.yaml")
    parser.add_argument("--config", default=str(BASE_DIR / "config" / "config.yaml"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config, scale=args.scale)
    rng = np.random.default_rng(cfg.seed)

    t0 = time.time()
    print(f"Generating '{args.scale}' scale data (seed={cfg.seed}) ...")

    locations = build_locations(rng, cfg.dimensions.num_plants, cfg.dimensions.num_distribution_centers)
    products = build_products(
        rng, locations,
        cfg.dimensions.num_gbus, cfg.dimensions.num_franchises_per_gbu,
        cfg.dimensions.num_categories_per_franchise, cfg.dimensions.num_brands_per_category,
        cfg.dimensions.num_materials_per_brand, cfg.business_rules.npi_rate,
    )
    customers = build_customers(rng, cfg.dimensions.num_customers, cfg.dimensions.num_ship_to_per_customer_max)
    print(f"  dimensions: {len(products)} materials, {len(customers)} ship-tos, {len(locations)} plants")

    daily_calendar = cal.build_daily_calendar(cfg.dates.history_start, cfg.dates.as_of_date)
    weekly_calendar_full = cal.build_weekly_calendar(daily_calendar)
    vuln_weeks = weekly_calendar_full.tail(cfg.dates.vulnerability_weeks).reset_index(drop=True)

    # One risk series spanning the full history_start..as_of_date range, shared by
    # historical/vulnerability/shipments (via current_risk) so all four tables tell
    # a consistent "why" story about the same material in the same week.
    risk = build_material_week_risk(rng, products["material"], weekly_calendar_full["week_start_date"])
    current_risk = (
        risk.sort_values("week_start_date").groupby("material", as_index=False).last()[["material", "risk_index"]]
    )
    print(f"  risk index built for {products['material'].nunique()} materials x {len(weekly_calendar_full)} weeks")

    shipments = build_shipments(rng, cfg, products, customers, locations, current_risk)
    print(f"  shipments: {len(shipments)} rows, {len(shipments.columns)} columns")

    historical = build_historical(rng, cfg, products, customers, locations, risk)
    print(f"  historical: {len(historical)} rows")

    allocation = build_allocation(rng, cfg, products, risk)
    print(f"  allocation: {len(allocation)} rows")

    vulnerability = build_vulnerability(rng, products, vuln_weeks, risk)
    print(f"  vulnerability: {len(vulnerability)} rows")

    tables = {
        "dim_product": products,
        "dim_customer": customers,
        "dim_location": locations,
        "shipments": shipments,
        "historical": historical,
        "allocation": allocation,
        "vulnerability": vulnerability,
    }

    write_tables(tables, cfg, BASE_DIR)
    print(f"  wrote {len(tables)} tables -> {BASE_DIR / cfg.output.duckdb_path}")

    report = validate(tables)
    report.print_summary()

    print(f"\nDone in {time.time() - t0:.1f}s")
    if not report.ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
