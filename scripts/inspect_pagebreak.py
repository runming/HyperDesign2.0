import docx
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

d = docx.Document(r"D:\hyperdesign2\docs\申报书_HyperDesign2.0.docx")

# 1) Heading 1 样式是否段前分页
st = d.styles["Heading 1"]
pf = st.paragraph_format
print("Heading1 page_break_before:", pf.page_break_before)
print("Heading1 space_before:", pf.space_before, "line_spacing:", pf.line_spacing)

# 2) 找 应用分析 之前的兄弟节点，看是否有空段落或显式分页
body = d.element.body
kids = list(body.iterchildren())
for i, k in enumerate(kids):
    if k.tag.split("}")[-1] == "p":
        p = Paragraph(k, d)
        if p.text.strip() == "应用分析":
            print(f"\n应用分析 在 body 索引 {i}")
            for j in range(max(0, i - 3), min(len(kids), i + 2)):
                c = kids[j]
                tag = c.tag.split("}")[-1]
                if tag == "p":
                    pp = Paragraph(c, d)
                    brs = c.findall(".//" + qn("w:br"))
                    br_types = [b.get(qn("w:type")) for b in brs]
                    print(f"  [{j}] p style={pp.style.name!r} text={pp.text[:30]!r} breaks={br_types}")
                else:
                    print(f"  [{j}] {tag}")
            break

# 3) 统计 body 中所有显式分页
n_br = 0
for k in kids:
    if k.tag.split("}")[-1] == "p":
        for b in k.findall(".//" + qn("w:br")):
            if b.get(qn("w:type")) == "page":
                n_br += 1
print("\n显式分页符数量:", n_br)

# 4) 空段落总数与位置
empties = [(i, Paragraph(k, d).style.name) for i, k in enumerate(kids)
           if k.tag.split("}")[-1] == "p" and not Paragraph(k, d).text.strip()]
print("空段落数:", len(empties), "前 12 个:", empties[:12])
