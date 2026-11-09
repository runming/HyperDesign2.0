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

ir = json.loads((ROOT / "examples" / "sensor_housing.m0.ir.json").read_text(encoding="utf-8"))
ir["parameters"].update({"LENGTH_X": 130.0, "WIDTH_Y": 90.0, "HEIGHT_Z": 50.0,
                         "WALL": 2.5, "CORNER_R": 5.0, "POST_H": 46.3,
                         "POST_INSET": 10.0, "LED_DEPTH": 4.3, "LED_Z": 45.5})
tmp = Path(tempfile.mkdtemp(prefix="hd_p_"))
(tmp / "ir.json").write_text(json.dumps(ir, ensure_ascii=False), encoding="utf-8")
env = dict(os.environ, HD2_CAD_IR=str(tmp / "ir.json"), HD2_CAD_OUT=str(tmp))
subprocess.run([FREECAD, str(RUNNER)], capture_output=True, text=True, env=env, timeout=300)
rep = json.loads((tmp / "cad_report.json").read_text(encoding="utf-8"))
m = rep.get("metrics") or {}
print("ok:", rep.get("ok"), "errors:", rep.get("errors"))
print("metrics:", json.dumps({k: m.get(k) for k in ("volume_mm3", "bbox_mm", "z_min", "solids")}, ensure_ascii=False))
print("dfm:", json.dumps(m.get("dfm"), ensure_ascii=False))
pack = RulePack.load(PACK)
v = evaluate(pack, {"cad": m, "target": {"bbox_mm": {"x": 130.0, "y": 90.0, "z": 50.0},
                                         "tolerance_mm": 1.5},
                    "process": PROCESS, "params": {}})
print("verdict:", v.verdict)
for r in v.results:
    if not r.passed:
        print("  FAIL", r.rule_id, "actual=", r.actual, "required=", r.required)
