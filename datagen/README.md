# RCL PoC — Synthetic Data Generator

Config-driven Python code that generates a fictitious-but-structurally-realistic
stand-in for the four RCL source tables (shipments, historical, allocation,
vulnerability), for the Context Engineering / AI Chatbot PoC. This generates
**code you run**, not a one-off AI-produced dataset — edit `config/config.yaml`
(or the generator modules) and rerun to regenerate.

See `../` (the parent folder) for the original client requirement doc context
and the raw snapshot screenshots this was reverse-engineered from — those
screenshots are real client data and are gitignored; nothing under this
`datagen/` folder should ever contain real client business names.

## Setup

```bash
cd datagen
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

## Generate data

```bash
python scripts/generate.py --scale dev     # ~2k open-order lines, ~20k historical rows — fast, for iterating
python scripts/generate.py --scale poc     # ~20k / ~300k rows — demo-sized
python scripts/generate.py --scale stress  # ~100k / ~2M rows — larger-scale test
```

Output lands in `output/` (gitignored, regenerate any time):
- `output/rcl_poc.duckdb` — all 9 tables (6 fact + 3 dimension), queryable with any DuckDB client
- `output/parquet/*.parquet` and `output/csv/*.csv` — same tables as flat files

Then, optionally:

```bash
python scripts/build_data_dictionary.py   # -> docs/data_dictionary.md
python scripts/build_reference_docs.py    # -> docs/reference_codes.md, docs/reference_order_processing.md
python scripts/run_sample_questions.py    # -> docs/sample_qa_output.md
```

## What's configurable without touching code

Everything in `config/config.yaml`: random seed, date ranges, row-count
presets (`dev`/`poc`/`stress`), product/customer/plant catalog sizes, and the
probabilities behind cuts, allocation, NPI rate, etc. Change a number, rerun
`generate.py` — no code changes needed for that class of adjustment.

## Structure

```
config/config.yaml          single source of truth for volumes/dates/probabilities
src/rcl_datagen/
  config.py                 loads config.yaml
  calendar.py                daily + fiscal-week calendar dimension (+ build_forward_weeks for horizons)
  namers.py                  fictitious brand/retailer/site name generation (all in one place, auditable)
  risk.py                     shared per-material-per-week "supply risk" latent value; risk_tier + vreport_status
  reference_codes.py           shared code/description/weight lookups (block/rejection/cut/order-type/etc.)
  scenarios.py                 deterministic "planted pattern" pass — see config.yaml's `scenarios` section
  dimensions/
    products.py               GBU -> Franchise -> Category -> Brand -> Material
    customers.py               Segment -> Key Customer -> Sold-to -> Ship-to
    locations.py                Plant / distribution-center reference
  facts/
    shipments.py                rcl_agent_shipments equivalent (live open orders)
    historical.py                rcl_agent_cuts_tact_attr_dtl equivalent (ETD history, fill rate, cuts, rejections)
    allocation.py                 rcl_agent_osas equivalent (daily allocation, by customer group)
    vulnerability.py               rcl_agent_vreport equivalent (SKU risk + forward horizon)
    atp_snapshot.py                 INVENTED — one consistent ATP value per (material, dc)
    inbound_schedule.py              INVENTED — forward inbound-receipt schedule
  writer.py                    Parquet/CSV + DuckDB output
  validate.py                  referential-integrity, business-rule & planted-pattern checks
  metadata.py                  column descriptions -> data dictionary source
scripts/
  generate.py                 main CLI — run this
  build_data_dictionary.py    -> docs/data_dictionary.md
  build_reference_docs.py     -> docs/reference_codes.md, docs/reference_order_processing.md
  run_sample_questions.py     -> docs/sample_qa_output.md
queries/order_intelligence.py  named NL question -> SQL pairs (the Q&A seed set)
docs/                        generated output (dictionary + reference docs + sample Q&A) — safe to commit, describes fictitious data only
```

## Design decisions & assumptions (confirm with the client SME when possible)

- **Table/column names mirror the real schema** as read from the snapshot
  screenshots (structural fidelity matters for a context-engineering PoC).
  **Data values are fully fictitious** — brands, retailers, and site/operator
  names are invented (see `namers.py`). The one exception is the real
  column name `JNJ_ITEM_NO`, which bakes the client's identity into the
  *name* itself (not just a value) — renamed to `CLIENT_ITEM_NO` throughout.
- **Fiscal calendar** is simplified to the ISO calendar (Monday-start weeks,
  fiscal period = calendar month) — swap in the client's real 4-4-5 retail
  calendar in `calendar.py` if it differs.
- **Historical volume is intentionally far below production** (~30M rows
  really) — `stress` scale tops out at 2M, stratified by lane rather than
  uniform-random, which should be enough signal for ETD-style testing
  without the cost of replicating full volume.
- **Shipments' ~130-column width** comes from per-distribution-center
  pivoted inventory metrics (ATP / QI-hold / blocked / in-transit, x EA/CS).
  Number of DCs is `dimensions.num_distribution_centers` in the config
  (default 6) — the real table may have more.
  Two columns (`DIBI`, `DB`) appear in the real data with unconfirmed
  meaning; they're populated with placeholder codes.
- **Vulnerability table's actual risk fields were never visible** in the
  snapshot at all — everything from `SINGLE_SOURCE_FLAG` onward in
  `facts/vulnerability.py` is invented from standard SKU-risk concepts, not
  a confirmed schema. This table needs the most SME validation of the four.
- **Cross-table consistency:** `risk.py` produces one shared per-material,
  per-week "risk index" that drives allocation status, vulnerability
  scoring, and shipment cut-probability together, so a chatbot answering
  "why was this short / why is this on allocation" gets a coherent answer
  instead of four independently-random tables.
- No Databricks access from this environment, so the default target is
  local DuckDB/Parquet — swap `writer.py` for a Spark/Delta writer if this
  needs to land in Databricks later; the generation logic (pandas
  DataFrames in, DataFrame out) doesn't need to change to do that.
