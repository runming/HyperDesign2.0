import docx
from docx.table import Table
from docx.text.paragraph import Paragraph

d = docx.Document(r"D:\hyperdesign2\docs\申报书_HyperDesign2.0.docx")

# 找到含"项目/计算口径"的表并打印
for ti, tb in enumerate(d.tables):
    head = " | ".join(c.text.strip()[:12] for c in tb.rows[0].cells)
    print(f"表{ti}: {len(tb.rows)}行  {head}")

print("\n--- body 顺序（表附近） ---")
body = d.element.body
seq = []
for child in body.iterchildren():
    tag = child.tag.split('}')[-1]
    if tag == "p":
        p = Paragraph(child, d)
        t = p.text.strip()
        if t:
            seq.append(("P", t[:46]))
    elif tag == "tbl":
        seq.append(("TBL", ""))
for i, (k, t) in enumerate(seq):
    if k == "TBL" or "表 4" in t or "应用分析" in t:
        lo, hi = max(0, i - 2), min(len(seq), i + 3)
        print(f"  idx={i}: {seq[i][0]} {seq[i][1]}")
