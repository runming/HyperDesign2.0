import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(r"D:\hyperdesign2")
sys.path.insert(0, str(ROOT / "backend"))
RUNNER = ROOT / "backend" / "app" / "cadir" / "runner_freecad.py"
FREECAD = r"C:\Users\omegahyper\AppData\Local\Programs\FreeCAD 1.1\bin\freecadcmd.exe"

base = json.loads((ROOT / "examples" / "sensor_housing.m0.ir.json").read_text(encoding="utf-8"))


def build(params, tag):
    ir = json.loads(json.dumps(base))
    ir["parameters"].update(params)
    tmp = Path(tempfile.mkdtemp(prefix=f"hd_h_{tag}_"))
    (tmp / "ir.json").write_text(json.dumps(ir, ensure_ascii=False), encoding="utf-8")
    env = dict(os.environ, HD2_CAD_IR=str(tmp / "ir.json"), HD2_CAD_OUT=str(tmp))
    subprocess.run([FREECAD, str(RUNNER)], capture_output=True, text=True, env=env, timeout=300)
    rep = json.loads((tmp / "cad_report.json").read_text(encoding="utf-8"))
    m = rep.get("metrics") or {}
    return rep.get("ok"), m.get("solids"), m.get("volume_mm3"), rep.get("errors")


cases = {
    "原设计 120×80×45": {"LENGTH_X": 120, "WIDTH_Y": 80, "HEIGHT_Z": 45},
    "130×90×50 POST_H=46.3": {"LENGTH_X": 130, "WIDTH_Y": 90, "HEIGHT_Z": 50,
                              "WALL": 2.5, "CORNER_R": 5.0, "POST_H": 46.3,
                              "LED_DEPTH": 4.3, "LED_Z": 45.5},
    "130×90×50 POST_H=44": {"LENGTH_X": 130, "WIDTH_Y": 90, "HEIGHT_Z": 50,
                            "WALL": 2.5, "CORNER_R": 5.0, "POST_H": 44.0,
                            "LED_DEPTH": 4.3, "LED_Z": 45.5},
    "130×90×50 POST_H=40": {"LENGTH_X": 130, "WIDTH_Y": 90, "HEIGHT_Z": 50,
                            "WALL": 2.5, "CORNER_R": 5.0, "POST_H": 40.0,
                            "LED_DEPTH": 4.3, "LED_Z": 45.5},
}
for tag, p in cases.items():
    ok, solids, vol, errs = build(p, tag.replace(" ", "_"))
    print(f"{tag:28s} ok={ok} solids={solids} vol={vol} {str(errs)[:80]}")
