# Databricks notebook source
# MAGIC %md
# MAGIC # Data Quality Checks
# MAGIC Explicit validation rules run after Silver transformation. Rows that
# MAGIC fail are written to a `_quarantine` table instead of silently dropped,
# MAGIC so nothing is lost and issues stay auditable.

# COMMAND ----------

from pyspark.sql import functions as F

spark.sql("CREATE SCHEMA IF NOT EXISTS silver")

# COMMAND ----------

# MAGIC %md ### Rule set
# MAGIC | Table | Rule |
# MAGIC |---|---|
# MAGIC | inventory | `quantity_on_hand >= 0` |
# MAGIC | inventory | `reorder_threshold >= 0` |
# MAGIC | sales | `quantity_sold > 0` |
# MAGIC | sales | `revenue >= 0` |
# MAGIC | orders | `expected_delivery >= order_date` |
# MAGIC | products | `unit_price > 0` |

# COMMAND ----------

def quarantine_failures(df, rule, table_name):
    passed = df.filter(rule)
    failed = df.filter(~rule)
    if failed.count() > 0:
        (failed
         .withColumn("_dq_failed_rule", F.lit(str(rule)))
         .write.format("delta").mode("append")
         .saveAsTable(f"silver.{table_name}_quarantine"))
    print(f"{table_name}: {passed.count()} passed, {failed.count()} quarantined")
    return passed

# COMMAND ----------

inventory = spark.table("silver.inventory")
inventory_clean = quarantine_failures(
    inventory, (F.col("quantity_on_hand") >= 0) & (F.col("reorder_threshold") >= 0), "inventory"
)

sales = spark.table("silver.sales")
sales_clean = quarantine_failures(
    sales, (F.col("quantity_sold") > 0) & (F.col("revenue") >= 0), "sales"
)

orders = spark.table("silver.orders")
orders_clean = quarantine_failures(
    orders, F.col("expected_delivery") >= F.col("order_date"), "orders"
)

products = spark.table("silver.products")
products_clean = quarantine_failures(
    products, F.col("unit_price") > 0, "products"
)

# COMMAND ----------

# MAGIC %md
# MAGIC Only rows that pass every rule should flow to the Gold layer.
# MAGIC Overwrite the silver tables with the validated (clean) versions:

# COMMAND ----------

inventory_clean.write.format("delta").mode("overwrite").saveAsTable("silver.inventory")
sales_clean.write.format("delta").mode("overwrite").saveAsTable("silver.sales")
orders_clean.write.format("delta").mode("overwrite").saveAsTable("silver.orders")
products_clean.write.format("delta").mode("overwrite").saveAsTable("silver.products")
