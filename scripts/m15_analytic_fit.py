# -*- coding: utf-8 -*-
"""M15 门禁：网格 → 解析特征恢复（平面/圆柱）+ 误差证书。

F1 纯长方体：恢复 6 个平面，三向间距误差 ≤0.05mm
F2 纯圆柱管：恢复 1 个圆柱，半径误差 ≤0.05mm、角度覆盖 ≥330°
F3 噪声鲁棒性：长方体加 σ=0.05mm 噪声后，间距误差仍 ≤0.15mm
F4 误差证书：逐特征 RMS/MAX 与容差判定
F5 真实机壳网格：识别平面数量（并如实报告圆柱识别情况）
F6 证书拦截：容差收紧到 0.0005mm 时判不通过
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.cadrefit import mesh_analytic as MA  # noqa: E402

REPORT = ROOT / "docs" / "poc" / "M15-ANALYTIC-FIT.md"
CHECKS = []
RUNNER = ROOT / "backend" / "app" / "cadir" / "runner_freecad.py"
IR = ROOT / "examples" / "sensor_housing.m0.ir.json"
FREECAD = os.environ.get("HD_FREECAD_CMD") or \
    r"C:\Users\omegahyper\AppData\Local\Programs\FreeCAD 1.1\bin\freecadcmd.exe"


def check(name, passed, detail=""):
    CHECKS.append({"name": name, "passed": passed, "detail": detail})
    print(("  PASS " if passed else "  FAIL ") + f"{name}: {detail}")


def spans(feats, axis_idx):
    """按法向符号还原有符号偏移，否则 ±50 的绝对值会互相抵消。"""
    vals = []
    for f in feats:
        if f["kind"] != "plane":
            continue
        n = np.array(f["normal"], dtype=float)
        if abs(float(n[axis_idx])) > 0.98:
            vals.append(float(f["offset"]) * (1.0 if n[axis_idx] > 0 else -1.0))
    vals.sort()
    return (vals[-1] - vals[0]) if len(vals) >= 2 else None


def main():
    tmp = Path(tempfile.mkdtemp(prefix="hd_m15_"))

    # F1 纯长方体
    stl = MA.write_binary_stl(MA.synth_box(100, 60, 30), tmp / "box.stl")
    r1 = MA.analyze(stl, tol_mm=0.05)
    sx, sy, sz = spans(r1["features"], 0), spans(r1["features"], 1), spans(r1["features"], 2)
    ok1 = (r1["planes"] == 6 and sx and sy and sz
           and abs(sx - 100) <= 0.05 and abs(sy - 60) <= 0.05 and abs(sz - 30) <= 0.05)
    check("F1 长方体平面恢复（6 面，间距误差 ≤0.05mm）", bool(ok1),
          f"平面 {r1['planes']} 个；X={sx:.3f}（真 100）Y={sy:.3f}（真 60）Z={sz:.3f}（真 30）")

    # F2 纯圆柱管
    stl2 = MA.write_binary_stl(MA.synth_tube(5.0, 30.0, seg=48), tmp / "tube.stl")
    r2 = MA.analyze(stl2, tol_mm=0.05)
    cyls = [f for f in r2["features"] if f["kind"] == "cylinder"]
    ok2 = bool(cyls) and abs(cyls[0]["radius"] - 5.0) <= 0.05 and cyls[0]["coverage_deg"] >= 330
    check("F2 圆柱管恢复（R5 误差 ≤0.05mm，覆盖 ≥330°）", ok2,
          (f"圆柱 {len(cyls)} 个：R={cyls[0]['radius']}mm（真 5.0）、覆盖 {cyls[0]['coverage_deg']}°、"
           f"高 {cyls[0]['height']}mm、RMS={cyls[0]['rms']}mm" if cyls else "未识别到圆柱"))

    # F3 噪声鲁棒性
    stl3 = MA.write_binary_stl(MA.synth_box(100, 60, 30, noise_mm=0.05, seed=7), tmp / "box_noise.stl")
    r3 = MA.analyze(stl3, tol_mm=0.2)
    s3 = [spans(r3["features"], i) for i in range(3)]
    ok3 = all(v is not None for v in s3) and abs(s3[0] - 100) <= 0.15 \
        and abs(s3[1] - 60) <= 0.15 and abs(s3[2] - 30) <= 0.15
    check("F3 噪声鲁棒性（σ=0.05mm，间距误差 ≤0.15mm）", bool(ok3),
          f"X={s3[0]:.3f} Y={s3[1]:.3f} Z={s3[2]:.3f}（真值 100/60/30）")

    # F4 误差证书
    cert = r1["certificate"]
    ok4 = cert["features"] == 6 and cert["passed"] and all("rms_mm" in r for r in cert["rows"])
    check("F4 误差证书逐特征可用", ok4,
          f"{cert['features']} 个特征全部出具证书，整体 {'通过' if cert['passed'] else '未通过'}，"
          f"最大 RMS={max(r['rms_mm'] for r in cert['rows']):.5f}mm")

    # F5 真实机壳
    ir_path = tmp / "ir.json"
    ir_path.write_text(IR.read_text(encoding="utf-8"), encoding="utf-8")
    env = dict(os.environ, HD2_CAD_IR=str(ir_path), HD2_CAD_OUT=str(tmp))
    subprocess.run([FREECAD, str(RUNNER)], capture_output=True, text=True, env=env,
                   timeout=300, errors="replace")
    produced = [p for p in tmp.glob("*.stl") if p.stat().st_size > 200_000]
    ok5, d5 = False, "未找到机壳 STL"
    if produced:
        r5 = MA.analyze(produced[0], tol_mm=0.2)
        ok5 = r5["planes"] >= 6
        d5 = (f"{produced[0].name}：{r5['triangle_count']} 三角面 → 平面 {r5['planes']} 个、"
              f"圆柱 {r5['cylinders']} 个" +
              (f"（R={[c['radius'] for c in r5['features'] if c['kind'] == 'cylinder'][:3]}）"
               if r5["cylinders"] else ""))
    check("F5 真实机壳网格特征识别（平面 ≥6）", ok5, d5)

    # F6 证书拦截（用含噪声的网格 + 极严容差，验证不会放行未验证几何）
    r3_strict = MA.certificate(r3["features"], tol_mm=0.0005)
    check("F6 容差收紧后证书判不通过", not r3_strict["passed"],
          f"噪声网格 + 0.0005mm 容差 → 通过={r3_strict['passed']}，"
          f"最大 RMS={max(r['rms_mm'] for r in r3_strict['rows']):.5f}mm")

    return write_report(all(c["passed"] for c in CHECKS), r1, r2, d5)


def write_report(ok_all, r1, r2, real_detail):
    lines = ["# M15 门禁报告 · 网格→解析特征恢复与误差证书", "",
             "- 结论：" + ("**通过**" if ok_all else "**未通过**"),
             "- 模块：`backend/app/cadrefit/mesh_analytic.py`（仅 numpy）",
             "- 顺序：**先识别圆柱基元（孔壁/圆角由多个平面小片组成，晚识别会被平面吃掉）**，"
             "再对剩余面片做平面聚类，最后出具逐特征误差证书", "",
             "| 门禁 | 结果 | 证据 |", "|---|---|---|"]
    for c in CHECKS:
        lines.append(f"| {c['name']} | {'✅' if c['passed'] else '❌'} | {c['detail']} |")
    lines += ["", "## 长方体恢复明细", "", "| 类型 | 三角面 | RMS (mm) | MAX (mm) | 方向/尺寸 |",
              "|---|---|---|---|---|"]
    for f in r1["features"]:
        lines.append(f"| 平面 | {f['triangles']} | {f['rms']:.5f} | {f['max']:.5f} | "
                     f"法向 {[round(float(x), 2) for x in f['normal']]}，偏移 {f['offset']:.3f}mm |")
    lines += ["", "## 圆柱管恢复明细", ""]
    for f in r2["features"]:
        if f["kind"] == "cylinder":
            lines.append(f"- R={f['radius']}mm，高 {f['height']}mm，夹角覆盖 {f['coverage_deg']}°，"
                         f"RMS={f['rms']}mm，三角面 {f['triangles']} 个")
    lines += ["", "## 真实机壳", f"- {real_detail}",
              "", "> 意义：把 AI 生成的毛糙网格还原为**可验证的解析特征**（平面/圆柱 + 尺寸 + 误差界）；",
              "> 只有证书通过的几何才允许进入参数化重建——这是从「玩具级生成」到「工业级可用」的关键一步。"]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n报告写入 {REPORT}")
    print("M15_GATE:", "PASS" if ok_all else "FAIL")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
