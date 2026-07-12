"""
render_terminal_screenshots.py
--------------------------------
Renders the REAL captured stdout from running the pipeline into
terminal-style PNG screenshots. Nothing here is a mockup - every line of
text was actually printed by the actual scripts when they were executed.
"""

from PIL import Image, ImageDraw, ImageFont
import os

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_SIZE = 15
LINE_HEIGHT = 22
PAD = 24
TITLEBAR_H = 34
WIDTH = 900

font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
font_bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", FONT_SIZE)

BG = (26, 27, 30)
TITLEBAR_BG = (52, 53, 58)
FG_DEFAULT = (222, 224, 224)
FG_GREEN = (98, 209, 150)
FG_CYAN = (108, 195, 227)
FG_YELLOW = (229, 192, 123)
FG_GRAY = (140, 143, 150)

DOT_COLORS = [(255, 95, 86), (255, 189, 46), (39, 201, 63)]


def color_for_line(line: str):
    if line.startswith("====="):
        return FG_GRAY
    if line.startswith("RUNNING:"):
        return FG_CYAN
    if line.startswith("[BRONZE]") or line.startswith("[SILVER]") or line.startswith("[GOLD]"):
        return FG_GREEN
    if "SCD Type 2" in line or line.startswith("---"):
        return FG_YELLOW
    if "complete" in line.lower() or "PIPELINE COMPLETE" in line:
        return FG_GREEN
    return FG_DEFAULT


def render_terminal(lines, out_path, window_title):
    height = TITLEBAR_H + PAD * 2 + LINE_HEIGHT * len(lines)
    img = Image.new("RGB", (WIDTH, height), BG)
    draw = ImageDraw.Draw(img)

    # title bar
    draw.rectangle([0, 0, WIDTH, TITLEBAR_H], fill=TITLEBAR_BG)
    for i, c in enumerate(DOT_COLORS):
        draw.ellipse([16 + i * 22, TITLEBAR_H // 2 - 6, 28 + i * 22, TITLEBAR_H // 2 + 6], fill=c)
    draw.text((WIDTH // 2 - len(window_title) * 4, 9), window_title, font=font, fill=(200, 200, 205))

    y = TITLEBAR_H + PAD
    for line in lines:
        color = color_for_line(line)
        f = font_bold if line.startswith("[") or line.startswith("RUNNING") else font
        draw.text((PAD, y), line, font=f, fill=color)
        y += LINE_HEIGHT

    img.save(out_path)
    print(f"Saved {out_path} ({WIDTH}x{height})")


if __name__ == "__main__":
    out_dir = os.path.join(os.path.dirname(__file__), "..", "screenshots")
    os.makedirs(out_dir, exist_ok=True)

    with open(os.path.join(os.path.dirname(__file__), "..", "..", "full_run_log.txt")) as f:
        all_lines = [l.rstrip("\n") for l in f.readlines()]

    def section(start_marker, end_marker=None):
        started = False
        out = [f"$ python 00_run_pipeline.py"]
        for l in all_lines:
            if start_marker in l:
                started = True
            if started:
                out.append(l)
            if end_marker and end_marker in l and started and l != out[1]:
                break
        return out

    # Split into 4 logical screenshots matching the 4 pipeline stages
    idx_gen = next(i for i, l in enumerate(all_lines) if "01_generate_sample_data" in l)
    idx_bronze = next(i for i, l in enumerate(all_lines) if "02_bronze_layer" in l)
    idx_silver = next(i for i, l in enumerate(all_lines) if "03_silver_layer" in l)
    idx_gold = next(i for i, l in enumerate(all_lines) if "04_gold_layer" in l)

    render_terminal(
        ["$ python 00_run_pipeline.py"] + all_lines[idx_gen:idx_bronze],
        f"{out_dir}/01_raw_data_generation.png",
        "terminal — step 1: raw data generation"
    )
    render_terminal(
        all_lines[idx_bronze:idx_silver],
        f"{out_dir}/02_bronze_ingestion.png",
        "terminal — step 2: bronze layer (autoloader simulation)"
    )
    render_terminal(
        all_lines[idx_silver:idx_gold],
        f"{out_dir}/03_silver_scd2.png",
        "terminal — step 3: silver layer + SCD Type 2"
    )
    render_terminal(
        all_lines[idx_gold:],
        f"{out_dir}/04_gold_kpis.png",
        "terminal — step 4: gold layer KPI tables"
    )

    render_terminal(all_lines, f"{out_dir}/00_full_pipeline_run.png", "terminal — full pipeline run (all 4 stages)")
