"""Writes generated tables to Parquet/CSV and loads them into a single DuckDB file."""
from __future__ import annotations

from pathlib import Path
from typing import Dict

import duckdb
import pandas as pd


def write_tables(tables: Dict[str, pd.DataFrame], cfg, base_dir: Path) -> None:
    parquet_dir = base_dir / cfg.output.parquet_dir
    parquet_dir.mkdir(parents=True, exist_ok=True)

    if cfg.output.write_csv:
        csv_dir = base_dir / cfg.output.csv_dir
        csv_dir.mkdir(parents=True, exist_ok=True)

    duckdb_path = base_dir / cfg.output.duckdb_path
    duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    if duckdb_path.exists():
        duckdb_path.unlink()

    con = duckdb.connect(str(duckdb_path))
    try:
        for name, df in tables.items():
            pq_path = parquet_dir / f"{name}.parquet"
            df.to_parquet(pq_path, index=False)

            if cfg.output.write_csv:
                df.to_csv(csv_dir / f"{name}.csv", index=False)

            con.register("_tmp_df", df)
            con.execute(f'CREATE OR REPLACE TABLE "{name}" AS SELECT * FROM _tmp_df')
            con.unregister("_tmp_df")
    finally:
        con.close()
