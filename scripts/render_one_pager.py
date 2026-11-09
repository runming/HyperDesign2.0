from pathlib import Path

from playwright.sync_api import sync_playwright

src = Path(r"D:\hyperdesign2\docs\一页纸速览_HyperDesign2.0.html")
pdf = Path(r"D:\hyperdesign2\docs\一页纸速览_HyperDesign2.0.pdf")

JS = """() => {
  const w = document.documentElement.clientWidth;
  let n = 0;
  document.querySelectorAll('body *').forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.right > w + 1.5) n++;
  });
  return n;
}"""

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True, channel="chrome", args=["--no-sandbox"])
    p = b.new_page(viewport={"width": 700, "height": 990})
    p.goto(src.as_uri(), wait_until="load")
    p.wait_for_timeout(400)
    info = p.evaluate(JS)
    p.pdf(path=str(pdf), format="A4", print_background=True,
          margin={"top": "0", "bottom": "0", "left": "0", "right": "0"}, prefer_css_page_size=True)
    b.close()

raw = pdf.read_bytes()
pages = raw.count(b"/Type /Page") - raw.count(b"/Type /Pages")
print(f"一页纸：{pages} 页 / 溢出 {info} / {len(raw)/1024:.1f} KB")
