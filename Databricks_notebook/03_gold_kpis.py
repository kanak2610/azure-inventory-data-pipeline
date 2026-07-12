# Databricks notebook source
# MAGIC %md
# MAGIC # Gold Layer - Business KPI Tables
# MAGIC Aggregates Silver Delta tables into 6 analytics-ready KPI tables
# MAGIC that Power BI connects to directly (via Databricks SQL endpoint).

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql.window import Window

spark.sql("CREATE SCHEMA IF NOT EXISTS gold")

products = spark.table("silver.products")
warehouse = spark.table("silver.warehouse")
inventory = spark.table("silver.inventory")
orders = spark.table("silver.orders")
sales = spark.table("silver.sales")
suppliers_current = spark.table("silver.suppliers_scd2").filter("is_current = true")

# COMMAND ----------

# MAGIC %md ## 1. Inventory Snapshot

# COMMAND ----------

inventory_snapshot = (
    inventory
    .join(products, "product_id", "left")
    .join(warehouse, "warehouse_id", "left")
    .withColumn("stock_value", F.col("quantity_on_hand") * F.col("unit_price"))
    .select("inventory_id", "product_id", "product_name", "category",
            "warehouse_id", "warehouse_name", "quantity_on_hand",
            "reorder_threshold", "stock_value", "last_updated")
)
inventory_snapshot.write.format("delta").mode("overwrite").saveAsTable("gold.inventory_snapshot")

# COMMAND ----------

# MAGIC %md ## 2. Low Stock Alerts

# COMMAND ----------

low_stock_alerts = (
    inventory_snapshot
    .filter(F.col("quantity_on_hand") < F.col("reorder_threshold"))
    .withColumn("shortfall", F.col("reorder_threshold") - F.col("quantity_on_hand"))
    .orderBy(F.col("shortfall").desc())
)
low_stock_alerts.write.format("delta").mode("overwrite").saveAsTable("gold.low_stock_alerts")

# COMMAND ----------

# MAGIC %md ## 3. Supplier Performance

# COMMAND ----------

supplier_performance = (
    orders
    .join(suppliers_current.select("supplier_id", "supplier_name", "rating"), "supplier_id", "left")
    .withColumn("on_time", F.col("delay_days") <= 0)
    .groupBy("supplier_id", "supplier_name")
    .agg(
        F.count("order_id").alias("total_orders"),
        F.round(F.avg("delay_days"), 2).alias("avg_delay_days"),
        F.round(F.avg(F.col("on_time").cast("int")) * 100, 1).alias("on_time_pct"),
        F.sum("quantity_ordered").alias("total_qty_ordered"),
        F.first("rating").alias("current_rating"),
    )
    .orderBy(F.col("on_time_pct").desc())
)
supplier_performance.write.format("delta").mode("overwrite").saveAsTable("gold.supplier_performance")

# COMMAND ----------

# MAGIC %md ## 4. Product Movement

# COMMAND ----------

product_movement_base = (
    sales.groupBy("product_id")
    .agg(
        F.sum("quantity_sold").alias("total_units_sold"),
        F.sum("revenue").alias("total_revenue"),
        F.count("sale_id").alias("num_sales_txns"),
    )
)

fast_cut, slow_cut = product_movement_base.approxQuantile("total_units_sold", [0.66, 0.33], 0.01)

product_movement = (
    product_movement_base
    .join(products.select("product_id", "product_name", "category"), "product_id", "left")
    .withColumn(
        "movement_category",
        F.when(F.col("total_units_sold") >= fast_cut, "Fast-moving")
         .when(F.col("total_units_sold") <= slow_cut, "Slow-moving")
         .otherwise("Medium-moving")
    )
    .orderBy(F.col("total_units_sold").desc())
)
product_movement.write.format("delta").mode("overwrite").saveAsTable("gold.product_movement")

# COMMAND ----------

# MAGIC %md ## 5. Sales Summary

# COMMAND ----------

sales_summary = (
    sales
    .join(products.select("product_id", "category"), "product_id", "left")
    .join(warehouse.select("warehouse_id", "warehouse_name"), "warehouse_id", "left")
    .groupBy("warehouse_id", "warehouse_name", "category")
    .agg(
        F.sum("quantity_sold").alias("total_units_sold"),
        F.sum("revenue").alias("total_revenue"),
        F.count("sale_id").alias("num_transactions"),
    )
    .orderBy(F.col("total_revenue").desc())
)
sales_summary.write.format("delta").mode("overwrite").saveAsTable("gold.sales_summary")

# COMMAND ----------

# MAGIC %md ## 6. Sales Trends (monthly)

# COMMAND ----------

sales_trends_base = (
    sales
    .withColumn("month", F.date_format("sale_date", "yyyy-MM"))
    .groupBy("month")
    .agg(
        F.sum("quantity_sold").alias("total_units_sold"),
        F.sum("revenue").alias("total_revenue"),
        F.count("sale_id").alias("num_transactions"),
    )
)

month_window = Window.orderBy("month")
sales_trends = (
    sales_trends_base
    .withColumn("prev_revenue", F.lag("total_revenue").over(month_window))
    .withColumn(
        "revenue_growth_pct",
        F.round((F.col("total_revenue") - F.col("prev_revenue")) / F.col("prev_revenue") * 100, 2)
    )
    .drop("prev_revenue")
    .orderBy("month")
)
sales_trends.write.format("delta").mode("overwrite").saveAsTable("gold.sales_trends")

# COMMAND ----------

# MAGIC %md ## Sanity check - row counts

# COMMAND ----------

for t in ["inventory_snapshot", "low_stock_alerts", "supplier_performance",
          "product_movement", "sales_summary", "sales_trends"]:
    print(f"gold.{t}: {spark.table(f'gold.{t}').count()} rows")
