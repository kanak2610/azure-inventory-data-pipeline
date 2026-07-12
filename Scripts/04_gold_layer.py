"""
04_gold_layer.py
-----------------
LOCAL SIMULATION of the Gold layer aggregations.

Builds the 6 business-facing KPI tables that Power BI connects to:
  1. inventory_snapshot
  2. low_stock_alerts
  3. supplier_performance
  4. product_movement
  5. sales_summary
  6. sales_trends

Real production version: databricks_notebooks/03_gold_kpis.py (Spark SQL /
DataFrame aggregations reading from Silver Delta tables).
"""

import pandas as pd
import os

SILVER_DIR = os.path.join(os.path.dirname(__file__), "..", "silver")
GOLD_DIR = os.path.join(os.path.dirname(__file__), "..", "gold")
os.makedirs(GOLD_DIR, exist_ok=True)

products = pd.read_csv(f"{SILVER_DIR}/products.csv")
warehouse = pd.read_csv(f"{SILVER_DIR}/warehouse.csv")
inventory = pd.read_csv(f"{SILVER_DIR}/inventory.csv", parse_dates=["last_updated"])
orders = pd.read_csv(f"{SILVER_DIR}/orders.csv", parse_dates=["order_date", "expected_delivery", "actual_delivery"])
sales = pd.read_csv(f"{SILVER_DIR}/sales.csv", parse_dates=["sale_date"])
suppliers = pd.read_csv(f"{SILVER_DIR}/suppliers_scd2.csv")
suppliers_current = suppliers[suppliers["is_current"] == True]


# ---------------------------------------------------------------------
# 1. INVENTORY SNAPSHOT
# ---------------------------------------------------------------------
def build_inventory_snapshot():
    df = inventory.merge(products, on="product_id", how="left") \
                   .merge(warehouse, on="warehouse_id", how="left")
    df["stock_value"] = df["quantity_on_hand"] * df["unit_price"]
    out = df[["inventory_id", "product_id", "product_name", "category",
              "warehouse_id", "warehouse_name", "quantity_on_hand",
              "reorder_threshold", "stock_value", "last_updated"]]
    out.to_csv(f"{GOLD_DIR}/inventory_snapshot.csv", index=False)
    print(f"[GOLD] inventory_snapshot   -> {len(out)} rows")
    return out


# ---------------------------------------------------------------------
# 2. LOW STOCK ALERTS
# ---------------------------------------------------------------------
def build_low_stock_alerts(snapshot):
    alerts = snapshot[snapshot["quantity_on_hand"] < snapshot["reorder_threshold"]].copy()
    alerts["shortfall"] = alerts["reorder_threshold"] - alerts["quantity_on_hand"]
    alerts = alerts.sort_values("shortfall", ascending=False)
    alerts.to_csv(f"{GOLD_DIR}/low_stock_alerts.csv", index=False)
    print(f"[GOLD] low_stock_alerts     -> {len(alerts)} rows")
    return alerts


# ---------------------------------------------------------------------
# 3. SUPPLIER PERFORMANCE
# ---------------------------------------------------------------------
def build_supplier_performance():
    df = orders.merge(suppliers_current[["supplier_id", "supplier_name", "rating"]],
                       on="supplier_id", how="left")
    df["on_time"] = df["delay_days"] <= 0
    perf = df.groupby(["supplier_id", "supplier_name"]).agg(
        total_orders=("order_id", "count"),
        avg_delay_days=("delay_days", "mean"),
        on_time_pct=("on_time", "mean"),
        total_qty_ordered=("quantity_ordered", "sum"),
        current_rating=("rating", "first"),
    ).reset_index()
    perf["on_time_pct"] = (perf["on_time_pct"] * 100).round(1)
    perf["avg_delay_days"] = perf["avg_delay_days"].round(2)
    perf = perf.sort_values("on_time_pct", ascending=False)
    perf.to_csv(f"{GOLD_DIR}/supplier_performance.csv", index=False)
    print(f"[GOLD] supplier_performance -> {len(perf)} rows")
    return perf


# ---------------------------------------------------------------------
# 4. PRODUCT MOVEMENT
# ---------------------------------------------------------------------
def build_product_movement():
    move = sales.groupby("product_id").agg(
        total_units_sold=("quantity_sold", "sum"),
        total_revenue=("revenue", "sum"),
        num_sales_txns=("sale_id", "count"),
    ).reset_index()
    move = move.merge(products[["product_id", "product_name", "category"]], on="product_id", how="left")

    # classify movement speed using quantile thresholds
    fast_cut = move["total_units_sold"].quantile(0.66)
    slow_cut = move["total_units_sold"].quantile(0.33)

    def classify(qty):
        if qty >= fast_cut:
            return "Fast-moving"
        elif qty <= slow_cut:
            return "Slow-moving"
        return "Medium-moving"

    move["movement_category"] = move["total_units_sold"].apply(classify)
    move = move.sort_values("total_units_sold", ascending=False)
    move = move[["product_id", "product_name", "category", "total_units_sold",
                 "total_revenue", "num_sales_txns", "movement_category"]]
    move.to_csv(f"{GOLD_DIR}/product_movement.csv", index=False)
    print(f"[GOLD] product_movement     -> {len(move)} rows")
    return move


# ---------------------------------------------------------------------
# 5. SALES SUMMARY
# ---------------------------------------------------------------------
def build_sales_summary():
    df = sales.merge(products[["product_id", "category"]], on="product_id", how="left") \
              .merge(warehouse[["warehouse_id", "warehouse_name"]], on="warehouse_id", how="left")
    summary = df.groupby(["warehouse_id", "warehouse_name", "category"]).agg(
        total_units_sold=("quantity_sold", "sum"),
        total_revenue=("revenue", "sum"),
        num_transactions=("sale_id", "count"),
    ).reset_index().sort_values("total_revenue", ascending=False)
    summary.to_csv(f"{GOLD_DIR}/sales_summary.csv", index=False)
    print(f"[GOLD] sales_summary        -> {len(summary)} rows")
    return summary


# ---------------------------------------------------------------------
# 6. SALES TRENDS (monthly)
# ---------------------------------------------------------------------
def build_sales_trends():
    df = sales.copy()
    df["month"] = df["sale_date"].dt.to_period("M").astype(str)
    trends = df.groupby("month").agg(
        total_units_sold=("quantity_sold", "sum"),
        total_revenue=("revenue", "sum"),
        num_transactions=("sale_id", "count"),
    ).reset_index().sort_values("month")
    trends["revenue_growth_pct"] = trends["total_revenue"].pct_change().mul(100).round(2)
    trends.to_csv(f"{GOLD_DIR}/sales_trends.csv", index=False)
    print(f"[GOLD] sales_trends         -> {len(trends)} rows")
    return trends


if __name__ == "__main__":
    snapshot = build_inventory_snapshot()
    build_low_stock_alerts(snapshot)
    build_supplier_performance()
    build_product_movement()
    build_sales_summary()
    build_sales_trends()
    print("\nGold layer complete ->", os.path.abspath(GOLD_DIR))
