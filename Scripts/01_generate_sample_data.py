"""
01_generate_sample_data.py
---------------------------
Generates 6 raw CSV files that simulate a real inventory & supply chain
system. This mimics what would normally be dropped into ADLS Gen2 "raw/"
container by upstream source systems (ERP, POS, warehouse management, etc.)

Files generated:
    1. products.csv
    2. suppliers.csv        (includes a "day2" version to demo SCD Type 2)
    3. inventory.csv
    4. warehouse.csv
    5. orders.csv           (supplier purchase orders)
    6. sales.csv

Intentional data-quality issues are injected (duplicates, nulls, bad types)
so the Silver layer has real cleaning work to do.
"""

import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta
import os

random.seed(42)
np.random.seed(42)

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "raw")
os.makedirs(RAW_DIR, exist_ok=True)

# ---------------------------------------------------------------------
# 1. WAREHOUSE
# ---------------------------------------------------------------------
warehouses = pd.DataFrame([
    {"warehouse_id": "WH01", "warehouse_name": "Jaipur Central", "location": "Rajasthan", "capacity": 50000},
    {"warehouse_id": "WH02", "warehouse_name": "Delhi North",    "location": "Delhi",     "capacity": 80000},
    {"warehouse_id": "WH03", "warehouse_name": "Mumbai West",    "location": "Maharashtra","capacity": 65000},
])
warehouses.to_csv(f"{RAW_DIR}/warehouse.csv", index=False)

# ---------------------------------------------------------------------
# 2. SUPPLIERS  (Day 1 snapshot + Day 2 snapshot -> feeds SCD Type 2)
# ---------------------------------------------------------------------
suppliers_day1 = pd.DataFrame([
    {"supplier_id": "SUP01", "supplier_name": "Acme Traders",     "address": "Sitapura, Jaipur",      "contact_email": "acme@example.com",     "rating": 4.2, "source_date": "2026-06-01"},
    {"supplier_id": "SUP02", "supplier_name": "Global Parts Co",  "address": "Okhla, Delhi",           "contact_email": "global@example.com",   "rating": 3.8, "source_date": "2026-06-01"},
    {"supplier_id": "SUP03", "supplier_name": "Reliable Supplies","address": "Andheri, Mumbai",        "contact_email": "reliable@example.com", "rating": 4.6, "source_date": "2026-06-01"},
    {"supplier_id": "SUP04", "supplier_name": "Fastrack Vendors", "address": "Vaishali Nagar, Jaipur", "contact_email": "fastrack@example.com", "rating": 3.5, "source_date": "2026-06-01"},
])
suppliers_day1.to_csv(f"{RAW_DIR}/suppliers_2026-06-01.csv", index=False)

# Day 2 feed: SUP01 changes address (rating stays), SUP02 rating drops, SUP05 is new
suppliers_day2 = pd.DataFrame([
    {"supplier_id": "SUP01", "supplier_name": "Acme Traders",     "address": "Malviya Nagar, Jaipur",  "contact_email": "acme@example.com",     "rating": 4.2, "source_date": "2026-07-01"},
    {"supplier_id": "SUP02", "supplier_name": "Global Parts Co",  "address": "Okhla, Delhi",            "contact_email": "global@example.com",   "rating": 3.2, "source_date": "2026-07-01"},
    {"supplier_id": "SUP03", "supplier_name": "Reliable Supplies","address": "Andheri, Mumbai",         "contact_email": "reliable@example.com", "rating": 4.6, "source_date": "2026-07-01"},
    {"supplier_id": "SUP04", "supplier_name": "Fastrack Vendors", "address": "Vaishali Nagar, Jaipur",  "contact_email": "fastrack@example.com", "rating": 3.5, "source_date": "2026-07-01"},
    {"supplier_id": "SUP05", "supplier_name": "NorthStar Supply", "address": "Salt Lake, Kolkata",      "contact_email": "northstar@example.com","rating": 4.0, "source_date": "2026-07-01"},
])
suppliers_day2.to_csv(f"{RAW_DIR}/suppliers_2026-07-01.csv", index=False)

# ---------------------------------------------------------------------
# 3. PRODUCTS
# ---------------------------------------------------------------------
categories = ["Electronics", "Stationery", "Furniture", "Grocery", "Apparel"]
products = []
for i in range(1, 26):
    products.append({
        "product_id": f"P{i:03d}",
        "product_name": f"Product {i}",
        "category": random.choice(categories),
        "unit_price": round(random.uniform(50, 5000), 2),
        "supplier_id": random.choice(["SUP01", "SUP02", "SUP03", "SUP04", "SUP05"]),
    })
products_df = pd.DataFrame(products)
# inject a duplicate row and a null price (data quality issue for Silver to fix)
products_df = pd.concat([products_df, products_df.iloc[[3]]], ignore_index=True)
products_df.loc[7, "unit_price"] = np.nan
products_df.to_csv(f"{RAW_DIR}/products.csv", index=False)

# ---------------------------------------------------------------------
# 4. INVENTORY (current stock per product per warehouse)
# ---------------------------------------------------------------------
inventory = []
inv_id = 1
for p in products_df["product_id"].unique():
    for w in warehouses["warehouse_id"]:
        inventory.append({
            "inventory_id": f"INV{inv_id:04d}",
            "product_id": p,
            "warehouse_id": w,
            "quantity_on_hand": random.randint(0, 500),
            "reorder_threshold": random.randint(50, 150),
            "last_updated": (datetime(2026, 7, 1) + timedelta(days=random.randint(0, 10))).strftime("%Y-%m-%d"),
        })
        inv_id += 1
inventory_df = pd.DataFrame(inventory)
inventory_df.to_csv(f"{RAW_DIR}/inventory.csv", index=False)

# ---------------------------------------------------------------------
# 5. ORDERS (purchase orders placed to suppliers)
# ---------------------------------------------------------------------
orders = []
for i in range(1, 121):
    order_date = datetime(2026, 5, 1) + timedelta(days=random.randint(0, 70))
    expected = order_date + timedelta(days=random.randint(3, 10))
    delay = random.choice([0, 0, 0, 1, 2, 3, -1])  # most on time, some late/early
    actual = expected + timedelta(days=delay)
    orders.append({
        "order_id": f"ORD{i:04d}",
        "product_id": random.choice(products_df["product_id"].unique()),
        "supplier_id": random.choice(["SUP01", "SUP02", "SUP03", "SUP04", "SUP05"]),
        "order_date": order_date.strftime("%Y-%m-%d"),
        "expected_delivery": expected.strftime("%Y-%m-%d"),
        "actual_delivery": actual.strftime("%Y-%m-%d"),
        "quantity_ordered": random.randint(10, 200),
        "status": "Delivered",
    })
orders_df = pd.DataFrame(orders)
orders_df.to_csv(f"{RAW_DIR}/orders.csv", index=False)

# ---------------------------------------------------------------------
# 6. SALES
# ---------------------------------------------------------------------
sales = []
for i in range(1, 401):
    sale_date = datetime(2026, 5, 1) + timedelta(days=random.randint(0, 71))
    product_id = random.choice(products_df["product_id"].unique())
    price_row = products_df.loc[products_df["product_id"] == product_id, "unit_price"]
    unit_price = float(price_row.iloc[0]) if not pd.isna(price_row.iloc[0]) else 100.0
    qty = random.randint(1, 20)
    sales.append({
        "sale_id": f"SALE{i:05d}",
        "product_id": product_id,
        "warehouse_id": random.choice(warehouses["warehouse_id"].tolist()),
        "sale_date": sale_date.strftime("%Y-%m-%d"),
        "quantity_sold": qty,
        "unit_price": unit_price,
        "revenue": round(qty * unit_price, 2),
    })
sales_df = pd.DataFrame(sales)
sales_df.to_csv(f"{RAW_DIR}/sales.csv", index=False)

print("Raw data generated in:", os.path.abspath(RAW_DIR))
for f in sorted(os.listdir(RAW_DIR)):
    print("  -", f)
