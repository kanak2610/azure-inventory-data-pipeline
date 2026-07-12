# Databricks notebook source
# MAGIC %md
# MAGIC # Bronze Layer - Autoloader Ingestion
# MAGIC Reads all 6 raw CSV datasets from ADLS Gen2 `raw/` container using
# MAGIC Databricks Autoloader (`cloudFiles`) and writes them as Delta tables
# MAGIC in the `bronze` schema. Autoloader gives incremental, scalable
# MAGIC ingestion with automatic schema inference and evolution.

# COMMAND ----------

from pyspark.sql.functions import current_timestamp, input_file_name

# COMMAND ----------

# MAGIC %md ### Config - update these for your environment

# COMMAND ----------

storage_account = "yourstorageaccount"
container_raw = "raw"
container_bronze = "bronze"

base_raw_path = f"abfss://{container_raw}@{storage_account}.dfs.core.windows.net"
base_bronze_path = f"abfss://{container_bronze}@{storage_account}.dfs.core.windows.net"
checkpoint_base = f"{base_bronze_path}/_checkpoints"
schema_base = f"{base_bronze_path}/_schemas"

spark.sql("CREATE SCHEMA IF NOT EXISTS bronze")

tables = ["products", "suppliers", "inventory", "warehouse", "orders", "sales"]

# COMMAND ----------

# MAGIC %md ### Generic Autoloader ingestion function

# COMMAND ----------

def ingest_table_autoloader(table_name: str):
    raw_path = f"{base_raw_path}/{table_name}"
    checkpoint_path = f"{checkpoint_base}/{table_name}"
    schema_path = f"{schema_base}/{table_name}"

    df = (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format", "csv")
        .option("cloudFiles.schemaLocation", schema_path)
        .option("cloudFiles.inferColumnTypes", "true")
        .option("header", "true")
        .load(raw_path)
        .withColumn("_ingest_timestamp", current_timestamp())
        .withColumn("_source_file", input_file_name())
    )

    query = (
        df.writeStream
        .format("delta")
        .option("checkpointLocation", checkpoint_path)
        .option("mergeSchema", "true")
        .trigger(availableNow=True)  # process everything currently available, then stop (good for scheduled jobs)
        .toTable(f"bronze.{table_name}")
    )
    query.awaitTermination()
    print(f"Ingested bronze.{table_name}")


# COMMAND ----------

# MAGIC %md ### Run ingestion for every raw dataset

# COMMAND ----------

for t in tables:
    ingest_table_autoloader(t)

# COMMAND ----------

# MAGIC %md ### Quick sanity check

# COMMAND ----------

for t in tables:
    cnt = spark.table(f"bronze.{t}").count()
    print(f"bronze.{t}: {cnt} rows")
