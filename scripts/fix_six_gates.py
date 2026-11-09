from pathlib import Path

edits = {
    r"D:\hyperdesign2\docs\poc\M6-MATERIALS.md": [
        ("六道门禁脚本可复跑", "七道门禁脚本可复跑"),
        ("| 0:54–1:02 | 六道门禁成绩单 |", "| 0:54–1:03 | 七道门禁成绩单 |"),
    ],
    r"D:\hyperdesign2\docs\一页纸速览_HyperDesign2.0.html": [
        ("含六道门禁脚本与报告", "含七道门禁脚本与报告"),
    ],
    r"D:\hyperdesign2\docs\作品介绍_HyperDesign2.0.html": [
        ("知识资产与六道工程门禁", "知识资产与七道工程门禁"),
    ],
}

for path, pairs in edits.items():
    p = Path(path)
    s = p.read_text(encoding="utf-8")
    n = 0
    for old, new in pairs:
        if old in s:
            s = s.replace(old, new)
            n += 1
    p.write_text(s, encoding="utf-8")
    print(f"{p.name}: {n} 处已修正")
