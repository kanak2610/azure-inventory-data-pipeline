"""
00_run_pipeline.py
-------------------
Runs the entire local simulation pipeline end-to-end:
    Raw -> Bronze -> Silver -> Gold -> Dashboard (auto-opens in browser)

Usage:
    python 00_run_pipeline.py

Set NO_BROWSER=1 as an environment variable to build the dashboard
without auto-opening it (useful for CI / headless runs).
"""

import subprocess
import sys
import os

SCRIPTS_DIR = os.path.dirname(__file__)

STEPS = [
    "01_generate_sample_data.py",
    "02_bronze_layer.py",
    "03_silver_layer.py",
    "04_gold_layer.py",
    "05_generate_dashboard.py",
]

for step in STEPS:
    print(f"\n{'='*60}\nRUNNING: {step}\n{'='*60}")
    result = subprocess.run([sys.executable, os.path.join(SCRIPTS_DIR, step)])
    if result.returncode != 0:
        print(f"Pipeline failed at step: {step}")
        sys.exit(1)

print("\nPIPELINE COMPLETE. Check the raw/, bronze/, silver/, gold/ folders.")
print("Dashboard built at dashboard/index.html and opened in your browser.")
