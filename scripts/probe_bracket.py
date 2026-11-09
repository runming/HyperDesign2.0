import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(r"D:\hyperdesign2")
RUNNER = ROOT / "backend" / "app" / "cadir" / "runner_freecad.py"
FREECAD = r"C:\Users\omegahyper\AppData\Local\Programs\FreeCAD 1.1\bin\freecadcmd.exe"
ir = json.loads((ROOT / "examples" / "bracket_mount.ir.json").read_text(encoding="utf-8"))
tmp = Path(tempfile.mkdtemp(prefix="hd2_bracket_"))
(tmp / "ir.json").write_text(json.dumps(ir, ensure_ascii=False), encoding="utf-8")
env = dict(os.environ, HD2_CAD_IR=str(tmp / "ir.json"), HD2_CAD_OUT=str(tmp))
p = subprocess.run([FREECAD, str(RUNNER)], capture_output=True, text=True,
                   encoding="utf-8", errors="replace", env=env, timeout=300)
rep = json.loads((tmp / "cad_report.json").read_text(encoding="utf-8")) if (tmp / "cad_report.json").exists() else {}
print("ok:", rep.get("ok"))
print("errors:", json.dumps(rep.get("errors"), ensure_ascii=False)[:600])
for f in rep.get("features", []):
    print(" ", f["id"], f["type"], f["status"], f.get("error", "")[:120])
