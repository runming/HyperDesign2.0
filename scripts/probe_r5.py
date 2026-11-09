import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(r"D:\hyperdesign2")
sys.path.insert(0, str(ROOT / "backend"))
from app.harness.engine import RulePack, evaluate

RUNNER = ROOT / "backend" / "app" / "cadir" / "runner_freecad.py"
FREECAD = r"C:\Users\omegahyper\AppData\Local\Programs\FreeCAD 1.1\bin\freecadcmd.exe"
PACK = ROOT / "backend" / "app" / "harness" / "rules" / "housing_cad.v1.json"
PROCESS = {"min_wall_mm": 2.4, "rib_max_mm": 1.44, "min_draft_deg": 1.8,
           "max_bulk_wall_mm": 4.5, "pc_abs_yield_mpa": 50.0, "max_allowable_stress_mpa": 25.0}
base = json.loads((ROOT / "examples" / "sensor_housing.m0.ir.json").read_text(encoding="utf-8"))


def run(params, tag):
    ir = json.loads(json.dumps(base))
    ir["parameters"].update(params)
    tmp = Path(tempfile.mkdtemp(prefix=f"hd_v_{tag}_"))
    (tmp / "ir.json").write_text(json.dumps(ir, ensure_ascii=False), encoding="utf-8")
    env = dict(os.environ, HD2_CAD_IR=str(tmp / "ir.json"), HD2_CAD_OUT=str(tmp))
    subprocess.run([FREECAD, str(RUNNER)], capture_output=True, text=True, env=env, timeout=300,
                   errors="replace")
    rep = json.loads((tmp / "cad_report.json").read_text(encoding="utf-8"))
    m = rep.get("metrics") or {}
    pack = RulePack.load(PACK)
    v = evaluate(pack, {"cad": m, "target": {"bbox_mm": {"x": 120.0, "y": 80.0, "z": 45.0},
                                             "tolerance_mm": 1.5},
                        "process": PROCESS, "params": {}})
    fails = []
    for r in v.results:
        if getattr(r, "status", None) not in (None, "passed") or getattr(r, "passed", None) is False:
            fails.append((r.rule_id, getattr(r, "actual", None)))
    print(f"{tag:18s} ok={rep.get('ok')} solids={m.get('solids')} valid={m.get('is_valid')} "
          f"draft={m.get('dfm', {}).get('min_draft_deg')} vert={m.get('dfm', {}).get('vertical_face_count')} "
          f"verdict={v.verdict} fails={fails[:3]}")


run({"CORNER_R": 5.0}, "R5")
run({"CORNER_R": 4.8}, "R4.8")
run({"WALL": 2.6}, "WALL2.6")
run({"CORNER_R": 5.0, "WALL": 2.6}, "R5+W2.6")
