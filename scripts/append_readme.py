from pathlib import Path

p = Path(r"D:\hyperdesign2\README.md")
s = p.read_text(encoding="utf-8")

addition = """

## 七、运行依赖与边界（重要）

- **2.0 平台层可独立运行**：CAD-IR 构建、准入规则、工作流、Studio、CAE、知识资产只依赖 Python 标准库 +
  `numpy`（CAE）/ `fastapi`+`uvicorn`（接口）/ 浏览器（前端），无需联网。
- **两条外部依赖（用于复现完整链路）**：
  1. 几何内核：需本机安装 FreeCAD（提供 `freecadcmd`），或通过环境变量 `HD_FREECAD_CMD` 指定路径；
  2. 网格物理门禁（M1/M2/M4 中的 housing_mesh 用例）：读取 1.0 版本产出的白模 DFM 指标（常量 `V1_MANIFEST`）；
     若只验证 2.0 自身能力，可跳过该用例或替换为任意合规数据。
- **生成式环节**（FLUX 概念图 / TRELLIS 三维重建）属于 1.0 能力层，2.0 通过数据契约对接，不重复实现。
- 全部门禁脚本的期望输出与报告结论记录在 `docs/poc/`。

## 八、快速验证

```powershell
$py = "E:\\hyperdesign\\venvs\\hd_brain\\Scripts\\python.exe"   # 任意装有 numpy/fastapi 的 Python 3.11+
& $py scripts\\m0_gate.py    # CAD-IR + 确定性 + 安全边界
& $py scripts\\m1_gate.py    # Harness + Agent 信封 + Skill Registry
& $py scripts\\m2_gate.py    # 工作流 + 事件流 + 审批门
& $py scripts\\m4_gate.py    # CAE 与理论解对标
& $py scripts\\m5_gate.py    # 知识资产（需先启动 API）
& $py backend\\app\\api\\server.py    # http://127.0.0.1:8010 -> Studio
```
"""

if "## 七、运行依赖与边界" not in s:
    s = s.rstrip() + addition
    p.write_text(s, encoding="utf-8")
    print("appended, total chars:", len(s))
else:
    print("already present")
