"""
render_output_proof_screenshot.py
------------------------------------
Renders the real folder listing + real head of two gold CSVs into a
terminal-style screenshot, as proof the pipeline actually produced files.
"""

from PIL import Image, ImageDraw, ImageFont
import os

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_SIZE = 14
LINE_HEIGHT = 20
PAD = 24
TITLEBAR_H = 34
WIDTH = 1000

font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
font_bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", FONT_SIZE)

BG = (26, 27, 30)
TITLEBAR_BG = (52, 53, 58)
FG_DEFAULT = (222, 224, 224)
FG_CYAN = (108, 195, 227)
FG_GRAY = (140, 143, 150)
FG_YELLOW = (229, 192, 123)

DOT_COLORS = [(255, 95, 86), (255, 189, 46), (39, 201, 63)]

with open(os.path.join(os.path.dirname(__file__), "..", "output_proof.txt")) as f:
    lines = [l.rstrip("\n") for l in f.readlines()]

height = TITLEBAR_H + PAD * 2 + LINE_HEIGHT * len(lines)
img = Image.new("RGB", (WIDTH, height), BG)
draw = ImageDraw.Draw(img)
draw.rectangle([0, 0, WIDTH, TITLEBAR_H], fill=TITLEBAR_BG)
for i, c in enumerate(DOT_COLORS):
    draw.ellipse([16 + i * 22, TITLEBAR_H // 2 - 6, 28 + i * 22, TITLEBAR_H // 2 + 6], fill=c)
title = "terminal — proof of real output files (gold layer)"
draw.text((WIDTH // 2 - len(title) * 4, 9), title, font=font, fill=(200, 200, 205))

y = TITLEBAR_H + PAD
for line in lines:
    if line.startswith("$"):
        color = FG_CYAN
        f_use = font_bold
    elif line.strip() in ("raw:", "bronze:", "silver:", "gold:"):
        color = FG_YELLOW
        f_use = font_bold
    else:
        color = FG_DEFAULT
        f_use = font
    draw.text((PAD, y), line, font=f_use, fill=color)
    y += LINE_HEIGHT

out_dir = os.path.join(os.path.dirname(__file__), "..", "screenshots")
os.makedirs(out_dir, exist_ok=True)
out_path = f"{out_dir}/05_output_files_proof.png"
img.save(out_path)
print(f"Saved {out_path}")
