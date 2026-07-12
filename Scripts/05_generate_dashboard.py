"""
05_generate_dashboard.py
-------------------------
Builds the local HTML dashboard directly from the Gold layer CSVs.

This is NOT a static mockup — every KPI number, table row, and chart
value below is computed live from whatever is currently sitting in
gold/*.csv. Re-run the pipeline with different data and the dashboard
regenerates with new numbers automatically.

Output: dashboard/index.html

In production this same gold/*.csv data lives in Databricks SQL tables
and Power BI connects to them live (see powerbi/connect_to_gold_layer.md).
This local HTML dashboard exists so you can see and demo the exact same
KPIs instantly, without needing an Azure/Power BI license.

Usage:
    python 05_generate_dashboard.py
"""

import pandas as pd
import os
import json
import webbrowser
from datetime import datetime

GOLD_DIR = os.path.join(os.path.dirname(__file__), "..", "gold")
DASHBOARD_DIR = os.path.join(os.path.dirname(__file__), "..", "dashboard")
os.makedirs(DASHBOARD_DIR, exist_ok=True)

MONTH_NAMES = {
    "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr", "05": "May", "06": "Jun",
    "07": "Jul", "08": "Aug", "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec",
}


def month_label(ym: str) -> str:
    year, month = ym.split("-")
    return f"{MONTH_NAMES[month]} {year}"


def lakh(value: float) -> float:
    return round(value / 1e5, 1)


def load_gold():
    return {
        "inventory": pd.read_csv(f"{GOLD_DIR}/inventory_snapshot.csv"),
        "low_stock": pd.read_csv(f"{GOLD_DIR}/low_stock_alerts.csv"),
        "suppliers": pd.read_csv(f"{GOLD_DIR}/supplier_performance.csv"),
        "movement": pd.read_csv(f"{GOLD_DIR}/product_movement.csv"),
        "trends": pd.read_csv(f"{GOLD_DIR}/sales_trends.csv"),
    }


def build_kpis(g):
    inv, low, sup, mov, trend = g["inventory"], g["low_stock"], g["suppliers"], g["movement"], g["trends"]

    best_sup = sup.loc[sup["on_time_pct"].idxmax()]
    top_rated = sup.loc[sup["current_rating"].idxmax()]
    latest_month = trend.iloc[-1]
    latest_growth = latest_month["revenue_growth_pct"]

    return {
        "total_stock_value_L": lakh(inv["stock_value"].sum()),
        "low_stock_count": int(len(low)),
        "inventory_rows": int(len(inv)),
        "warehouse_count": int(inv["warehouse_id"].nunique()),

        "avg_on_time_pct": round(sup["on_time_pct"].mean(), 1),
        "total_orders_3mo": int(sup["total_orders"].sum()),
        "best_supplier_name": best_sup["supplier_name"],
        "best_supplier_pct": round(best_sup["on_time_pct"], 1),
        "top_rated_name": top_rated["supplier_name"],
        "top_rated_score": round(top_rated["current_rating"], 1),

        "revenue_3mo_L": lakh(trend["total_revenue"].sum()),
        "units_3mo": int(trend["total_units_sold"].sum()),
        "latest_growth_pct": None if pd.isna(latest_growth) else round(latest_growth, 1),
        "fast_moving_count": int((mov["movement_category"] == "Fast-moving").sum()),
    }


def build_low_stock_rows(low, n=6):
    top = low.sort_values("shortfall", ascending=False).head(n)
    rows = ""
    for _, r in top.iterrows():
        rows += (f"<tr><td>{r.product_name}</td><td>{r.warehouse_name}</td>"
                  f"<td>{int(r.quantity_on_hand)}</td><td>{int(r.reorder_threshold)}</td>"
                  f"<td><span class=\"pill\">{int(r.shortfall)}</span></td></tr>\n")
    return rows


def build_supplier_rows(sup):
    ordered = sup.sort_values("on_time_pct", ascending=False)
    rows = ""
    for _, r in ordered.iterrows():
        rows += (f"<tr><td>{r.supplier_name}</td><td>{int(r.total_orders)}</td>"
                  f"<td>{r.avg_delay_days:.2f}d</td><td>{r.on_time_pct:.1f}%</td>"
                  f"<td>{r.current_rating:.1f}</td></tr>\n")
    return rows


def movement_pill_class(category):
    return {"Fast-moving": "fast", "Medium-moving": "medium", "Slow-moving": "slow"}.get(category, "")


def build_movement_rows(mov, n=5):
    top = mov.sort_values("total_units_sold", ascending=False).head(n)
    rows = ""
    for _, r in top.iterrows():
        label = r.movement_category.replace("-moving", "")
        rows += (f"<tr><td>{r.product_name}</td><td>{r.category}</td>"
                  f"<td>{int(r.total_units_sold)}</td>"
                  f"<td><span class=\"pill {movement_pill_class(r.movement_category)}\">{label}</span></td></tr>\n")
    return rows


def build_chart_data(g):
    inv, sup, trend = g["inventory"], g["suppliers"], g["trends"]

    wh = inv.groupby("warehouse_name")["stock_value"].sum().sort_values()
    wh_labels = list(wh.index)
    wh_values = [lakh(v) for v in wh.values]

    sup_sorted = sup.sort_values("on_time_pct", ascending=False)
    sup_labels = [n.split()[0] for n in sup_sorted["supplier_name"]]
    sup_values = [round(v, 1) for v in sup_sorted["on_time_pct"]]

    trend_labels = [month_label(m) for m in trend["month"]]
    trend_values = [lakh(v) for v in trend["total_revenue"]]

    return {
        "wh_labels": wh_labels, "wh_values": wh_values,
        "sup_labels": sup_labels, "sup_values": sup_values,
        "trend_labels": trend_labels, "trend_values": trend_values,
    }


TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Inventory & Supply Chain Dashboard</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<style>
  :root{{
    --bg:#12141a; --panel:#1a1d26; --panel2:#20232e; --border:#2b2f3b;
    --text:#e8e9ed; --sub:#9498a6; --muted:#6b6f7d;
    --accent:#3a7bd5; --accent2:#5fd0a6; --warn:#e0a23a; --danger:#e5636b;
  }}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif}}
  header{{padding:20px 28px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center}}
  header h1{{font-size:18px;font-weight:600;margin:0;letter-spacing:.2px}}
  header p{{margin:2px 0 0;font-size:12px;color:var(--muted)}}
  nav{{display:flex;gap:4px;padding:14px 28px 0}}
  nav button{{background:none;border:none;color:var(--sub);font-size:13px;padding:10px 16px;border-radius:8px 8px 0 0;cursor:pointer;border-bottom:2px solid transparent}}
  nav button.active{{color:var(--text);border-bottom:2px solid var(--accent);background:var(--panel)}}
  main{{padding:24px 28px 40px}}
  .page{{display:none}}
  .page.active{{display:block}}
  .kpi-row{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:22px}}
  .kpi{{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:16px 18px}}
  .kpi .label{{font-size:12px;color:var(--sub);margin-bottom:6px}}
  .kpi .value{{font-size:24px;font-weight:600}}
  .kpi .value.danger{{color:var(--danger)}}
  .kpi .value.good{{color:var(--accent2)}}
  .grid2{{display:grid;grid-template-columns:1.3fr 1fr;gap:16px;margin-bottom:16px}}
  .card{{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:18px}}
  .card h3{{margin:0 0 14px;font-size:13px;font-weight:600;color:var(--sub);text-transform:uppercase;letter-spacing:.4px}}
  table{{width:100%;border-collapse:collapse;font-size:13px}}
  th{{text-align:left;color:var(--muted);font-weight:500;padding:8px 6px;border-bottom:1px solid var(--border);font-size:11px;text-transform:uppercase}}
  td{{padding:9px 6px;border-bottom:1px solid var(--border)}}
  tr:last-child td{{border-bottom:none}}
  .pill{{font-size:11px;padding:2px 8px;border-radius:20px;background:rgba(229,99,107,.15);color:var(--danger)}}
  .pill.fast{{background:rgba(95,208,166,.15);color:var(--accent2)}}
  .pill.medium{{background:rgba(224,162,58,.15);color:var(--warn)}}
  .pill.slow{{background:rgba(229,99,107,.15);color:var(--danger)}}
  .chart-wrap{{position:relative;width:100%}}
  footer{{padding:14px 28px;border-top:1px solid var(--border);font-size:11px;color:var(--muted)}}
</style>
</head>
<body>

<header>
  <div>
    <h1>Inventory & supply chain dashboard</h1>
    <p>Source: gold layer &middot; local pipeline output (gold/*.csv) &middot; regenerate anytime with 05_generate_dashboard.py</p>
  </div>
  <p style="font-size:12px;color:var(--muted)">Last refresh: {refresh_date}</p>
</header>

<nav>
  <button class="tab active" data-page="p1">Inventory health</button>
  <button class="tab" data-page="p2">Supplier performance</button>
  <button class="tab" data-page="p3">Sales trends</button>
</nav>

<main>

  <div class="page active" id="p1">
    <div class="kpi-row">
      <div class="kpi"><div class="label">Total stock value</div><div class="value">&#8377;{total_stock_value_L}L</div></div>
      <div class="kpi"><div class="label">Low stock alerts</div><div class="value danger">{low_stock_count}</div></div>
      <div class="kpi"><div class="label">Inventory rows tracked</div><div class="value">{inventory_rows}</div></div>
      <div class="kpi"><div class="label">Warehouses</div><div class="value">{warehouse_count}</div></div>
    </div>
    <div class="grid2">
      <div class="card">
        <h3>Low stock alerts &mdash; top shortfalls</h3>
        <table>
          <tr><th>Product</th><th>Warehouse</th><th>On hand</th><th>Threshold</th><th>Shortfall</th></tr>
          {low_stock_rows}
        </table>
      </div>
      <div class="card">
        <h3>Stock value by warehouse</h3>
        <div class="chart-wrap" style="height:280px"><canvas id="stockChart" role="img" aria-label="Bar chart of stock value by warehouse"></canvas></div>
      </div>
    </div>
  </div>

  <div class="page" id="p2">
    <div class="kpi-row">
      <div class="kpi"><div class="label">Avg on-time delivery</div><div class="value">{avg_on_time_pct}%</div></div>
      <div class="kpi"><div class="label">Total orders (3mo)</div><div class="value">{total_orders_3mo}</div></div>
      <div class="kpi"><div class="label">Best on-time supplier</div><div class="value good">{best_supplier_name} {best_supplier_pct}%</div></div>
      <div class="kpi"><div class="label">Highest rated</div><div class="value">{top_rated_name} {top_rated_score}</div></div>
    </div>
    <div class="grid2">
      <div class="card">
        <h3>On-time delivery % by supplier</h3>
        <div class="chart-wrap" style="height:280px"><canvas id="supChart" role="img" aria-label="Bar chart of on-time delivery percent by supplier"></canvas></div>
      </div>
      <div class="card">
        <h3>Supplier scorecard</h3>
        <table>
          <tr><th>Supplier</th><th>Orders</th><th>Avg delay</th><th>On-time</th><th>Rating</th></tr>
          {supplier_rows}
        </table>
      </div>
    </div>
  </div>

  <div class="page" id="p3">
    <div class="kpi-row">
      <div class="kpi"><div class="label">Revenue (3 months)</div><div class="value">&#8377;{revenue_3mo_L}L</div></div>
      <div class="kpi"><div class="label">Units sold (3 months)</div><div class="value">{units_3mo}</div></div>
      <div class="kpi"><div class="label">Latest month growth</div><div class="value {growth_class}">{growth_display}</div></div>
      <div class="kpi"><div class="label">Fast-moving products</div><div class="value good">{fast_moving_count}</div></div>
    </div>
    <div class="grid2">
      <div class="card">
        <h3>Monthly revenue trend</h3>
        <div class="chart-wrap" style="height:280px"><canvas id="trendChart" role="img" aria-label="Line chart of monthly revenue"></canvas></div>
      </div>
      <div class="card">
        <h3>Top moving products</h3>
        <table>
          <tr><th>Product</th><th>Category</th><th>Units sold</th><th>Movement</th></tr>
          {movement_rows}
        </table>
      </div>
    </div>
  </div>

</main>

<footer>Local dashboard rendered live from this project's gold/*.csv pipeline output. In production this connects live to Databricks SQL via Power BI &mdash; see powerbi/connect_to_gold_layer.md</footer>

<script>
document.querySelectorAll('.tab').forEach(btn=>{{
  btn.addEventListener('click',()=>{{
    document.querySelectorAll('.tab').forEach(b=>b.classList.remove('active'));
    document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById(btn.dataset.page).classList.add('active');
  }});
}});

const gridColor = '#2b2f3b';
const textColor = '#9498a6';

new Chart(document.getElementById('stockChart'), {{
  type: 'bar',
  data: {{ labels: {wh_labels_json},
    datasets: [{{ data: {wh_values_json}, backgroundColor:'#3a7bd5', borderRadius:4, maxBarThickness:50 }}] }},
  options: {{ responsive:true, maintainAspectRatio:false,
    plugins:{{ legend:{{display:false}}, tooltip:{{callbacks:{{label:c=>'₹'+c.raw+'L'}}}} }},
    scales:{{ y:{{ ticks:{{color:textColor,callback:v=>'₹'+v+'L'}}, grid:{{color:gridColor}} }},
             x:{{ ticks:{{color:textColor}}, grid:{{display:false}} }} }} }}
}});

new Chart(document.getElementById('supChart'), {{
  type: 'bar',
  data: {{ labels: {sup_labels_json},
    datasets: [{{ data:{sup_values_json}, backgroundColor:'#5fd0a6', borderRadius:4, maxBarThickness:36 }}] }},
  options: {{ responsive:true, maintainAspectRatio:false,
    plugins:{{ legend:{{display:false}}, tooltip:{{callbacks:{{label:c=>c.raw+'%'}}}} }},
    scales:{{ y:{{ beginAtZero:true, max:80, ticks:{{color:textColor,callback:v=>v+'%'}}, grid:{{color:gridColor}} }},
             x:{{ ticks:{{color:textColor}}, grid:{{display:false}} }} }} }}
}});

new Chart(document.getElementById('trendChart'), {{
  type: 'line',
  data: {{ labels:{trend_labels_json},
    datasets:[{{ data:{trend_values_json}, borderColor:'#3a7bd5', backgroundColor:'rgba(58,123,213,.1)',
      fill:true, tension:.3, pointRadius:4, pointBackgroundColor:'#3a7bd5' }}] }},
  options: {{ responsive:true, maintainAspectRatio:false,
    plugins:{{ legend:{{display:false}}, tooltip:{{callbacks:{{label:c=>'₹'+c.raw+'L'}}}} }},
    scales:{{ y:{{ ticks:{{color:textColor,callback:v=>'₹'+v+'L'}}, grid:{{color:gridColor}} }},
             x:{{ ticks:{{color:textColor}}, grid:{{display:false}} }} }} }}
}});
</script>

</body>
</html>
"""


def render(g):
    k = build_kpis(g)
    c = build_chart_data(g)

    growth = k["latest_growth_pct"]
    if growth is None:
        growth_display, growth_class = "N/A", ""
    else:
        growth_display = f"{growth:+.1f}%"
        growth_class = "danger" if growth < 0 else "good"

    html = TEMPLATE.format(
        refresh_date=datetime.now().strftime("%Y-%m-%d"),
        total_stock_value_L=k["total_stock_value_L"],
        low_stock_count=k["low_stock_count"],
        inventory_rows=k["inventory_rows"],
        warehouse_count=k["warehouse_count"],
        low_stock_rows=build_low_stock_rows(g["low_stock"]),

        avg_on_time_pct=k["avg_on_time_pct"],
        total_orders_3mo=k["total_orders_3mo"],
        best_supplier_name=k["best_supplier_name"],
        best_supplier_pct=k["best_supplier_pct"],
        top_rated_name=k["top_rated_name"],
        top_rated_score=k["top_rated_score"],
        supplier_rows=build_supplier_rows(g["suppliers"]),

        revenue_3mo_L=k["revenue_3mo_L"],
        units_3mo=k["units_3mo"],
        growth_display=growth_display,
        growth_class=growth_class,
        fast_moving_count=k["fast_moving_count"],
        movement_rows=build_movement_rows(g["movement"]),

        wh_labels_json=json.dumps(c["wh_labels"]),
        wh_values_json=json.dumps(c["wh_values"]),
        sup_labels_json=json.dumps(c["sup_labels"]),
        sup_values_json=json.dumps(c["sup_values"]),
        trend_labels_json=json.dumps(c["trend_labels"]),
        trend_values_json=json.dumps(c["trend_values"]),
    )
    return html


if __name__ == "__main__":
    gold = load_gold()
    html = render(gold)
    out_path = os.path.join(DASHBOARD_DIR, "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[DASHBOARD] built -> {os.path.abspath(out_path)}")

    # Auto-open in the default browser (skip if explicitly disabled, e.g. CI runs)
    if os.environ.get("NO_BROWSER") != "1":
        webbrowser.open(f"file://{os.path.abspath(out_path)}")
        print("[DASHBOARD] opened in default browser")
