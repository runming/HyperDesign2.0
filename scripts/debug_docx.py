import docx

d = docx.Document(r"D:\hyperdesign2\docs\申报书_HyperDesign2.0.docx")
t1 = d.tables[1]
print("表1 行数/列数:", len(t1.rows), len(t1.columns))
seen = set()
for ri, row in enumerate(t1.rows):
    for ci, cell in enumerate(row.cells):
        tc = id(cell._tc)
        print(f"  r{ri}c{ci} tc={tc} dup={tc in seen} text={cell.text!r}")
        seen.add(tc)

print("\n全表 2:", [c.text for c in d.tables[2].rows[0].cells])
print("表0:", [r.cells[1].text for r in d.tables[0].rows])
