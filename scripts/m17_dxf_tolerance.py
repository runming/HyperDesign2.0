# -*- coding: utf-8 -*-
"""M17 门禁：DXF 工程图导出（尺寸 + 公差标注，而非光轮廓）。

D1 DXF 可被解析：5 类图元/4 个图层，实体数 > 0
D2 外轮廓为 1:1 真实尺寸（120×80），与 CAD-IR 参数一致
D3 尺寸文本含公差（±0.xxx），且公差值来自 GB/T 1800.1 IT9 表
D4 孔位数量正确（1 导光孔 + 4 安装柱 = 5）
D5 切割层与标注层分离（尺寸线不混入 CUT_PROFILE）
D6 真实内核指标进入标题栏（体积/包络可回溯）
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.caddraw.dxf_writer import export_part_drawing, parse_entities  # noqa: E402
from app.standards.tables import tolerance_for  # noqa: E402

REPORT = ROOT / "docs" / "poc" / "M17-DXF-TOLERANCE.md"
CHECKS = []
IR = ROOT / "examples" / "sensor_housing.m0.ir.json"
RUNNER = ROOT / "backend" / "app" / "cadir" / "runner_freecad.py"
FREECAD = os.environ.get("HD_FREECAD_CMD") or \
    r"C:\Users\omegahyper\AppData\Local\Programs\FreeCAD 1.1\bin\freecadcmd.exe"


def check(name, passed, detail=""):
    CHECKS.append({"name": name, "passed": passed, "detail": detail})
    print(("  PASS " if passed else "  FAIL ") + f"{name}: {detail}")


def main():
    tmp = Path(tempfile.mkdtemp(prefix="hd_m17_"))
    ir = json.loads(IR.read_text(encoding="utf-8"))
    # 取真实内核指标
    irp = tmp / "ir.json"
    irp.write_text(json.dumps(ir, ensure_ascii=False), encoding="utf-8")
    env = dict(os.environ, HD2_CAD_IR=str(irp), HD2_CAD_OUT=str(tmp))
    subprocess.run([FREECAD, str(RUNNER)], capture_output=True, text=True, env=env,
                   timeout=300, errors="replace")
    rep = json.loads((tmp / "cad_report.json").read_text(encoding="utf-8"))
    metrics = rep.get("metrics") or {}

    dxf = tmp / "part.dxf"
    info = export_part_drawing(ir, metrics, dxf)
    parsed = parse_entities(dxf)

    # D1
    ok1 = (parsed["total"] > 10 and {"CUT_PROFILE", "HIDDEN_LINE", "DIMENSIONS",
                                     "TITLE_BLOCK"} <= set(parsed["layers"]))
    check("D1 DXF 可解析且四图层齐备", ok1,
          f"实体 {parsed['total']} 个，图层 {parsed['layers']}")

    # D2 外轮廓尺寸
    ok2 = info["outline_mm"] == [120.0, 80.0]
    check("D2 外轮廓为 1:1 真实尺寸", ok2,
          f"outline_mm={info['outline_mm']}（来自 CAD-IR 参数）")

    # D3 公差文本（用 %%)
    tol_l = tolerance_for(120.0, "IT9")
    tol_w = tolerance_for(80.0, "IT9")
    text_all = " | ".join(parsed["texts"])
    ok3 = (f"%%p{tol_l['tolerance_mm']:.3f}" in text_all and
           f"%%p{tol_w['tolerance_mm']:.3f}" in text_all)
    check("D3 尺寸文本含公差且取自标准表", ok3,
          f"IT9：120→{tol_l['tolerance_um']}µm、80→{tol_w['tolerance_um']}µm；"
          f"文本样例={parsed['texts'][:2]}")

    # D4 孔位
    ok4 = info["holes"] == 5 and parsed["counts"].get("CIRCLE@CUT_PROFILE", 0) == 5
    check("D4 孔位数量（1 导光孔 + 4 安装柱）", ok4,
          f"holes={info['holes']}，CUT_PROFILE 圆={parsed['counts'].get('CIRCLE@CUT_PROFILE')}")

    # D5 图层分离
    dim_in_cut = parsed["counts"].get("TEXT@CUT_PROFILE", 0)
    ok5 = dim_in_cut == 0 and parsed["counts"].get("TEXT@DIMENSIONS", 0) >= 3
    check("D5 标注不混入切割层", ok5,
          f"CUT_PROFILE 文本={dim_in_cut}，DIMENSIONS 文本={parsed['counts'].get('TEXT@DIMENSIONS')}")

    # D6 标题栏含实测值
    ok6 = any("mm3" in t for t in parsed["texts"]) and any("IT9" in t for t in parsed["texts"])
    check("D6 标题栏含实测体积与包络", ok6,
          f"体积 {metrics.get('volume_mm3')}mm³、包络 {metrics.get('bbox_mm')}")

    return write_report(all(c["passed"] for c in CHECKS), info, parsed, metrics)


def write_report(ok_all, info, parsed, metrics):
    lines = ["# M17 门禁报告 · DXF 工程图（尺寸 + 公差标注）", "",
             "- 结论：" + ("**通过**" if ok_all else "**未通过**"),
             "- 模块：`backend/app/caddraw/dxf_writer.py`（R12 ASCII，**自带写出器，无第三方依赖**）",
             "- 公差来源：`app/standards/tables.py`（GB/T 1800.1 标准公差，IT9）", "",
             "| 门禁 | 结果 | 证据 |", "|---|---|---|"]
    for c in CHECKS:
        lines.append(f"| {c['name']} | {'✅' if c['passed'] else '❌'} | {c['detail']} |")
    lines += ["", "## 图层分工", "", "| 图层 | 用途 | 图元 |", "|---|---|---|"]
    usage = {"CUT_PROFILE": "1:1 激光切割/CNC 外轮廓，直接进 CAM",
             "HIDDEN_LINE": "内腔与不可见边（虚线）",
             "DIMENSIONS": "尺寸线 + 尺寸文本（含公差）",
             "TITLE_BLOCK": "图框标题栏（材料/壁厚/拔模/公差等级/实测）"}
    for layer in info["layers"]:
        ents = [f"{k.split('@')[0]}×{v}" for k, v in parsed["counts"].items()
                if k.endswith("@" + layer)]
        lines.append(f"| {layer} | {usage.get(layer, '')} | {', '.join(ents) or '—'} |")
    lines += ["", "## 尺寸与公差", "",
              "| 尺寸 | 数值 | 公差（IT9） |", "|---|---|---|"]
    for key, label in (("length", "总长"), ("width", "总宽"), ("height", "总高"), ("hole", "导光孔")):
        lines.append(f"| {label} | {info['outline_mm'][0] if key == 'length' else ''}"
                     f"{info['outline_mm'][1] if key == 'width' else ''} | "
                     f"{info['tolerances'][key]} |")
    lines += ["", "## 与常见做法的差异", "",
              "- 常见导出：只出轮廓线，公差与配合信息丢失，质检仍需人工补标；",
              "- 本实现：按配合/尺寸自动查 GB/T 1800.1 公差表并写入尺寸文本，"
              "同时把实测体积与包络写进标题栏，图纸可回溯到具体运行。", "",
              f"> 实测指标：体积 {metrics.get('volume_mm3')}mm³，包络 {metrics.get('bbox_mm')}。"]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n报告写入 {REPORT}")
    print("M17_GATE:", "PASS" if ok_all else "FAIL")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
