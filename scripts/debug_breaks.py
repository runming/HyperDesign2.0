import docx
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

d = docx.Document(r"D:\hyperdesign2\docs\申报书_HyperDesign2.0.docx")
body = d.element.body
kids = list(body.iterchildren())
print("body children:", len(kids))
for i, k in enumerate(kids):
    if k.tag.split("}")[-1] != "p":
        continue
    p = Paragraph(k, d)
    brs = [b.get(qn("w:type")) for b in k.findall(".//" + qn("w:br"))]
    if "page" in brs:
        nxt = kids[i + 1] if i + 1 < len(kids) else None
        nxt_desc = "None"
        if nxt is not None:
            if nxt.tag.split("}")[-1] == "p":
                np = Paragraph(nxt, d)
                nxt_desc = f"p style={np.style.name!r} text={np.text[:20]!r}"
            else:
                nxt_desc = nxt.tag.split("}")[-1]
        print(f"  [{i}] 空段含分页符  style={p.style.name!r} text={p.text!r}")
        print(f"        下一兄弟: {nxt_desc}")
        print(f"        startswith('Heading 1') = {nxt_desc.startswith('p style=') and Paragraph(nxt, d).style.name.startswith('Heading 1') if nxt is not None and nxt.tag.split('}')[-1]=='p' else 'n/a'}")
