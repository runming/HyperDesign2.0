from pathlib import Path

p = Path(r"D:\hyperdesign2\README.md")
s = p.read_text(encoding="utf-8")

old_row = "| M6 | 参赛材料：申报书（按官方模板填写） | ✅ 已完成并通过校验（7,038 中文字 / 18 页 / 5 表） |"
new_row = ("| M6 | 参赛材料：申报书（按官方模板填写） | ✅ 已通过校验（20 页 / 6 表 / 3 配图 / 7,386 中文字） |\n"
           "| M7 | 设计空间可行性判定 + 自动修复 + 跨产品族复用 | ✅ PASS（10 项） |")
s = s.replace(old_row, new_row)

anchor = "### 参赛材料（M6 产出）"
add = """### 设计空间可行性与跨产品族复用（M7 新增）

- 模块：`backend/app/cadir/feasibility.py`（纯解析，不依赖几何内核）
- 约束：顶部内角半径、顶面平台、壁厚上下限、拔模下限、高厚比；每条带公式与依据
- 实测：外角 R=3.0 → 内角半径 **−0.82mm** 判不可行（真实内核同样报错 −0.740mm）→ 最小改动建议 **4.1mm** → 重建通过
- 复用：同一解释器构建 **CNC 支架**（80×40×44mm，18,789mm³），仅替换 IR 与规则包即通过；
  用注塑规则包判定同一支架则因拔模被判失败（证明规则与工艺绑定，非硬编码）

"""
if "### 设计空间可行性与跨产品族复用" not in s:
    s = s.replace(anchor, add + anchor)

p.write_text(s, encoding="utf-8")
print("README updated, chars:", len(s))
