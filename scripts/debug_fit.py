import sys

import numpy as np

sys.path.insert(0, r"D:\hyperdesign2\backend")
from app.cadrefit import mesh_analytic as MA

tris, truth = MA.synth_trimesh(L=100, W=60, H=30, hole_d=10, seg=48)
print("tris:", len(tris), "truth:", truth)
unit, centroid, area = MA.tri_normals(tris)
print("nan normals:", int((~np.isfinite(unit).all(axis=1)).sum()))
print("degenerate:", int((area <= 1e-9).sum()))

planes = MA.segment_planes(tris)
print("planes:", len(planes))
for p in sorted(planes, key=lambda x: -x["triangles"])[:10]:
    print(f"  n={[round(float(v),3) for v in p['normal']]} off={p['offset']:.3f} "
          f"tris={p['triangles']} rms={p['rms']:.6f}")

cyls = MA.segment_cylinders(tris, planes)
print("cylinders:", len(cyls), cyls[:1])
