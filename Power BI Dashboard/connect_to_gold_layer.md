# Connecting Power BI to the Gold Layer

1. In Power BI Desktop: **Get Data > Azure > Azure Databricks**
2. Enter the **Server Hostname** and **HTTP Path** of your Databricks SQL
   warehouse (found under Databricks: SQL Warehouses > your warehouse > Connection details)
3. Authenticate (Azure AD or Personal Access Token)
4. Select the `gold` schema and load these 6 tables:
   - `inventory_snapshot`
   - `low_stock_alerts`
   - `supplier_performance`
   - `product_movement`
   - `sales_summary`
   - `sales_trends`
5. Prefer **DirectQuery** mode over Import if you want near real-time
   refresh as new data lands in Gold; use **Import** for faster report
   interaction if the tables are small and refreshed on a schedule.

## Suggested dashboard pages
- **Inventory Health**: cards for total stock value, low stock alert count;
  table of `low_stock_alerts` sorted by shortfall
- **Supplier Performance**: bar chart of on-time % by supplier;
  scatter of avg delay days vs current rating
- **Sales Trends**: line chart of `sales_trends` monthly revenue with
  growth % as a secondary axis; matrix of `sales_summary` by warehouse/category
