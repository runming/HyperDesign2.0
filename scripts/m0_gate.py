# -*- coding: utf-8 -*-
"""
M0 门禁：CAD-IR 解释器 + 确定性 + 安全边界 自检

门禁项（对应 docs/00-competitive-analysis 第六节 M0）：
  G1 同一 IR 连续两次重建 -> 包围盒/体积偏差 < 0.1%（确定性）
  G2 B-Rep 合法（isValid）+ 单一实体
  G3 关键尺寸：底面包络 = 120.0 × 80.0 × 45.0 mm（±0.05），底面坐平 Z_min = 0
  G4 CAD 几何级拔模：min_draft_deg ≥ 1.8°（±0.05），垂直面数 = 0
  G5 安全边界：含 execute_script 的 IR 必须被拒绝（CAD_FEATURE_UNSUPPORTED）
  G6 无依赖算子缺失：所有 feature.type 均在能力清单内

用法：python scripts/m0_gate.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "backend" / "app" / "cadir" / "runner_freecad.py"
IR_PATH = ROOT / "examples" / "sensor_housing.m0.ir.json"
REPORT = ROOT / "docs" / "poc" / "M0-GATE-REPORT.md"

FREECAD = os.environ.get("HD_FREECAD_CMD") or \
    r"C:\Users\omegahyper\AppData\Local\Programs\FreeCAD 1.1\bin\freecadcmd.exe"


def run_ir(ir_path: Path, out_dir: Path):
    t0 = time.time()
    env = dict(os.environ, HD2_CAD_IR=str(ir_path), HD2_CAD_OUT=str(out_dir))
    proc = subprocess.run([FREECAD, str(RUNNER)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    elapsed = time.time() - t0
    report_path = out_dir / "cad_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else None
    return proc, report, elapsed


def main():
    checks = []
    ok_all = True

    def check(gid, name, passed, detail):
        nonlocal ok_all
        ok_all = ok_all and passed
        checks.append({"id": gid, "name": name, "passed": passed, "detail": detail})
        print(("  PASS " if passed else "  FAIL ") + f"{gid} {name}: {detail}")

    print("[M0] 运行 CAD-IR -> FreeCAD/OCCT")
    tmp = Path(tempfile.mkdtemp(prefix="hd2_m0_"))
    ir = json.loads(IR_PATH.read_text(encoding="utf-8"))

    proc1, rep1, t1 = run_ir(IR_PATH, tmp / "run1")
    print(f"  第一次: 耗时 {t1:.1f}s, 报告 ok={None if not rep1 else rep1.get('ok')}")
    if not rep1 or not rep1.get("ok"):
        print((proc1.stdout or "")[-1500:], (proc1.stderr or "")[-1500:])
        check("G0", "解释器可执行", False,
              f"无有效报告；错误={(rep1 or {}).get('errors')}")
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text("# M0 门禁报告\n\n未通过（解释器无法执行）。\n\n```\n"
                          + ((proc1.stdout or "")[-2000:]) + "\n```\n", encoding="utf-8")
        return 1
    check("G0", "解释器可执行", True, f"引擎 {rep1.get('engine')} {rep1.get('engine_version')}")

    m1 = rep1.get("metrics", {})
    proc2, rep2, t2 = run_ir(IR_PATH, tmp / "run2")
    m2 = (rep2 or {}).get("metrics", {})

    # G1 确定性
    dv = abs(m1["volume_mm3"] - m2["volume_mm3"]) / max(m1["volume_mm3"], 1e-9) * 100
    dbb = max(abs(m1["bbox_mm"][k] - m2["bbox_mm"][k]) for k in "xyz")
    check("G1", "两次重建确定性", dv < 0.1 and dbb < 0.05,
          f"体积偏差 {dv:.4f}% / 包围盒最大偏差 {dbb:.4f} mm")

    # G2 B-Rep
    check("G2", "B-Rep 合法且单实体", bool(m1["is_valid"]) and m1["solids"] == 1,
          f"isValid={m1['is_valid']}, solids={m1['solids']}, shells={m1['shells']}, faces={m1['faces']}")

    # G3 关键尺寸
    bb = m1["bbox_mm"]
    dim_ok = all(abs(bb[k] - t) < 0.05 for k, t in (("x", 120.0), ("y", 80.0), ("z", 45.0)))
    z_ok = abs(m1["z_min"]) < 1e-6
    check("G3", "包络与基准面", dim_ok and z_ok,
          f"{bb['x']} × {bb['y']} × {bb['z']} mm, Z_min={m1['z_min']}, 体积 {m1['volume_mm3']:,} mm³")

    # G4 拔模
    dfm = m1.get("dfm", {})
    draft_ok = dfm.get("measured") and dfm["min_draft_deg"] >= 1.75 and dfm["vertical_face_count"] == 0
    check("G4", "CAD 几何级拔模角", draft_ok,
          f"min={dfm.get('min_draft_deg')}°, median={dfm.get('median_draft_deg')}°, "
          f"垂直面={dfm.get('vertical_face_count')}, 侧壁面数={dfm.get('planar_side_faces')}")

    # G5 安全边界：任意代码执行必须被拒
    bad = dict(ir)
    bad["features"] = ir["features"] + [{"id": "evil", "type": "execute_script",
                                         "params": {"code": "import os; os.remove('x')"},
                                         "depends_on": ["f6_led_window"]}]
    bad_path = tmp / "evil.ir.json"
    bad_path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
    pbad, rbad, _ = run_ir(bad_path, tmp / "run_bad")
    errs = " ".join((rbad or {}).get("errors", []))
    rejected = bool(rbad) and rbad.get("ok") is not True and "CAD_FEATURE_UNSUPPORTED" in errs
    check("G5", "拒绝任意代码执行", rejected,
          f"ok={None if not rbad else rbad.get('ok')}, 错误包含 CAD_FEATURE_UNSUPPORTED={'CAD_FEATURE_UNSUPPORTED' in errs}")

    # G6 能力清单覆盖
    caps = set((rep1 or {}).get("capabilities", []))
    used = {f["type"] for f in ir["features"]}
    check("G6", "算子均被引擎能力声明支持", used.issubset(caps), f"使用 {sorted(used)}；缺失 {sorted(used - caps)}")

    # 产物
    step = tmp / "run1" / "model.step"
    stl = tmp / "run1" / "model.stl"
    size_ok = step.exists() and step.stat().st_size > 1024
    check("G7", "STEP/STL 产物落盘", size_ok,
          f"STEP {step.stat().st_size if step.exists() else 0} B / STL {stl.stat().st_size if stl.exists() else 0} B")

    # 报告
    lines = ["# M0 门禁报告 · CAD-IR 解释器", "",
             f"- 时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
             f"- 引擎：{rep1.get('engine')} {rep1.get('engine_version')}（FreeCAD 自带 OpenCascade）",
             f"- IR：`examples/sensor_housing.m0.ir.json`（{len(ir['features'])} 个特征，全部走白名单算子）",
             f"- 结论：{'**通过**' if ok_all else '**未通过**'}", "",
             "| 门禁 | 检查项 | 结果 | 证据 |", "|---|---|---|---|"]
    for c in checks:
        lines.append(f"| {c['id']} | {c['name']} | {'✅' if c['passed'] else '❌'} | {c['detail']} |")
    lines += ["", "## 特征级耗时", "", "| 特征 | 类型 | 耗时(ms) | 状态 |", "|---|---|---|---|"]
    for f in rep1.get("features", []):
        lines.append(f"| {f['id']} | {f['type']} | {f.get('elapsed_ms', 0)} | {f['status']} |")
    lines += ["", "## 语义引用映射（业务层只用这些名字，不碰 Edge1/Face3）", "", "```json",
              json.dumps(rep1.get("semantic_refs", {}), ensure_ascii=False, indent=2), "```", "",
              "## 几何元数据", "", "```json",
              json.dumps({k: m1.get(k) for k in ("is_valid", "volume_mm3", "surface_area_mm2",
                                                 "bbox_mm", "z_min", "faces", "edges", "dfm")},
                         ensure_ascii=False, indent=2), "```"]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n报告已写入 {REPORT}")
    print("M0_GATE:", "PASS" if ok_all else "FAIL")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
