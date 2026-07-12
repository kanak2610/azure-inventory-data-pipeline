# Databricks notebook source
# MAGIC %md
# MAGIC # Silver Layer - Cleaning, Validation, and SCD Type 2
# MAGIC Reads bronze Delta tables, applies cleaning/validation, and
# MAGIC implements SCD Type 2 on the `suppliers` dimension using
# MAGIC Delta Lake `MERGE INTO`.

# COMMAND ----------

from pyspark.sql import functions as F
from delta.tables import DeltaTable

spark.sql("CREATE SCHEMA IF NOT EXISTS silver")

# COMMAND ----------

# MAGIC %md ## 1. Products - clean, dedupe, validate

# COMMAND ----------

products_bronze = spark.table("bronze.products")

products_silver = (
    products_bronze
    .dropDuplicates(["product_id"])
    .filter(F.col("product_id").isNotNull() & F.col("product_name").isNotNull())
    .withColumn("unit_price", F.col("unit_price").cast("double"))
)

# impute missing price with category median
median_price = products_silver.approxQuantile("unit_price", [0.5], 0.01)[0]
products_silver = products_silver.fillna({"unit_price": median_price})

(products_silver
 .select("product_id", "product_name", "category", "unit_price", "supplier_id")
 .write.format("delta").mode("overwrite")
 .saveAsTable("silver.products"))

# COMMAND ----------

# MAGIC %md ## 2. Inventory, Warehouse, Orders, Sales - clean + type cast

# COMMAND ----------

warehouse_silver = spark.table("bronze.warehouse").dropDuplicates(["warehouse_id"])
warehouse_silver.write.format("delta").mode("overwrite").saveAsTable("silver.warehouse")

inventory_silver = (
    spark.table("bronze.inventory")
    .dropDuplicates(["inventory_id"])
    .withColumn("quantity_on_hand", F.col("quantity_on_hand").cast("int"))
    .withColumn("reorder_threshold", F.col("reorder_threshold").cast("int"))
    .withColumn("last_updated", F.to_date("last_updated"))
    .filter(F.col("product_id").isNotNull() & F.col("warehouse_id").isNotNull())
)
inventory_silver.write.format("delta").mode("overwrite").saveAsTable("silver.inventory")

orders_silver = (
    spark.table("bronze.orders")
    .dropDuplicates(["order_id"])
    .withColumn("order_date", F.to_date("order_date"))
    .withColumn("expected_delivery", F.to_date("expected_delivery"))
    .withColumn("actual_delivery", F.to_date("actual_delivery"))
    .withColumn("quantity_ordered", F.col("quantity_ordered").cast("int"))
    .withColumn("delay_days", F.datediff("actual_delivery", "expected_delivery"))
    .filter(F.col("order_id").isNotNull() & F.col("supplier_id").isNotNull())
)
orders_silver.write.format("delta").mode("overwrite").saveAsTable("silver.orders")

sales_silver = (
    spark.table("bronze.sales")
    .dropDuplicates(["sale_id"])
    .withColumn("sale_date", F.to_date("sale_date"))
    .withColumn("quantity_sold", F.col("quantity_sold").cast("int"))
    .withColumn("unit_price", F.col("unit_price").cast("double"))
    .withColumn("revenue", F.col("revenue").cast("double"))
    .filter((F.col("sale_id").isNotNull()) & (F.col("quantity_sold") > 0))
)
sales_silver.write.format("delta").mode("overwrite").saveAsTable("silver.sales")

# COMMAND ----------

# MAGIC %md ## 3. Suppliers - SCD Type 2 via Delta MERGE INTO
# MAGIC
# MAGIC Standard SCD2 pattern:
# MAGIC 1. Create the target table on first run with `is_current`, `effective_start`, `effective_end`.
# MAGIC 2. On every new supplier feed: MERGE the incoming batch against the
# MAGIC    target on `supplier_id`, comparing tracked attributes.
# MAGIC 3. If a tracked attribute changed -> expire the old row
# MAGIC    (`is_current = false`, `effective_end = today`).
# MAGIC 4. Insert new incoming rows as fresh current rows
# MAGIC    (`is_current = true`, `effective_end = null`).

# COMMAND ----------

TARGET_TABLE = "silver.suppliers_scd2"
TRACKED_COLS = ["address", "rating"]

incoming = (
    spark.table("bronze.suppliers")
    .withColumn("source_date", F.to_date("source_date"))
    .dropDuplicates()
)

# Only keep the LATEST row per supplier_id from this incoming batch
latest_incoming = (
    incoming
    .withColumn("rn", F.row_number().over(
        __import__("pyspark").sql.Window.partitionBy("supplier_id").orderBy(F.col("source_date").desc())
    ))
    .filter("rn = 1")
    .drop("rn")
)

if not spark.catalog.tableExists(TARGET_TABLE):
    # first run: everything is a new current record
    initial = (
        latest_incoming
        .withColumn("effective_start", F.col("source_date"))
        .withColumn("effective_end", F.lit(None).cast("date"))
        .withColumn("is_current", F.lit(True))
        .select("supplier_id", "supplier_name", "address", "contact_email",
                "rating", "effective_start", "effective_end", "is_current")
    )
    initial.write.format("delta").mode("overwrite").saveAsTable(TARGET_TABLE)
else:
    target = DeltaTable.forName(spark, TARGET_TABLE)

    # Step 1: expire current rows whose tracked attributes changed
    change_condition = " OR ".join([f"target.{c} <> source.{c}" for c in TRACKED_COLS])

    (target.alias("target")
        .merge(
            latest_incoming.alias("source"),
            "target.supplier_id = source.supplier_id AND target.is_current = true"
        )
        .whenMatchedUpdate(
            condition=change_condition,
            set={
                "is_current": "false",
                "effective_end": "source.source_date",
            }
        )
        .execute())

    # Step 2: insert new current rows for suppliers that are new OR changed
    changed_or_new = (
        latest_incoming.alias("source")
        .join(
            spark.table(TARGET_TABLE).filter("is_current = true").alias("target"),
            on="supplier_id", how="left_anti"
        )
        .withColumn("effective_start", F.col("source_date"))
        .withColumn("effective_end", F.lit(None).cast("date"))
        .withColumn("is_current", F.lit(True))
        .select("supplier_id", "supplier_name", "address", "contact_email",
                "rating", "effective_start", "effective_end", "is_current")
    )

    changed_or_new.write.format("delta").mode("append").saveAsTable(TARGET_TABLE)

# COMMAND ----------

display(spark.table(TARGET_TABLE).orderBy("supplier_id", "effective_start"))
