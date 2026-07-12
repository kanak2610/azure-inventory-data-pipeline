"""
02_bronze_layer.py
-------------------
LOCAL SIMULATION of the Databricks Autoloader Bronze ingestion step.

On real Azure Databricks this logic is:

    df = (spark.readStream
                .format("cloudFiles")
                .option("cloudFiles.format", "csv")
                .option("cloudFiles.schemaLocation", schema_path)
                .option("cloudFiles.inferColumnTypes", "true")
                .load(raw_path))

    (df.writeStream
        .format("delta")
        .option("checkpointLocation", checkpoint_path)
        .trigger(availableNow=True)
        .toTable("bronze.inventory"))

See databricks_notebooks/01_bronze_autoloader.py for the real PySpark version.

Here we reproduce the SAME behaviour with pandas so the whole pipeline can
be executed end-to-end without an actual Databricks cluster:
  - reads every raw CSV
  - does NOT clean/transform anything (bronze = raw + metadata only)
  - adds ingestion metadata columns (_ingest_timestamp, _source_file)
  - writes out as parquet (stand-in for Delta tables)
"""

import pandas as pd
import os
from datetime import datetime

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "raw")
BRONZE_DIR = os.path.join(os.path.dirname(__file__), "..", "bronze")
os.makedirs(BRONZE_DIR, exist_ok=True)

INGEST_TS = datetime.now().isoformat()

# map: bronze table name -> list of raw source files that feed it
TABLE_SOURCES = {
    "products": ["products.csv"],
    "inventory": ["inventory.csv"],
    "warehouse": ["warehouse.csv"],
    "orders": ["orders.csv"],
    "sales": ["sales.csv"],
    "suppliers": ["suppliers_2026-06-01.csv", "suppliers_2026-07-01.csv"],  # both feeds land in bronze
}

def ingest_table(table_name, source_files):
    frames = []
    for f in source_files:
        path = os.path.join(RAW_DIR, f)
        df = pd.read_csv(path)
        df["_source_file"] = f
        df["_ingest_timestamp"] = INGEST_TS
        frames.append(df)
    combined = pd.concat(frames, ignore_index=True)
    out_path = os.path.join(BRONZE_DIR, f"{table_name}.csv")
    combined.to_csv(out_path, index=False)
    print(f"[BRONZE] {table_name:12s} -> {len(combined):4d} rows  ({', '.join(source_files)})")
    return combined

if __name__ == "__main__":
    for table, sources in TABLE_SOURCES.items():
        ingest_table(table, sources)
    print("\nBronze ingestion complete ->", os.path.abspath(BRONZE_DIR))
