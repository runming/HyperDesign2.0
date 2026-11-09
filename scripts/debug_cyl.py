import math
import sys

import numpy as np

sys.path.insert(0, r"D:\hyperdesign2\backend")
from app.cadrefit import mesh_analytic as MA

tris = MA.synth_tube(5.0, 30.0, seg=48)
unit, centroid, area = MA.tri_normals(tris)
valid = np.isfinite(unit).all(axis=1) & (area > 1e-9)
a = np.array([0.0, 0.0, 1.0])
perp = valid & (np.abs(unit @ a) < 0.08)
idx_perp = np.where(perp)[0]
pts_all = tris[idx_perp].reshape(-1, 3)
coarse = MA.fit_cylinder(pts_all, unit[idx_perp], axis_hint=a)
print("coarse:", coarse["radius"], coarse["rms"])
r, _ = MA._circle_residuals(pts_all, coarse["axis"], coarse["center"])
resid = np.abs(r - coarse["radius"])
print("resid max:", resid.max())
facet_ok = (resid.reshape(len(idx_perp), 3) < max(0.1, 0.05 * 1.5)).all(axis=1)
print("facet_ok:", int(facet_ok.sum()), "/", len(idx_perp))
keep = idx_perp[facet_ok]
cyl = MA.fit_cylinder(tris[keep].reshape(-1, 3), unit[keep], axis_hint=coarse["axis"])
print("refit:", cyl["radius"], cyl["rms"], np.round(cyl["axis"], 3))
_, ang = MA._circle_residuals(tris[keep].reshape(-1, 3), cyl["axis"], cyl["center"])
bins = np.unique(np.round(((ang + math.pi) / (2 * math.pi)) * 72).astype(int) % 72)
print("coverage:", len(bins) * 5.0)
print("radius>0.5:", cyl["radius"] > 0.5, "rms<=0.05:", cyl["rms"] <= 0.05)
