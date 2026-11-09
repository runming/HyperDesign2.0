# -*- coding: utf-8 -*-
"""作品介绍 2.0：HTML -> PDF（A4，带背景，嵌入中文字体）+ 溢出与内容校验。"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

DOCS = Path(r"D:\hyperdesign2\docs")
SRC = DOCS / "作品介绍_HyperDesign2.0.html"
PDF = DOCS / "作品介绍_HyperDesign2.0.pdf"


def main():
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, channel="chrome",
                               args=["--no-sandbox", "--font-render-hinting=none"])
        # 1) 溢出检查（A4 内容宽 210-28=182mm ≈ 688px）
        page = b.new_page(viewport={"width": 688, "height": 1000})
        page.goto(SRC.as_uri(), wait_until="load", timeout=60_000)
        page.wait_for_timeout(500)
        info = page.evaluate("""() => {
            const w = document.documentElement.clientWidth;
            const over = [];
            document.querySelectorAll('body *').forEach(el => {
                const r = el.getBoundingClientRect();
                if (r.width > 0 && r.right > w + 1.5) over.push(el.tagName + '.' + (el.className||''));
            });
            return {w, scroll: document.documentElement.scrollWidth, over: over.slice(0, 5), n: over.length};
        }""")
        print(f"A4 内容宽={info['w']} scrollWidth={info['scroll']} 溢出元素={info['n']} {info['over']}")
        page.close()

        # 2) 出 PDF
        page = b.new_page(viewport={"width": 1240, "height": 1754}, device_scale_factor=2)
        page.goto(SRC.as_uri(), wait_until="load", timeout=60_000)
        page.wait_for_timeout(800)
        page.pdf(path=str(PDF), format="A4", print_background=True,
                 margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
                 display_header_footer=False, prefer_css_page_size=True)
        b.close()

    raw = PDF.read_bytes()
    pages = raw.count(b"/Type /Page") - raw.count(b"/Type /Pages")
    print(f"PDF_OK {PDF}  {len(raw)/1024:.1f} KB  {pages} 页  溢出={info['n']}")
    return 0 if info["n"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
