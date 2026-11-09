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
FREE = r"C:\Users\omegahyper\AppData\Local\Programs\FreeCAD 1.1\bin\freecadcmd.exe"
PROC = {"min_wall_mm": 2.4, "rib_max_mm": 1.44, "min_draft_deg": 1.8,
        "max_bulk_wall_mm": 4.5, "pc_abs_yield_mpa": 50.0, "max_allowable_stress_mpa": 25.0}
BASE = json.loads((ROOT / "examples" / "sensor_housing.m0.ir.json").read_text(encoding="utf-8"))


def reconcile(L, W, H, wall=2.4):
    import math
    if H / wall > 20.0:
        wall = math.ceil(H / 20.0 * 10) / 10.0
    return {"LENGTH_X": L, "WIDTH_Y": W, "HEIGHT_Z": H, "WALL": wall,
            "POST_H": round(H - wall, 1),
            "LED_DEPTH": round(wall + 2.0, 1),
            "LED_Z": round(H - 3.4, 1),
            "POST_INSET": max(6.0, min(10.0, min(L, W) / 4.0))}


def run(dims, tag):
    L, W, H = dims
    p = reconcile(L, W, H)
    ir = json.loads(json.dumps(BASE))
    ir["parameters"].update(p)
    tmp = Path(tempfile.mkdtemp(prefix=f"hd_d_{tag}_"))
    (tmp / "ir.json").write_text(json.dumps(ir, ensure_ascii=False), encoding="utf-8")
    env = dict(os.environ, HD2_CAD_IR=str(tmp / "ir.json"), HD2_CAD_OUT=str(tmp))
    subprocess.run([FREE, str(RUNNER)], capture_output=True, text=True, env=env,
                   timeout=300, errors="replace")
    rep = json.loads((tmp / "cad_report.json").read_text(encoding="utf-8"))
    m = rep.get("metrics") or {}
    v = evaluate(RulePack.load(ROOT / "backend" / "app" / "harness" / "rules" / "housing_cad.v1.json"),
                 {"cad": m, "target": {"bbox_mm": {"x": L, "y": W, "z": H}, "tolerance_mm": 1.5},
                  "process": PROC, "params": {}})
    print(f"{tag:6s} {dims} params={{'WALL': {p['WALL']}, 'POST_H': {p['POST_H']}, "
          f"'LED_Z': {p['LED_Z']}}} ok={rep.get('ok')} solids={m.get('solids')} "
          f"vol={m.get('volume_mm3')} verdict={v.verdict} {v.blocking_failures[:2]}")


run((120, 80, 45), "base")
run((130, 90, 50), "big")
