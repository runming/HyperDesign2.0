# -*- coding: utf-8 -*-
"""检查申报模板的段落/样式/表格结构，为"按模板填写"做准备。"""
import docx

SRC = r"D:\hyperdesign\_ref\submission_template.docx"
d = docx.Document(SRC)

print("=== 段落（索引 / 样式 / 文本 / 首run字体） ===")
for i, p in enumerate(d.paragraphs):
    t = p.text.strip()
    f = ""
    if p.runs:
        r = p.runs[0]
        f = f"{r.font.name}|{r.font.size.pt if r.font.size else '-'}|{r.font.bold}"
    print(f"[{i:3d}] {p.style.name:12s} |{f:22s}| {t[:70]}")

print("\n=== 表格 ===")
for ti, tb in enumerate(d.tables):
    print(f"--- 表{ti}: {len(tb.rows)}行 x {len(tb.columns)}列 | style={tb.style.name if tb.style else None}")
    for ri, row in enumerate(tb.rows):
        cells = [c.text.strip().replace("\n", "⏎") for c in row.cells]
        print(f"   r{ri}: {cells}")

print("\n=== 节与页面 ===")
for si, s in enumerate(d.sections):
    print(f" 节{si}: page={s.page_width.mm:.1f}x{s.page_height.mm:.1f}mm margins L{s.left_margin.mm:.0f} R{s.right_margin.mm:.0f}")

print("\n=== 样式可用性 ===")
names = {st.name for st in d.styles}
for want in ["Normal", "Heading 1", "Heading 2", "Body Text", "Title"]:
    print(f"  {want}: {'有' if want in names else '无'}")
