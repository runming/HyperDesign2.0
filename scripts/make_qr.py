# -*- coding: utf-8 -*-
"""生成演示视频与仓库的二维码（PNG），供申报书附录 2 使用。

依赖 segno（已安装到 D:\\hyperdesign2\\.qrlib，仅构建期使用，不进运行时）。
"""
import sys
from pathlib import Path

sys.path.insert(0, r"D:\hyperdesign2\.qrlib")
import segno  # noqa: E402

OUT = Path(r"D:\hyperdesign2\docs\poc")
OUT.mkdir(parents=True, exist_ok=True)

TARGETS = {
    "qr_video.png": ("https://github.com/runming/HyperDesign2.0/blob/main/docs/demo/"
                     "HyperDesign2.0_Demo_1080p.mp4", "演示视频"),
    "qr_repo.png": ("https://github.com/runming/HyperDesign2.0", "代码仓库"),
}

for name, (url, label) in TARGETS.items():
    path = OUT / name
    segno.make(url, error="h").save(str(path), scale=10, border=3, dark="#0d1b2a")
    print(f"{label}: {path}  ({path.stat().st_size/1024:.1f} KB)  -> {url}")

# 一张带中文标签的合并图（便于直接贴进文档）
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

W, H = 1200, 640
canvas = Image.new("RGB", (W, H), "white")
draw = ImageDraw.Draw(canvas)
font_path = r"C:\Windows\Fonts\msyh.ttc"
title = ImageFont.truetype(font_path, 34)
small = ImageFont.truetype(font_path, 20)

draw.text((40, 28), "HyperDesign 2.0 · 扫码查看", font=title, fill="#0d1b2a")
for i, (name, (url, label)) in enumerate(TARGETS.items()):
    qr = Image.open(OUT / name).convert("RGB").resize((420, 420))
    x = 90 + i * 560
    canvas.paste(qr, (x, 100))
    draw.text((x, 540), label, font=title, fill="#0a5f8f")
    short = url.replace("https://", "")
    draw.text((x, 590), short[:44] + ("…" if len(short) > 44 else ""), font=small, fill="#61727f")

combo = OUT / "qr_combo.png"
canvas.save(combo)
print("合并图:", combo, f"({combo.stat().st_size/1024:.1f} KB)")
