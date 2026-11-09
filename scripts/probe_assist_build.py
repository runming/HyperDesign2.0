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

ir = json.loads((ROOT / "examples" / "sensor_housing.m0.ir.json").read_text(encoding="utf-8"))
for dims in ((130, 90, 50),):
    ir["parameters"].update({"LENGTH_X": float(dims[0]), "WIDTH_Y": float(dims[1]),
                             "HEIGHT_Z": float(dims[2])})
    tmp = Path(tempfile.mkdtemp(prefix="hd_dbg_"))
    (tmp / "ir.json").write_text(json.dumps(ir, ensure_ascii=False), encoding="utf-8")
    env = dict(os.environ, HD2_CAD_IR=str(tmp / "ir.json"), HD2_CAD_OUT=str(tmp))
    subprocess.run([FREECAD, str(RUNNER)], capture_output=True, text=True, env=env, timeout=300)
    rep = json.loads((tmp / "cad_report.json").read_text(encoding="utf-8"))
    print(dims, "ok=", rep.get("ok"))
    for e in rep.get("errors", []):
        print("   ", e[:220])
