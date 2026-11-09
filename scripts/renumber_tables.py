from pathlib import Path

p = Path(r"D:\hyperdesign2\backend\app\materials\content.py")
s = p.read_text(encoding="utf-8")

pairs = [
    ('"title": "表 4  成本结构与测算框架（示例参数，待试点标定）"',
     '"title": "表 2  成本结构与测算框架（示例参数，待试点标定）"'),
    ('"title": "表 2  端到端验证数据（本机实测）"',
     '"title": "表 3  端到端验证数据（本机实测）"'),
    ('"title": "表 3  同一产品、同一台工作站的分环节耗时账（全部取自运行日志，可复算）"',
     '"title": "表 4  同一产品、同一台工作站的分环节耗时账（全部取自运行日志，可复算）"'),
]
for a, b in pairs:
    assert a in s, a[:40]
    s = s.replace(a, b)
p.write_text(s, encoding="utf-8")
print("表号已按文档顺序重排：成本=表2、验证=表3、耗时=表4")
