"""
03_silver_layer.py
-------------------
LOCAL SIMULATION of the Silver layer transformation logic.

Real Databricks version uses Delta Lake MERGE for SCD Type 2:
See databricks_notebooks/02_silver_transform_scd2.py for the production
PySpark + Delta MERGE INTO code.

What happens here (same business logic, executed with pandas so it can
run end-to-end offline):
  1. Type casting          -> correct dtypes for dates/numbers
  2. Deduplication          -> drop exact duplicate rows
  3. Validation             -> drop/flag nulls & invalid values
  4. SCD Type 2              -> suppliers table tracks full history:
                                  is_current, effective_start, effective_end
"""

import pandas as pd
import os

BRONZE_DIR = os.path.join(os.path.dirname(__file__), "..", "bronze")
SILVER_DIR = os.path.join(os.path.dirname(__file__), "..", "silver")
os.makedirs(SILVER_DIR, exist_ok=True)


def clean_products():
    df = pd.read_csv(f"{BRONZE_DIR}/products.csv")
    before = len(df)
    df = df.drop_duplicates(subset=["product_id"])                     # dedup
    df = df.dropna(subset=["product_id", "product_name"])              # validation
    df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce")
    df["unit_price"] = df["unit_price"].fillna(df["unit_price"].median())  # impute missing price
    df = df[["product_id", "product_name", "category", "unit_price", "supplier_id"]]
    df.to_csv(f"{SILVER_DIR}/products.csv", index=False)
    print(f"[SILVER] products     {before} -> {len(df)} rows (deduped + price nulls fixed)")
    return df


def clean_warehouse():
    df = pd.read_csv(f"{BRONZE_DIR}/warehouse.csv")
    df = df.drop_duplicates(subset=["warehouse_id"])
    df.to_csv(f"{SILVER_DIR}/warehouse.csv", index=False)
    print(f"[SILVER] warehouse    {len(df)} rows")
    return df


def clean_inventory():
    df = pd.read_csv(f"{BRONZE_DIR}/inventory.csv")
    before = len(df)
    df = df.drop_duplicates(subset=["inventory_id"])
    df["quantity_on_hand"] = pd.to_numeric(df["quantity_on_hand"], errors="coerce").fillna(0).astype(int)
    df["reorder_threshold"] = pd.to_numeric(df["reorder_threshold"], errors="coerce").fillna(0).astype(int)
    df["last_updated"] = pd.to_datetime(df["last_updated"], errors="coerce")
    df = df.dropna(subset=["product_id", "warehouse_id"])
    df.to_csv(f"{SILVER_DIR}/inventory.csv", index=False)
    print(f"[SILVER] inventory    {before} -> {len(df)} rows")
    return df


def clean_orders():
    df = pd.read_csv(f"{BRONZE_DIR}/orders.csv")
    before = len(df)
    df = df.drop_duplicates(subset=["order_id"])
    for col in ["order_date", "expected_delivery", "actual_delivery"]:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    df["quantity_ordered"] = pd.to_numeric(df["quantity_ordered"], errors="coerce").fillna(0).astype(int)
    df = df.dropna(subset=["order_id", "supplier_id", "product_id"])
    df["delay_days"] = (df["actual_delivery"] - df["expected_delivery"]).dt.days
    df.to_csv(f"{SILVER_DIR}/orders.csv", index=False)
    print(f"[SILVER] orders       {before} -> {len(df)} rows (delay_days computed)")
    return df


def clean_sales():
    df = pd.read_csv(f"{BRONZE_DIR}/sales.csv")
    before = len(df)
    df = df.drop_duplicates(subset=["sale_id"])
    df["sale_date"] = pd.to_datetime(df["sale_date"], errors="coerce")
    df["quantity_sold"] = pd.to_numeric(df["quantity_sold"], errors="coerce").fillna(0).astype(int)
    df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce")
    df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce")
    df = df.dropna(subset=["sale_id", "product_id", "warehouse_id"])
    df = df[df["quantity_sold"] > 0]  # validation: no zero/negative sales
    df.to_csv(f"{SILVER_DIR}/sales.csv", index=False)
    print(f"[SILVER] sales        {before} -> {len(df)} rows")
    return df


def scd_type2_suppliers():
    """
    Implements SCD Type 2 for the suppliers dimension.

    Logic (identical to the Delta MERGE INTO pattern used in production):
      - For each supplier_id, sort all incoming snapshots by source_date.
      - Compare each row to the previous row for that supplier_id across
        the tracked attributes (address, rating).
      - If nothing changed -> keep as one continuous history record.
      - If something changed -> close out the previous record
        (is_current=False, effective_end = new record's start) and open
        a new current record (is_current=True, effective_end=NULL).
    """
    df = pd.read_csv(f"{BRONZE_DIR}/suppliers.csv")
    df["source_date"] = pd.to_datetime(df["source_date"])
    df = df.drop_duplicates()
    df = df.sort_values(["supplier_id", "source_date"])

    tracked_cols = ["address", "rating"]
    history_rows = []

    for supplier_id, group in df.groupby("supplier_id"):
        group = group.sort_values("source_date").reset_index(drop=True)
        current_row = None
        for _, row in group.iterrows():
            if current_row is None:
                current_row = row.copy()
                current_row["effective_start"] = row["source_date"]
                current_row["effective_end"] = pd.NaT
                current_row["is_current"] = True
                continue

            changed = any(row[c] != current_row[c] for c in tracked_cols)
            if changed:
                # close out old record
                closed = current_row.copy()
                closed["effective_end"] = row["source_date"]
                closed["is_current"] = False
                history_rows.append(closed)

                # open new current record
                current_row = row.copy()
                current_row["effective_start"] = row["source_date"]
                current_row["effective_end"] = pd.NaT
                current_row["is_current"] = True
            # if unchanged, current_row stays open (do nothing)

        history_rows.append(current_row)

    scd_df = pd.DataFrame(history_rows)
    scd_df = scd_df[[
        "supplier_id", "supplier_name", "address", "contact_email", "rating",
        "effective_start", "effective_end", "is_current"
    ]].sort_values(["supplier_id", "effective_start"])

    scd_df.to_csv(f"{SILVER_DIR}/suppliers_scd2.csv", index=False)
    print(f"[SILVER] suppliers    {len(scd_df)} history rows (SCD Type 2) "
          f"-> {scd_df['is_current'].sum()} current records")
    return scd_df


if __name__ == "__main__":
    clean_products()
    clean_warehouse()
    clean_inventory()
    clean_orders()
    clean_sales()
    scd_df = scd_type2_suppliers()

    print("\n--- SCD Type 2 preview (SUP01 changed address on 2026-07-01) ---")
    print(scd_df[scd_df["supplier_id"] == "SUP01"].to_string(index=False))

    print("\nSilver layer complete ->", os.path.abspath(SILVER_DIR))
