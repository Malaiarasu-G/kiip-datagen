# Databricks notebook source
# MAGIC %md
# MAGIC # RCL PoC -> Unity Catalog
# MAGIC
# MAGIC Rebuilds the 9 RCL PoC tables (the exact same logic as `scripts/generate.py`
# MAGIC in this repo) and writes each one into Unity Catalog as a managed Delta
# MAGIC table, under the catalog/schema set in the widgets below.
# MAGIC
# MAGIC ### Before you run this
# MAGIC 1. Open this notebook **from inside a Databricks Repo** cloned from
# MAGIC    `https://github.com/Malaiarasu-G/kiip-datagen` (left sidebar -> **Workspace**
# MAGIC    -> **Repos** -> **Add Repo** -> paste that URL -> Create). That's what lets
# MAGIC    it `import rcl_datagen` the same way the local project does.
# MAGIC 2. Attach this notebook to a cluster whose **Access mode** is `Shared` or
# MAGIC    `Single user` (or use Serverless, if available on your workspace).
# MAGIC    Unity Catalog writes fail on an old-style "No isolation shared" cluster.
# MAGIC 3. You need `CREATE SCHEMA` + `CREATE TABLE` permission on the target catalog.
# MAGIC    Defaults to `integrated_intelligence_poc` (this workspace's PoC catalog) --
# MAGIC    change the `catalog` widget if you want a different one.
# MAGIC 4. Click **Run all** (or step through cell by cell).
# MAGIC
# MAGIC Nothing here touches the real client's data or systems -- this only
# MAGIC (re)generates the same fictitious PoC data already described in
# MAGIC `datagen/README.md` and writes it into whatever catalog/schema you point it at.

# COMMAND ----------

# MAGIC %md ### 1. Configuration widgets -- edit these in the notebook UI, not in code

# COMMAND ----------

dbutils.widgets.text("catalog", "integrated_intelligence_poc", "1. Catalog name")
dbutils.widgets.text("schema", "rcl_poc", "2. Schema name (created if missing)")
dbutils.widgets.dropdown("scale", "poc", ["dev", "poc", "stress"], "3. Data volume preset")
dbutils.widgets.dropdown("apply_comments", "true", ["true", "false"], "4. Add table/column descriptions?")

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
SCALE = dbutils.widgets.get("scale")
APPLY_COMMENTS = dbutils.widgets.get("apply_comments") == "true"

print(f"Target: {CATALOG}.{SCHEMA}   scale={SCALE}   apply_comments={APPLY_COMMENTS}")

# COMMAND ----------

# MAGIC %md ### 2. Import the generator code from this same Repo checkout
# MAGIC
# MAGIC `os.getcwd()` in a Databricks Repo notebook is the notebook's own folder --
# MAGIC this notebook lives at `datagen/databricks/`, so its parent is `datagen/`,
# MAGIC exactly like `scripts/generate.py` locally.

# COMMAND ----------

import os
import sys
from pathlib import Path

NOTEBOOK_DIR = Path(os.getcwd())
PROJECT_DIR = NOTEBOOK_DIR.parent
print(f"Notebook dir: {NOTEBOOK_DIR}")
print(f"Project dir:  {PROJECT_DIR}")
assert (PROJECT_DIR / "src" / "rcl_datagen").exists(), (
    f"Couldn't find src/rcl_datagen under {PROJECT_DIR} -- this notebook must stay at "
    "datagen/databricks/ inside the Repo checkout. See the markdown cell above."
)
sys.path.insert(0, str(PROJECT_DIR / "src"))

# COMMAND ----------

import numpy as np
import pandas as pd

from rcl_datagen import calendar as cal
from rcl_datagen.config import load_config
from rcl_datagen.dimensions.customers import build_customers
from rcl_datagen.dimensions.locations import build_locations
from rcl_datagen.dimensions.products import build_products
from rcl_datagen.facts.allocation import build_allocation
from rcl_datagen.facts.atp_snapshot import build_atp_snapshot
from rcl_datagen.facts.historical import build_historical
from rcl_datagen.facts.inbound_schedule import build_inbound_schedule
from rcl_datagen.facts.shipments import build_shipments
from rcl_datagen.facts.vulnerability import build_vulnerability
from rcl_datagen.metadata import TABLE_DESCRIPTIONS, describe_column
from rcl_datagen.risk import build_material_week_risk
from rcl_datagen.scenarios import apply_scenarios
from rcl_datagen.validate import validate

SHEET_ORDER = [
    "dim_product", "dim_customer", "dim_location",
    "shipments", "historical", "allocation", "vulnerability",
    "atp_snapshot", "inbound_schedule",
]

# COMMAND ----------

# MAGIC %md ### 3. Generate the data -- identical pipeline to `scripts/generate.py`

# COMMAND ----------

cfg = load_config(PROJECT_DIR / "config" / "config.yaml", scale=SCALE)
rng = np.random.default_rng(cfg.seed)

print(f"Generating '{SCALE}' scale data (seed={cfg.seed}) ...")

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

risk = build_material_week_risk(rng, products["material"], weekly_calendar_full["week_start_date"])
current_risk = (
    risk.sort_values("week_start_date").groupby("material", as_index=False).last()[["material", "risk_index"]]
)
print(f"  risk index built for {products['material'].nunique()} materials x {len(weekly_calendar_full)} weeks")

shipments = build_shipments(rng, cfg, products, customers, locations, current_risk)
print(f"  shipments: {len(shipments)} rows, {len(shipments.columns)} columns")

allocation = build_allocation(rng, cfg, products, customers, risk)
print(f"  allocation: {len(allocation)} rows")

historical = build_historical(rng, cfg, products, customers, locations, risk, allocation)
print(f"  historical: {len(historical)} rows")

vulnerability = build_vulnerability(rng, cfg, products, vuln_weeks, risk)
print(f"  vulnerability: {len(vulnerability)} rows")

atp_snapshot = build_atp_snapshot(rng, cfg, products, locations, current_risk)
print(f"  atp_snapshot: {len(atp_snapshot)} rows")

inbound_schedule = build_inbound_schedule(rng, cfg, products, locations, current_risk)
print(f"  inbound_schedule: {len(inbound_schedule)} rows")

tables = {
    "dim_product": products,
    "dim_customer": customers,
    "dim_location": locations,
    "shipments": shipments,
    "historical": historical,
    "allocation": allocation,
    "vulnerability": vulnerability,
    "atp_snapshot": atp_snapshot,
    "inbound_schedule": inbound_schedule,
}

# COMMAND ----------

# MAGIC %md ### 4. Plant the 5 demo storylines + validate (same as `scripts/generate.py`)

# COMMAND ----------

scenario_keys = None
if cfg.scenarios.enabled:
    scenario_keys = apply_scenarios(rng, cfg, tables)
    applied = [k for k, v in scenario_keys.items() if v is not None]
    print(f"  planted patterns applied: {', '.join(applied) if applied else '(none)'}")

report = validate(tables, scenario_keys=scenario_keys)
report.print_summary()
assert report.ok, "Validation failed -- see FAILED lines printed above before writing anything to Unity Catalog."

# COMMAND ----------

# MAGIC %md ### 5. Write each table into Unity Catalog as a managed Delta table
# MAGIC
# MAGIC `overwrite` + `overwriteSchema=true` so reruns (e.g. a different `scale`)
# MAGIC cleanly replace the table rather than appending or erroring on a schema change --
# MAGIC mirrors `writer.py`'s local `CREATE OR REPLACE TABLE` behavior.

# COMMAND ----------

spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{CATALOG}`.`{SCHEMA}`")

for name in SHEET_ORDER:
    pdf = tables[name]
    sdf = spark.createDataFrame(pdf)
    full_name = f"`{CATALOG}`.`{SCHEMA}`.`{name}`"
    (sdf.write
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(full_name))
    print(f"  wrote {full_name}: {sdf.count()} rows, {len(sdf.columns)} columns")

print("\nDone.")

# COMMAND ----------

# MAGIC %md ### 6. (Optional) Copy the plain-English table/column descriptions into Unity Catalog
# MAGIC
# MAGIC Reuses `src/rcl_datagen/metadata.py` -- the same source the local
# MAGIC `docs/data_dictionary.md` is built from -- so the descriptions show up
# MAGIC directly in Catalog Explorer for anyone browsing the tables there.
# MAGIC Toggle off with the `apply_comments` widget above if you'd rather skip it.

# COMMAND ----------

if APPLY_COMMENTS:
    def _escape(text: str) -> str:
        return text.replace("\\", "\\\\").replace("'", "\\'")

    for name in SHEET_ORDER:
        full_name = f"`{CATALOG}`.`{SCHEMA}`.`{name}`"
        table_comment = TABLE_DESCRIPTIONS.get(name, "")
        if table_comment:
            spark.sql(f"COMMENT ON TABLE {full_name} IS '{_escape(table_comment)}'")
        for col in tables[name].columns:
            desc = describe_column(name, col)
            if desc:
                spark.sql(f"ALTER TABLE {full_name} ALTER COLUMN `{col}` COMMENT '{_escape(desc)}'")
    print("Table and column descriptions applied.")
else:
    print("Skipped (apply_comments = false).")

# COMMAND ----------

# MAGIC %md ### 7. Verify

# COMMAND ----------

display(spark.sql(f"SHOW TABLES IN `{CATALOG}`.`{SCHEMA}`"))

# COMMAND ----------

display(spark.sql(f"SELECT * FROM `{CATALOG}`.`{SCHEMA}`.dim_product LIMIT 10"))
