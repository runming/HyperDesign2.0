# -*- coding: utf-8 -*-
"""网格 → 解析机械特征恢复（平面 / 圆柱）+ 误差证书。

动机（参考 BSpline2Analytic 的 ConvertIsoThenFallback）：
AI 生成的三维网格（TRELLIS 等）是三角面片，毛糙、无量纲语义；
本模块在**极短预算内先尝试规则特征**（轴对齐平面、圆柱孔），
对每个识别出的特征给出「点数 / 主轴 / 尺寸 / RMS / 最大偏差」的**误差证书**，
只有证书通过容差的特征才允许进入参数化重建。

实现要点：
- 平面：法向聚类 + 偏移分簇 + PCA 最小二乘拟合；证书 = 点到平面距离的 RMS/MAX；
- 圆柱：法向与轴垂直性搜索轴向后，投影到垂直平面做代数圆拟合（Kasa）；
  证书 = 径向偏差的 RMS/MAX；
- 不依赖第三方库（仅 numpy），可离线复跑。
"""
from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


# -------------------------------------------------------------------------------- STL
def read_stl(path: Path) -> Tuple[np.ndarray, np.ndarray]:
    """读取二进制或 ASCII STL，返回 (triangles[N,3,3], 顶点(N*3,3))。"""
    raw = Path(path).read_bytes()
    if raw[:5].lower() == b"solid" and b"facet" in raw[:200].lower():
        tris = []
        for line in raw.decode("utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line.startswith("vertex"):
                tris.append([float(x) for x in line.split()[1:4]])
        arr = np.array(tris, dtype=float)
        return arr.reshape(-1, 3, 3), arr
    n = struct.unpack_from("<I", raw, 80)[0]
    tris = np.empty((n, 3, 3), dtype=float)
    for i in range(n):
        off = 84 + i * 50 + 12
        vals = struct.unpack_from("<9f", raw, off)
        tris[i] = np.array(vals, dtype=float).reshape(3, 3)
    return tris, tris.reshape(-1, 3)


# -------------------------------------------------------------------------------- 基础拟合
def tri_normals(tris: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    v0, v1, v2 = tris[:, 0], tris[:, 1], tris[:, 2]
    n = np.cross(v1 - v0, v2 - v0)
    area = np.linalg.norm(n, axis=1) * 0.5
    with np.errstate(invalid="ignore", divide="ignore"):
        unit = n / np.linalg.norm(n, axis=1, keepdims=True)
    unit[~np.isfinite(unit)] = 0.0
    centroid = tris.mean(axis=1)
    return unit, centroid, area


def fit_plane(points: np.ndarray) -> Dict[str, Any]:
    c = points.mean(axis=0)
    _, _, vt = np.linalg.svd(points - c, full_matrices=False)
    normal = vt[2]
    d = float(np.dot(normal, c))
    dist = np.abs(points @ normal - d)
    return {"normal": normal, "offset": d, "point": c,
            "rms": float(np.sqrt((dist ** 2).mean())), "max": float(dist.max())}


def fit_circle_2d(pts: np.ndarray) -> Tuple[np.ndarray, float]:
    """Kasa 代数圆拟合。pts: [N,2]"""
    x, y = pts[:, 0], pts[:, 1]
    A = np.column_stack([2 * x, 2 * y, np.ones(len(x))])
    b = x ** 2 + y ** 2
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    cx, cy = sol[0], sol[1]
    r = math.sqrt(max(sol[2] + cx ** 2 + cy ** 2, 1e-9))
    return np.array([cx, cy]), float(r)


def fit_cylinder(points: np.ndarray, normals: np.ndarray,
                 axis_hint: Optional[np.ndarray] = None) -> Dict[str, Any]:
    """
    圆柱拟合：先用「法向几乎垂直于轴」估计轴向（法向协方差最小特征向量），
    再投影到垂直平面做圆拟合。返回轴向、圆心、半径与径向误差。
    """
    if axis_hint is None:
        cov = np.cov(normals.T)
        w, v = np.linalg.eigh(cov)
        axis = v[:, 0]
    else:
        axis = np.asarray(axis_hint, dtype=float)
    axis = axis / np.linalg.norm(axis)
    # 构造平面基
    tmp = np.array([1.0, 0.0, 0.0]) if abs(axis[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    e1 = np.cross(axis, tmp)
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(axis, e1)
    # 投影点
    c0 = points.mean(axis=0)
    rel = points - c0
    # 去掉轴向分量，回到三维
    axial = rel @ axis
    planar = rel - np.outer(axial, axis)
    xy = np.column_stack([planar @ e1, planar @ e2])
    center2d, radius = fit_circle_2d(xy)
    radial = np.linalg.norm(xy - center2d, axis=1)
    resid = np.abs(radial - radius)
    center3d = c0 + center2d[0] * e1 + center2d[1] * e2
    return {"axis": axis, "center": center3d, "radius": radius,
            "rms": float(np.sqrt((resid ** 2).mean())), "max": float(resid.max()),
            "height": float(axial.max() - axial.min())}


# -------------------------------------------------------------------------------- 特征分割
def segment_planes(tris: np.ndarray, angle_tol_deg: float = 3.0,
                   offset_tol_mm: float = 0.35) -> List[Dict[str, Any]]:
    """两段式：① 按法向做 leader 聚类；② 每个法向簇内按偏移分簇，再逐簇最小二乘拟合。"""
    unit, centroid, area = tri_normals(tris)
    valid = np.isfinite(unit).all(axis=1) & (area > 1e-9)
    cos_tol = math.cos(math.radians(angle_tol_deg))

    leaders: List[Dict[str, Any]] = []
    for idx in np.argsort(-area):
        if not valid[idx]:
            continue
        n = unit[idx]
        for L in leaders:
            if abs(float(np.dot(n, L["n"]))) >= cos_tol:
                L["idx"].append(int(idx))
                break
        else:
            leaders.append({"n": n.copy(), "idx": [int(idx)]})

    groups: List[Dict[str, Any]] = []
    for L in leaders:
        n_ref = L["n"]
        idxs = np.array(L["idx"], dtype=int)
        d = centroid[idxs] @ n_ref
        order = np.argsort(d)
        d_sorted = d[order]
        cut = [0]
        for k in range(1, len(d_sorted)):
            if d_sorted[k] - d_sorted[k - 1] > 2 * offset_tol_mm:
                cut.append(k)
        cut.append(len(d_sorted))
        for a, b in zip(cut[:-1], cut[1:]):
            sel = idxs[order[a:b]]
            if len(sel) < 2:
                continue
            pts = tris[sel].reshape(-1, 3)
            plane = fit_plane(pts)
            if float(np.dot(plane["normal"], n_ref)) < 0:
                plane["normal"] = -plane["normal"]
                plane["offset"] = -plane["offset"]
            groups.append({"kind": "plane", "triangles": int(len(sel)),
                           "area_mm2": round(float(area[sel].sum()), 3),
                           "normal": plane["normal"].tolist() if isinstance(plane["normal"], np.ndarray)
                           else plane["normal"],
                           "offset": float(plane["offset"]),
                           "rms": float(plane["rms"]), "max": float(plane["max"]),
                           "point": [float(x) for x in plane["point"]],
                           "_idx": sel})
    return groups


def _circle_residuals(pts: np.ndarray, axis: np.ndarray, center: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """返回每点径向残差与绕轴角度。"""
    ax = axis / np.linalg.norm(axis)
    tmp = np.array([1.0, 0.0, 0.0]) if abs(ax[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    e1 = np.cross(ax, tmp); e1 /= np.linalg.norm(e1)
    e2 = np.cross(ax, e1)
    rel = pts - center
    planar = rel - np.outer(rel @ ax, ax)
    xy = np.column_stack([planar @ e1, planar @ e2])
    r = np.linalg.norm(xy, axis=1)
    return r, np.arctan2(xy[:, 1], xy[:, 0])


def detect_cylinders(tris: np.ndarray, min_facets: int = 4, min_coverage_deg: float = 300.0,
                     radial_tol_mm: float = 0.05) -> List[Dict[str, Any]]:
    """
    圆柱基元优先检测（孔壁/圆角由许多平面小面片组成，必须先于平面聚类）。

    步骤：轴向候选 → 垂直法向筛面片 → 粗拟合圆 → **按径向残差筛内点面片** → 复拟合 →
    检查内点面片数与角度覆盖，避免把"侧面"误当圆柱。
    """
    unit, centroid, area = tri_normals(tris)
    valid = np.isfinite(unit).all(axis=1) & (area > 1e-9)

    axes: List[np.ndarray] = [np.array(v, float) for v in
                              ([1, 0, 0], [0, 1, 0], [0, 0, 1], [-1, 0, 0], [0, -1, 0], [0, 0, -1])]
    axes = [a / np.linalg.norm(a) for a in axes]

    found: List[Dict[str, Any]] = []
    for a in axes:
        perp = valid & (np.abs(unit @ a) < 0.08)
        if perp.sum() < min_facets:
            continue
        idx_perp = np.where(perp)[0]
        pts_all = tris[idx_perp].reshape(-1, 3)
        try:
            coarse = fit_cylinder(pts_all, unit[idx_perp], axis_hint=a)
        except Exception:
            continue
        if coarse["radius"] <= 0.5:
            continue
        # 内点精化：面片三个顶点径向残差都小才算内点
        r, _ = _circle_residuals(pts_all, coarse["axis"], coarse["center"])
        resid = np.abs(r - coarse["radius"])
        facet_ok = (resid.reshape(len(idx_perp), 3) < max(0.1, radial_tol_mm * 1.5)).all(axis=1)
        keep = idx_perp[facet_ok]
        if len(keep) < min_facets:
            continue
        pts_in = tris[keep].reshape(-1, 3)
        try:
            cyl = fit_cylinder(pts_in, unit[keep], axis_hint=coarse["axis"])
        except Exception:
            continue
        if cyl["radius"] <= 0.5 or cyl["rms"] > radial_tol_mm:
            continue
        _, ang = _circle_residuals(pts_in, cyl["axis"], cyl["center"])
        # 覆盖角 = 360 − 最大角间隙（避免按固定分箱计数时的量化假象）
        a_sorted = np.sort(np.unique(np.round(np.degrees(ang), 3)))
        gaps = np.diff(a_sorted).tolist() + [360.0 - (a_sorted[-1] - a_sorted[0])]
        coverage = 360.0 - float(max(gaps))
        if coverage < min_coverage_deg:
            continue
        ax = cyl["axis"] / np.linalg.norm(cyl["axis"])
        if any(abs(float(np.dot(ax, f["_axis"]))) > 0.99 and
               np.linalg.norm(np.array(f["center"]) - cyl["center"]) < 0.5 for f in found):
            continue
        found.append({"kind": "cylinder", "triangles": int(len(keep)),
                      "area_mm2": round(float(area[keep].sum()), 3),
                      "axis": [float(x) for x in ax], "_axis": ax,
                      "center": [float(x) for x in cyl["center"]],
                      "radius": round(float(cyl["radius"]), 4),
                      "height": round(float(cyl["height"]), 4),
                      "coverage_deg": round(coverage, 1),
                      "rms": round(float(cyl["rms"]), 5), "max": round(float(cyl["max"]), 5),
                      "_idx": keep})
    return found


def segment_cylinders(tris: np.ndarray, planes: List[Dict[str, Any]],
                      axial_tol: float = 0.12, radial_tol_mm: float = 0.2,
                      min_tris: int = 6) -> List[Dict[str, Any]]:
    """兼容旧接口：基于已识别平面之后的残差做二次圆柱拟合。"""
    unit, centroid, area = tri_normals(tris)
    valid = np.isfinite(unit).all(axis=1) & (area > 1e-9)
    covered = np.zeros(len(tris), dtype=bool)
    for pl in planes:
        if "_idx" in pl:
            covered[pl["_idx"]] = True
    cand = valid & ~covered
    if cand.sum() < min_tris:
        return []
    normals = unit[cand]
    cov = np.cov(normals.T)
    _, v = np.linalg.eigh(cov)
    axis = v[:, 0]
    axis = axis / np.linalg.norm(axis)
    pts = tris[cand].reshape(-1, 3)
    try:
        cyl = fit_cylinder(pts, normals, axis_hint=axis)
    except Exception:
        return []
    if cyl["rms"] > radial_tol_mm or cyl["radius"] <= 0:
        return []
    return [{"kind": "cylinder", "triangles": int(cand.sum()),
             "area_mm2": round(float(area[cand].sum()), 3),
             "axis": [float(x) for x in cyl["axis"]],
             "center": [float(x) for x in cyl["center"]],
             "radius": round(float(cyl["radius"]), 4),
             "height": round(float(cyl["height"]), 4),
             "rms": round(float(cyl["rms"]), 5), "max": round(float(cyl["max"]), 5)}]


# -------------------------------------------------------------------------------- 证书与分析
def merge_coplanar(tris: np.ndarray, groups: List[Dict[str, Any]],
                   angle_deg: float = 0.5, offset_mm: float = 0.15) -> List[Dict[str, Any]]:
    """
    合并共面小组：同一物理面常被法向噪声/偏移误差切成许多小片，需按
    「法向夹角 ≤ 0.5° 且 面距 ≤ 0.15mm」合并后重新最小二乘拟合。
    """
    cos_tol = math.cos(math.radians(angle_deg))
    merged: List[Dict[str, Any]] = []
    for g in sorted(groups, key=lambda x: -x["triangles"]):
        n_g = np.asarray(g["normal"], dtype=float)
        placed = False
        for m in merged:
            n_m = np.asarray(m["normal"], dtype=float)
            if abs(float(np.dot(n_g, n_m))) < cos_tol:
                continue
            if abs(float(g["offset"]) - float(m["offset"])) > offset_mm:
                continue
            m["_idx"] = np.concatenate([m["_idx"], g["_idx"]])
            m["triangles"] += g["triangles"]
            m["area_mm2"] = round(float(m["area_mm2"]) + float(g["area_mm2"]), 3)
            placed = True
            break
        if not placed:
            merged.append(dict(g, _idx=np.array(g["_idx"], dtype=int)))

    # 合并后按各自点集重新拟合
    out: List[Dict[str, Any]] = []
    for m in merged:
        pts = tris[m["_idx"]].reshape(-1, 3)
        plane = fit_plane(pts)
        n_ref = np.asarray(m["normal"], dtype=float)
        if float(np.dot(plane["normal"], n_ref)) < 0:
            plane["normal"] = -plane["normal"]
            plane["offset"] = -plane["offset"]
        out.append({"kind": "plane", "triangles": int(len(m["_idx"])),
                    "area_mm2": m["area_mm2"],
                    "normal": [float(x) for x in plane["normal"]],
                    "offset": float(plane["offset"]),
                    "rms": float(plane["rms"]), "max": float(plane["max"]),
                    "point": [float(x) for x in plane["point"]],
                    "_idx": m["_idx"]})
    return sorted(out, key=lambda x: -x["triangles"])


def certificate(features: List[Dict[str, Any]], tol_mm: float = 0.1) -> Dict[str, Any]:
    """逐特征给证书；任一超差即整体不通过（不放行未验证的几何）。"""
    rows = []
    for i, f in enumerate(features):
        rms, mx = f.get("rms", 9e9), f.get("max", 9e9)
        ok = (rms <= tol_mm) and (mx <= tol_mm * 3)
        rows.append({"index": i, "kind": f["kind"], "triangles": f.get("triangles"),
                     "rms_mm": round(float(rms), 5), "max_mm": round(float(mx), 5),
                     "tolerance_mm": tol_mm, "passed": bool(ok)})
    return {"tolerance_mm": tol_mm, "features": len(rows),
            "passed": all(r["passed"] for r in rows), "rows": rows}


def analyze(path: Path, tol_mm: float = 0.1) -> Dict[str, Any]:
    tris, _ = read_stl(path)
    # 顺序很重要：先提圆柱基元（孔壁/圆角是多个平面小面片，会被平面聚类吃掉）
    cyls = detect_cylinders(tris)
    covered = np.zeros(len(tris), dtype=bool)
    for c in cyls:
        covered[c["_idx"]] = True
    rest = tris[~covered] if covered.any() else tris
    planes = merge_coplanar(rest, segment_planes(rest)) if len(rest) else []
    feats = planes + cyls
    cert = certificate(feats, tol_mm)
    total_area = float(sum(p["area_mm2"] for p in planes)) or 1.0
    major = [p for p in planes if p["area_mm2"] / total_area >= 0.01]
    top1 = (planes[0]["area_mm2"] / total_area) if planes else 0.0
    top6 = sum(p["area_mm2"] for p in planes[:6]) / total_area if planes else 0.0
    return {"triangle_count": int(len(tris)),
            "planes": len(planes), "cylinders": len(cyls),
            "major_planes": len(major), "top1_area_ratio": round(top1, 4),
            "top6_area_ratio": round(top6, 4),
            "features": feats, "certificate": cert}


# -------------------------------------------------------------------------------- 合成算例
def synth_box(L: float = 100.0, W: float = 60.0, H: float = 30.0,
              noise_mm: float = 0.0, seed: int = 0) -> np.ndarray:
    """纯长方体（6 个平面，无孔），用于平面恢复自检。"""
    rng = np.random.default_rng(seed)
    x0, x1 = -L / 2, L / 2
    y0, y1 = -W / 2, W / 2
    z0, z1 = 0.0, H
    tris = []

    def quad(a, b, c, d):
        tris.append([a, b, c])
        tris.append([a, c, d])

    quad([x0, y0, z0], [x1, y0, z0], [x1, y0, z1], [x0, y0, z1])
    quad([x1, y1, z0], [x0, y1, z0], [x0, y1, z1], [x1, y1, z1])
    quad([x1, y0, z0], [x1, y1, z0], [x1, y1, z1], [x1, y0, z1])
    quad([x0, y1, z0], [x0, y0, z0], [x0, y0, z1], [x0, y1, z1])
    quad([x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1])   # 顶
    quad([x0, y1, z0], [x1, y1, z0], [x1, y0, z0], [x0, y0, z0])   # 底
    arr = np.array(tris, dtype=float)
    if noise_mm > 0:
        arr = arr + rng.normal(0.0, noise_mm, size=arr.shape)
    return arr


def synth_tube(radius: float = 5.0, height: float = 30.0, seg: int = 48,
               noise_mm: float = 0.0, seed: int = 0) -> np.ndarray:
    """纯圆柱管（侧面 + 上下盖），用于圆柱恢复自检。"""
    rng = np.random.default_rng(seed)
    tris = []
    for i in range(seg):
        j = (i + 1) % seg
        a0 = 2 * math.pi * i / seg
        a1 = 2 * math.pi * j / seg
        p0 = [radius * math.cos(a0), radius * math.sin(a0)]
        p1 = [radius * math.cos(a1), radius * math.sin(a1)]
        # 侧面
        tris.append([[p0[0], p0[1], 0.0], [p1[0], p1[1], 0.0], [p1[0], p1[1], height]])
        tris.append([[p0[0], p0[1], 0.0], [p1[0], p1[1], height], [p0[0], p0[1], height]])
        # 上下盖
        tris.append([[0.0, 0.0, height], [p0[0], p0[1], height], [p1[0], p1[1], height]])
        tris.append([[0.0, 0.0, 0.0], [p1[0], p1[1], 0.0], [p0[0], p0[1], 0.0]])
    arr = np.array(tris, dtype=float)
    if noise_mm > 0:
        arr = arr + rng.normal(0.0, noise_mm, size=arr.shape)
    return arr


def write_binary_stl(tris: np.ndarray, path: Path) -> Path:
    import struct
    with open(path, "wb") as fh:
        fh.write(b"\0" * 80)
        fh.write(struct.pack("<I", len(tris)))
        for t in tris:
            fh.write(struct.pack("<3f", 0, 0, 0))
            for v in t:
                fh.write(struct.pack("<3f", *[float(x) for x in v]))
            fh.write(struct.pack("<H", 0))
    return path


def synth_box_with_hole(L: float = 100.0, W: float = 60.0, H: float = 30.0,
                        hole_d: float = 10.0, seg: int = 48,
                        noise_mm: float = 0.0, seed: int = 0) -> np.ndarray:
    """生成带通孔的长方体三角网格（已知解析真值），用于自检与噪声鲁棒性测试。"""
    rng = np.random.default_rng(seed)
    tris: List[List[List[float]]] = []

    def quad(a, b, c, d):
        tris.append([a, b, c])
        tris.append([a, c, d])

    x0, x1 = -L / 2, L / 2
    y0, y1 = -W / 2, W / 2
    z0, z1 = 0.0, H
    # 侧面（不含顶底面，顶面要挖孔）
    quad([x0, y0, z0], [x1, y0, z0], [x1, y0, z1], [x0, y0, z1])   # -Y
    quad([x1, y1, z0], [x0, y1, z0], [x0, y1, z1], [x1, y1, z1])   # +Y
    quad([x1, y0, z0], [x1, y1, z0], [x1, y1, z1], [x1, y0, z1])   # +X
    quad([x0, y1, z0], [x0, y0, z0], [x0, y0, z1], [x0, y1, z1])   # -X
    quad([x0, y0, z0], [x0, y1, z0], [x1, y1, z0], [x1, y0, z0])   # -Z

    # 顶面：四块 + 圆环向孔中心过渡（用环扇形近似）
    cx, cy = 0.0, 0.0
    r = hole_d / 2
    ring = [(cx + r * math.cos(2 * math.pi * i / seg), cy + r * math.sin(2 * math.pi * i / seg))
            for i in range(seg)]
    # 顶面外圈到内圈：把矩形边界按角度投影到外圈
    outer = []
    for i in range(seg):
        ang = 2 * math.pi * i / seg
        # 从中心沿角度射线与外框求交
        dx, dy = math.cos(ang), math.sin(ang)
        ts = []
        if abs(dx) > 1e-9:
            ts += [(x1 / dx), (x0 / dx)]
        if abs(dy) > 1e-9:
            ts += [(y1 / dy), (y0 / dy)]
        t = min([t for t in ts if t > 0])
        outer.append((cx + dx * t, cy + dy * t))
    for i in range(seg):
        j = (i + 1) % seg
        a = [outer[i][0], outer[i][1], z1]
        b = [outer[j][0], outer[j][1], z1]
        c = [ring[j][0], ring[j][1], z1]
        d = [ring[i][0], ring[i][1], z1]
        quad(a, b, c, d)
        # 孔壁
        tris.append([[ring[i][0], ring[i][1], z0], [ring[j][0], ring[j][1], z0],
                     [ring[j][0], ring[j][1], z1]])
        tris.append([[ring[i][0], ring[i][1], z0], [ring[j][0], ring[j][1], z1],
                     [ring[i][0], ring[i][1], z1]])

    arr = np.array(tris, dtype=float)
    # 剔除退化三角形（四角射线重复导致的零面积面）
    v0, v1, v2 = arr[:, 0], arr[:, 1], arr[:, 2]
    keep = np.linalg.norm(np.cross(v1 - v0, v2 - v0), axis=1) > 1e-9
    arr = arr[keep]
    if noise_mm > 0:
        arr = arr + rng.normal(0.0, noise_mm, size=arr.shape)
    return arr


def synth_trimesh(L=100.0, W=60.0, H=30.0, hole_d=10.0, seg=48, noise=0.0, seed=0):
    """返回 (tris, 真值字典)。"""
    tris = synth_box_with_hole(L, W, H, hole_d, seg, noise, seed)
    return tris, {"L": L, "W": W, "H": H, "hole_d": hole_d, "noise": noise}
