# -*- coding: utf-8 -*-
"""
CAD-IR 解释器（FreeCAD/OCCT 执行器）—— 由 HyperDesign 2.0 的 CAD Worker 调用

设计原则（对标 08-cad-ir 规范，并做差异化增强）：
1. **本文件是唯一的可执行体**：智能体只能产出 JSON 数据（CAD-IR），永远不能提交 Python 代码；
2. 特征算子**白名单**：未注册的 type 直接返回 CAD_FEATURE_UNSUPPORTED 并终止；
3. 语义引用：输出「语义名 -> 引擎拓扑对象」映射，业务层不引用 Edge1/Face3；
4. 每个特征产出结构化状态（ok/failed + 诊断 + 耗时），失败即停并保留已完成部分；
5. 产出几何元数据（包围盒/体积/表面积/质心/实体数/面数/边数）供 Harness 裁决；
6. 数值全部做有限性与范围检查，路径由 Worker 分配（不接受用户拼接）。

用法：
  freecadcmd runner_freecad.py <ir.json> <out_dir>
退出码：0 成功；2 IR/参数非法；3 特征执行失败；4 导出失败
"""
import json
import math
import os
import sys
import time
import traceback

import FreeCAD
import Part

SCHEMA_VERSION = "1.0"
MAX_FEATURES = 200
ABS_LIMIT = 1.0e4          # 任何几何参数的绝对值上限（mm）
MIN_POSITIVE = 1.0e-4      # 任何"必须为正"的参数下限


# --------------------------------------------------------------------------------------
# 工具函数
# --------------------------------------------------------------------------------------
def _num(v, params, where):
    """把 IR 中的数值/参数名解析为有限浮点数，并做范围检查。"""
    if isinstance(v, str):
        if v not in params:
            raise ValueError(f"{where}: 引用了未定义参数 '{v}'")
        v = params[v]
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError(f"{where}: 期望数值，得到 {type(v).__name__}")
    f = float(v)
    if not math.isfinite(f):
        raise ValueError(f"{where}: 非有限数值")
    if abs(f) > ABS_LIMIT:
        raise ValueError(f"{where}: {f} 超出允许范围 ±{ABS_LIMIT}")
    return f


def _pos(v, params, where):
    if not v:
        raise ValueError(f"{where}: 位置非法")
    vals = [_num(x, params, where) for x in v]
    if len(vals) == 2:
        vals.append(0.0)
    if len(vals) != 3:
        raise ValueError(f"{where}: 位置应为 2 或 3 元组")
    return FreeCAD.Vector(*vals)


def _edges_by(shape, selector, height=None):
    """语义选择器 -> 边列表（业务层不直接引用 Edge 编号）。"""
    if selector == "all_edges":
        return list(shape.Edges)
    if selector == "vertical_edges":
        return [e for e in shape.Edges
                if abs(e.Vertexes[0].Point.z - e.Vertexes[1].Point.z) > 1e-6]
    if selector == "top_edges":
        zs = [v.Point.z for v in shape.Vertexes]
        zmax = max(zs) if zs else 0.0
        return [e for e in shape.Edges
                if abs(e.Vertexes[0].Point.z - zmax) < 1e-6 and abs(e.Vertexes[1].Point.z - zmax) < 1e-6]
    if selector == "bottom_edges":
        zs = [v.Point.z for v in shape.Vertexes]
        zmin = min(zs) if zs else 0.0
        return [e for e in shape.Edges
                if abs(e.Vertexes[0].Point.z - zmin) < 1e-6 and abs(e.Vertexes[1].Point.z - zmin) < 1e-6]
    if selector == "horizontal_edges":
        return [e for e in shape.Edges
                if abs(e.Vertexes[0].Point.z - e.Vertexes[1].Point.z) <= 1e-6]
    if selector == "non_horizontal_edges":
        # 立方体 -> 垂直棱；带拔模锥体 -> 倾斜角棱（统一语义，不用改 IR）
        return [e for e in shape.Edges
                if abs(e.Vertexes[0].Point.z - e.Vertexes[1].Point.z) > 1e-6]
    raise ValueError(f"未知的边选择器 '{selector}'")


def _faces_by(shape, selector):
    if selector == "all_faces":
        return list(shape.Faces)
    if selector == "bottom_face":
        return [f for f in shape.Faces if abs(f.normalAt(0, 0).z + 1.0) < 1e-6]
    if selector == "top_face":
        return [f for f in shape.Faces if abs(f.normalAt(0, 0).z - 1.0) < 1e-6]
    raise ValueError(f"未知的面选择器 '{selector}'")


def _positions(spec, params, shape):
    """位置组：显式点列，或按基体包围盒推导的四角内缩点（语义化，不写死坐标）。"""
    if spec is None:
        return []
    t = spec.get("type", "explicit")
    if t == "explicit":
        return [_pos(p, params, "positions.points") for p in spec.get("points", [])]
    if t == "corner4":
        inset = spec.get("inset", [0, 0])
        ix = _num(inset[0], params, "positions.inset[0]")
        iy = _num(inset[1], params, "positions.inset[1]")
        bb = shape.BoundBox
        cx1, cx2 = bb.XMin + ix, bb.XMax - ix
        cy1, cy2 = bb.YMin + iy, bb.YMax - iy
        return [FreeCAD.Vector(cx1, cy1, 0), FreeCAD.Vector(cx2, cy1, 0),
                FreeCAD.Vector(cx1, cy2, 0), FreeCAD.Vector(cx2, cy2, 0)]
    raise ValueError(f"未知的位置类型 '{t}'")


# --------------------------------------------------------------------------------------
# 白名单算子
# --------------------------------------------------------------------------------------
def op_create_box(shape, feat, params):
    p = feat["params"]
    L = _num(p["length"], params, "create_box.length")
    W = _num(p["width"], params, "create_box.width")
    H = _num(p["height"], params, "create_box.height")
    for name, val in (("length", L), ("width", W), ("height", H)):
        if val < MIN_POSITIVE:
            raise ValueError(f"create_box.{name} 必须为正（{val}）")
    center = p.get("center", "origin_bottom_center")
    if center == "origin_bottom_center":
        base = FreeCAD.Vector(-L / 2.0, -W / 2.0, 0.0)
    elif center == "origin_center":
        base = FreeCAD.Vector(-L / 2.0, -W / 2.0, -H / 2.0)
    else:
        base = _pos(center, params, "create_box.center")
    box = Part.makeBox(L, W, H, base)
    return box, {"body": "body", "top_face": "top_face", "bottom_face": "bottom_face"}


def op_shell(shape, feat, params):
    """
    抽壳。两种策略：
      thickness  —— OCC makeThickness（对简单棱柱最稳，v1 用法）
      cavity_cut —— 构造「内腔偏移体」后布尔切除（对带拔模的放样体可靠）
                   内腔按法向厚度 t 偏移，并给内角随形圆角 R_outer - t，
                   使拐角处壁厚仍为 t（否则 R3 外圆角 + 尖内角 => 拐角壁厚仅 ~1.52mm，违反 2.4mm 铁律）
    """
    p = feat["params"]
    t = _num(p["thickness"], params, "shell.thickness")
    if t <= 0:
        raise ValueError("shell.thickness 必须为正")
    open_faces = p.get("open_faces", "none")
    strategy = p.get("strategy", "auto")

    if strategy in ("auto", "thickness") and open_faces != "none":
        faces = _faces_by(shape, "bottom_face" if open_faces == "bottom" else "top_face")
        if not faces:
            raise ValueError(f"shell: 未找到待开口的面（{open_faces}）")
        try:
            out = shape.makeThickness(faces, -t, 1e-3)
            return out, {"shell": "thickness", "wall_mm": t}
        except Exception as exc:
            if strategy == "thickness":
                raise ValueError(f"shell(makeThickness) 失败：{exc}")
            # auto 模式：落到 cavity_cut

    # ---------- cavity_cut ----------
    warnings = []
    bb = shape.BoundBox
    L, W, H = bb.XLength, bb.YLength, bb.ZLength
    d = _num(p.get("draft_deg", 0.0), params, "shell.draft_deg")
    cosd = math.cos(math.radians(d))
    if cosd < 0.2:
        raise ValueError("shell.draft_deg 过大")
    ttan = math.tan(math.radians(d))
    off = t / cosd                       # 水平偏移量：法向厚度 = t
    top_z = bb.ZMax - off                # 顶壁按法向厚度收口
    z_lo = bb.ZMin - 1.0 if open_faces == "bottom" else bb.ZMin + off

    r_out = p.get("corner_radius_outer")
    if r_out is None:
        raise ValueError("cavity_cut 需要 corner_radius_outer（用于保证拐角等壁厚）")
    r_out = _num(r_out, params, "shell.corner_radius_outer")

    def sec(z):
        """给定高度，返回内腔截面的 (span_x, span_y, corner_r)。"""
        sx = L - 2 * off - 2 * z * ttan
        sy = W - 2 * off - 2 * z * ttan
        r = r_out - z * ttan - off
        return sx, sy, r

    sx0, sy0, r0 = sec(z_lo)
    sx1, sy1, r1 = sec(top_z)
    for tag, sx, sy, r in (("底部", sx0, sy0, r0), ("顶部", sx1, sy1, r1)):
        if min(sx, sy) <= 1.0:
            raise ValueError(f"cavity_cut: {tag}内腔截面过小 {sx:.2f}×{sy:.2f}")
        if r <= 0.15:
            raise ValueError(
                f"cavity_cut: {tag}内角半径只有 {r:.3f}mm —— 外角 R{r_out} 在拔模 "
                f"{d}°/高度 {H}mm 下已不足以维持 {t}mm 等壁厚圆角。"
                f"请增大外角半径（≥ 拔模内缩 + 壁厚 ≈ {H * ttan + t:.2f}mm）或降低高度。")

    cav_lo = Part.makePolygon(_rounded_rect_points(sx0, sy0, r0, z_lo))
    cav_hi = Part.makePolygon(_rounded_rect_points(sx1, sy1, r1, top_z))
    cavity = Part.makeLoft([cav_lo, cav_hi], True, True, False)
    if not cavity.isValid():
        raise ValueError("cavity_cut: 内腔放样无效")

    out = shape.cut(cavity)
    if float(out.Volume) <= 0:
        raise ValueError("cavity_cut: 布尔切除结果体积非正")
    return out, {"shell": "cavity_cut", "wall_mm": t,
                 "inner_corner_r_bottom": round(r0, 3), "inner_corner_r_top": round(r1, 3),
                 "top_wall_z": round(top_z, 3), "warnings": warnings}


def op_fillet(shape, feat, params):
    p = feat["params"]
    r = _num(p["radius"], params, "fillet.radius")
    if r <= 0:
        raise ValueError("fillet.radius 必须为正")
    edges = _edges_by(shape, p.get("selector", "vertical_edges"))
    if not edges:
        raise ValueError(f"fillet: 选择器 '{p.get('selector')}' 未命中任何边")
    return shape.makeFillet(r, edges), {"filleted_edges": f"count:{len(edges)}"}


def op_chamfer(shape, feat, params):
    p = feat["params"]
    size = _num(p["size"], params, "chamfer.size")
    if size <= 0:
        raise ValueError("chamfer.size 必须为正")
    edges = _edges_by(shape, p.get("selector", "top_edges"))
    if not edges:
        raise ValueError(f"chamfer: 选择器 '{p.get('selector')}' 未命中任何边")
    return shape.makeChamfer(size, edges), {"chamfered_edges": f"count:{len(edges)}"}


def op_add_cylinder(shape, feat, params):
    p = feat["params"]
    r = _num(p["radius"], params, "add_cylinder.radius")
    h = _num(p["height"], params, "add_cylinder.height")
    if r <= 0 or h <= 0:
        raise ValueError("add_cylinder 半径与高度必须为正")
    pts = _positions(p.get("positions"), params, shape)
    if not pts:
        pts = [_pos(p.get("at"), params, "add_cylinder.at")]
    z0 = _num(p.get("z_start", 0.0), params, "add_cylinder.z_start")
    mode = p.get("mode", "fuse")
    n = 0
    for pt in pts:
        cyl = Part.makeCylinder(r, h, FreeCAD.Vector(pt.x, pt.y, z0))
        shape = shape.fuse(cyl) if mode == "fuse" else shape.cut(cyl)
        n += 1
    return shape, {f"{mode}_cylinders": f"count:{n}"}


def op_add_boss_pattern(shape, feat, params):
    """螺钉柱：先 fuse 外柱，再 cut 内孔（顺序固定，避免自交）。"""
    p = feat["params"]
    od = _num(p["outer_diameter"], params, "boss.outer_diameter")
    idia = _num(p["inner_diameter"], params, "boss.inner_diameter")
    h = _num(p["height"], params, "boss.height")
    if not (0 < idia < od):
        raise ValueError(f"boss 尺寸非法：外径 {od} / 内径 {idia}")
    pts = _positions(p.get("positions"), params, shape)
    if not pts:
        raise ValueError("boss 需要 positions")
    z0 = _num(p.get("z_start", 0.0), params, "boss.z_start")
    for pt in pts:
        shape = shape.fuse(Part.makeCylinder(od / 2.0, h, FreeCAD.Vector(pt.x, pt.y, z0)))
    for pt in pts:
        shape = shape.cut(Part.makeCylinder(idia / 2.0, h + 2.0,
                                            FreeCAD.Vector(pt.x, pt.y, z0 - 1.0)))
    return shape, {"bosses": f"count:{len(pts)}"}


def op_add_hole_pattern(shape, feat, params):
    p = feat["params"]
    d = _num(p["diameter"], params, "hole.diameter")
    if d <= 0:
        raise ValueError("hole.diameter 必须为正")
    depth = p.get("depth", "through")
    pts = _positions(p.get("positions"), params, shape)
    if not pts:
        raise ValueError("hole 需要 positions")
    axis = p.get("axis", "Z")
    if axis not in ("X", "Y", "Z"):
        raise ValueError(f"hole.axis 只能是 X/Y/Z（得到 {axis}）")
    bb = shape.BoundBox
    span = {"Z": bb.ZLength, "X": bb.XLength, "Y": bb.YLength}[axis]
    h = span + 2.0 if depth == "through" else _num(depth, params, "hole.depth")
    # 直接用 makeCylinder 的方向参数建轴向孔（rotate(axis=零向量) 会抛 gp_Dir 零范数错误）
    direction = {"X": FreeCAD.Vector(1, 0, 0), "Y": FreeCAD.Vector(0, 1, 0),
                 "Z": FreeCAD.Vector(0, 0, 1)}[axis]
    for pt in pts:
        if axis == "Z":
            base = FreeCAD.Vector(pt.x, pt.y, bb.ZMin - 1.0)
        elif axis == "X":
            base = FreeCAD.Vector(bb.XMin - 1.0, pt.y, pt.z)
        else:
            base = FreeCAD.Vector(pt.x, bb.YMin - 1.0, pt.z)
        shape = shape.cut(Part.makeCylinder(d / 2.0, h, base, direction))
    return shape, {"holes": f"count:{len(pts)}", "axis": axis}


def _rounded_rect_points(L, W, R, z, seg=24):
    """
    圆角矩形折线点列（逆时针、闭合、点数固定 = 2 + 4*(seg+1)）。
    用折线逼近圆弧而非 Part.Arc：FreeCAD 的线框圆弧拼接会产生数值缝隙，
    导致 makeLoft 得到无效实体；seg=24 时弦误差 = R*(1-cos(pi/(4*seg))) ≈ 0.003mm。
    """
    if R < 1e-6:
        R = 1e-6
    if 2 * R >= min(L, W) - 1e-9:
        raise ValueError(f"圆角半径 {R:.3f} 相对截面 {L:.3f}×{W:.3f} 过大")
    x, y = L / 2.0, W / 2.0
    pts = [FreeCAD.Vector(-x + R, -y, z), FreeCAD.Vector(x - R, -y, z)]
    corners = [(x - R, -y + R, -90.0, 0.0), (x - R, y - R, 0.0, 90.0),
               (-x + R, y - R, 90.0, 180.0), (-x + R, -y + R, 180.0, 270.0)]
    for cx, cy, a0, a1 in corners:
        for i in range(seg + 1):
            a = math.radians(a0 + (a1 - a0) * i / seg)
            pts.append(FreeCAD.Vector(cx + R * math.cos(a), cy + R * math.sin(a), z))
    return pts


def op_create_tapered_box(shape, feat, params):
    """
    带拔模与圆角的基体：底面 L×W（z=0，真实最大包络），向上按 draft_deg 收小，
    顶面圆角半径按等距偏移解析缩减 R - H*tan(d)。
    """
    p = feat["params"]
    L = _num(p["length"], params, "create_tapered_box.length")
    W = _num(p["width"], params, "create_tapered_box.width")
    H = _num(p["height"], params, "create_tapered_box.height")
    d = _num(p.get("draft_deg", 1.8), params, "create_tapered_box.draft_deg")
    R = _num(p.get("corner_radius", 3.0), params, "create_tapered_box.corner_radius")
    if d < 0 or d > 45:
        raise ValueError(f"draft_deg 应在 [0,45]（{d}）")
    for name, val in (("length", L), ("width", W), ("height", H)):
        if val < MIN_POSITIVE:
            raise ValueError(f"create_tapered_box.{name} 必须为正（{val}）")
    t = math.tan(math.radians(d))
    inset = H * t
    r_top = R - inset
    if r_top <= 0.15:
        raise ValueError(
            f"拔模内缩 {inset:.2f}mm 使顶部圆角半径只剩 {r_top:.2f}mm："
            f"请增大外角半径（≥ 拔模内缩 + 壁厚）或降低高度")
    lo = Part.makePolygon(_rounded_rect_points(L, W, R, 0.0))
    hi = Part.makePolygon(_rounded_rect_points(L - 2 * inset, W - 2 * inset, r_top, H))
    solid = Part.makeLoft([lo, hi], True, True, False)
    if not solid.isValid() or float(solid.Volume) <= 0:
        raise ValueError("create_tapered_box: 放样实体无效（检查尺寸/圆角/拔模组合）")
    return solid, {"body": "body", "draft_inset_mm": round(inset, 4),
                   "corner_radius_bottom": R, "corner_radius_top": round(r_top, 4),
                   "top_span": [round(L - 2 * inset, 4), round(W - 2 * inset, 4)]}


def op_fuse(shape, feat, params):
    """与一个由参数派生的简单体融合（支架/耳板等），几何由尺寸数据完全决定。"""
    p = feat["params"]
    kind = p.get("primitive", "box")
    if kind == "box":
        L = _num(p["length"], params, "fuse.box.length")
        W = _num(p["width"], params, "fuse.box.width")
        H = _num(p["height"], params, "fuse.box.height")
        at = _pos(p.get("at"), params, "fuse.box.at")
        tool = Part.makeBox(L, W, H, FreeCAD.Vector(at.x, at.y, at.z))
    elif kind == "cylinder":
        r = _num(p["radius"], params, "fuse.cylinder.radius")
        h = _num(p["height"], params, "fuse.cylinder.height")
        at = _pos(p.get("at"), params, "fuse.cylinder.at")
        tool = Part.makeCylinder(r, h, FreeCAD.Vector(at.x, at.y, at.z))
    else:
        raise ValueError(f"fuse: 未知 primitive '{kind}'")
    return shape.fuse(tool), {"fused": kind}


OPS = {
    "create_box": op_create_box,
    "create_tapered_box": op_create_tapered_box,
    "shell": op_shell,
    "fillet": op_fillet,
    "chamfer": op_chamfer,
    "add_cylinder": op_add_cylinder,
    "add_boss_pattern": op_add_boss_pattern,
    "add_hole_pattern": op_add_hole_pattern,
    "fuse": op_fuse,
}

CAPABILITIES = [
    "create_box", "create_tapered_box", "shell", "fillet", "chamfer", "add_cylinder",
    "add_boss_pattern", "add_hole_pattern", "fuse",
    "step_export", "stl_export", "glb_export", "validate_shape", "semantic_refs",
    "dfm_face_field",
]


# --------------------------------------------------------------------------------------
# 执行器
# --------------------------------------------------------------------------------------
def topological(features):
    by_id = {f["id"]: f for f in features}
    done, order = set(), []

    def visit(fid, stack):
        if fid in done:
            return
        if fid in stack:
            raise ValueError(f"CAD-IR 存在循环依赖：{' -> '.join(stack + [fid])}")
        f = by_id.get(fid)
        if f is None:
            raise ValueError(f"依赖引用了不存在的特征 '{fid}'")
        for dep in f.get("depends_on", []):
            visit(dep, stack + [fid])
        done.add(fid)
        order.append(f)

    for f in features:
        visit(f["id"], [])
    return order


def _dfm_draft(shape, side_limit_deg=45.0):
    """
    在 B-Rep 上直接量拔模角：对每个平面取法向与 +Z（脱模方向）的夹角 α，
    拔模角 = 90° - α = asin(|n·Z|)。只统计"侧壁类"平面（拔模角 < 45°），
    并统计垂直面数量（拔模=0，卡模拉伤风险）。
    这是 v1 没有的能力：v1 只在三角网格上量，CAD 实体本身是否为直壁无人校验。
    """
    vals, vertical = [], 0
    for f in shape.Faces:
        if not isinstance(getattr(f, "Surface", None), Part.Plane):
            continue
        n = f.normalAt(0, 0)
        n.normalize()
        nz = min(1.0, max(0.0, abs(n.z)))
        ang = math.degrees(math.asin(nz))
        if ang < side_limit_deg:
            vals.append(ang)
            if ang < 1e-3:
                vertical += 1
    if not vals:
        return {"measured": False, "reason": "无侧壁类平面"}
    vals.sort()
    return {"measured": True, "planar_side_faces": len(vals),
            "min_draft_deg": round(vals[0], 3),
            "median_draft_deg": round(vals[len(vals) // 2], 3),
            "vertical_face_count": vertical, "pull_direction": "+Z"}


def main(argv):
    # 参数来源：优先环境变量（freecadcmd 会把命令行里的 .json 当成待打开文档，故不走 argv）
    ir_path = os.environ.get("HD2_CAD_IR")
    out_dir = os.environ.get("HD2_CAD_OUT")
    if not ir_path or not out_dir:
        if len(argv) >= 3:
            ir_path, out_dir = argv[1], argv[2]
        else:
            print("用法: HD2_CAD_IR=<ir.json> HD2_CAD_OUT=<out_dir> freecadcmd runner_freecad.py")
            return 2
    os.makedirs(out_dir, exist_ok=True)

    with open(ir_path, "r", encoding="utf-8") as fh:
        ir = json.load(fh)

    report = {"schema_version": SCHEMA_VERSION, "engine": "freecad_occt",
              "engine_version": ".".join(str(x) for x in FreeCAD.Version()[:3]),
              "capabilities": CAPABILITIES, "features": [], "outputs": {},
              "errors": [], "started": time.strftime("%Y-%m-%dT%H:%M:%S")}

    if ir.get("schema_version") != SCHEMA_VERSION:
        report["errors"].append(f"CAD_IR_SCHEMA_MISMATCH: 期望 {SCHEMA_VERSION}，得到 {ir.get('schema_version')}")
        _write(report, out_dir)
        return 2

    params = ir.get("parameters", {})
    features = ir.get("features", [])
    if not features or len(features) > MAX_FEATURES:
        report["errors"].append(f"CAD_IR_FEATURE_COUNT_INVALID: {len(features)}")
        _write(report, out_dir)
        return 2
    for f in features:
        if f.get("type") not in OPS:
            report["errors"].append(
                f"CAD_FEATURE_UNSUPPORTED: '{f.get('type')}'（引擎能力不含此算子；"
                f"可用：{', '.join(sorted(OPS))}）")
    if report["errors"]:
        _write(report, out_dir)
        return 2

    shape = None
    semantic = {}
    try:
        for feat in topological(features):
            t0 = time.time()
            entry = {"id": feat["id"], "type": feat["type"], "status": "ok", "diagnostics": {}}
            try:
                shape, refs = OPS[feat["type"]](shape, feat, params)
                semantic.update(refs)
                entry["diagnostics"] = refs
            except Exception as exc:  # 特征级失败：记录并停止后续依赖特征
                entry["status"] = "failed"
                entry["error"] = f"{type(exc).__name__}: {exc}"
                entry["trace"] = traceback.format_exc(limit=3)
                entry["elapsed_ms"] = int((time.time() - t0) * 1000)
                report["features"].append(entry)
                report["errors"].append(f"CAD_FEATURE_FAILED: {feat['id']} -> {entry['error']}")
                break
            entry["elapsed_ms"] = int((time.time() - t0) * 1000)
            report["features"].append(entry)

        if shape is None or any(e["status"] == "failed" for e in report["features"]):
            _write(report, out_dir)
            return 3

        # 几何元数据（Harness 裁决依据）——Compound/Solid 差异做兜底
        # 注意：布尔运算后 FreeCAD 的 BoundBox 会被刀具面"撑大"（实测 z=[-1,45] 而真实材料只在 [0,45]），
        # 因此包络一律由真实顶点计算，避免误判基准面。
        raw_bb = shape.BoundBox
        verts = list(getattr(shape, "Vertexes", []) or [])
        if verts:
            xs = [v.Point.x for v in verts]
            ys = [v.Point.y for v in verts]
            zs = [v.Point.z for v in verts]
            xmin, xmax = min(xs), max(xs)
            ymin, ymax = min(ys), max(ys)
            zmin, zmax = min(zs), max(zs)
        else:
            xmin, xmax = raw_bb.XMin, raw_bb.XMax
            ymin, ymax = raw_bb.YMin, raw_bb.YMax
            zmin, zmax = raw_bb.ZMin, raw_bb.ZMax
        solids = list(getattr(shape, "Solids", []) or [])
        try:
            shape.validate()
        except Exception:
            pass
        vol = float(getattr(shape, "Volume", 0.0) or 0.0)
        area = float(getattr(shape, "Area", 0.0) or 0.0)
        if vol <= 0 and solids:
            vol = sum(float(s.Volume) for s in solids)
        if area <= 0 and solids:
            area = sum(float(s.Area) for s in solids)
        com = None
        for cand in [shape] + solids:
            try:
                com = [round(float(c), 4) for c in cand.CenterOfMass]
                break
            except Exception:
                continue
        try:
            is_valid = bool(shape.isValid())
        except Exception:
            is_valid = False
        report["metrics"] = {
            "is_valid": is_valid,
            "volume_mm3": round(vol, 3),
            "surface_area_mm2": round(area, 3),
            "bbox_mm": {"x": round(xmax - xmin, 4), "y": round(ymax - ymin, 4), "z": round(zmax - zmin, 4)},
            "bounds_min": [round(xmin, 4), round(ymin, 4), round(zmin, 4)],
            "bounds_max": [round(xmax, 4), round(ymax, 4), round(zmax, 4)],
            "z_min": round(zmin, 4),
            "raw_boundbox_z": [round(raw_bb.ZMin, 4), round(raw_bb.ZMax, 4)],
            "solids": len(solids), "shells": len(getattr(shape, "Shells", []) or []),
            "faces": len(getattr(shape, "Faces", []) or []),
            "edges": len(getattr(shape, "Edges", []) or []),
            "vertices": len(verts),
            "center_of_mass": com,
        }
        report["metrics"]["dfm"] = _dfm_draft(shape)
        report["semantic_refs"] = semantic

        # 导出（路径由 Worker 分配，文件名不接受用户拼接）
        for out in ir.get("outputs", []):
            kind = out if isinstance(out, str) else out.get("type")
            fmt = {"step": "step_export", "stl": "stl_export", "glb": "glb_export"}.get(kind)
            if not fmt:
                report["errors"].append(f"CAD_OUTPUT_UNSUPPORTED: {kind}")
                continue
            path = os.path.join(out_dir, f"model.{kind}")
            try:
                if kind == "step":
                    shape.exportStep(path)
                elif kind == "stl":
                    shape.exportStl(path, 0.05)
                else:
                    import Mesh
                    Mesh.export([shape], path)
                report["outputs"][kind] = {"path": path, "bytes": os.path.getsize(path)}
            except Exception as exc:
                report["errors"].append(f"CAD_EXPORT_FAILED: {kind} -> {type(exc).__name__}: {exc}")

    except Exception as exc:
        report["errors"].append(f"CAD_IR_EXEC_FAILED: {type(exc).__name__}: {exc}")
        report["trace"] = traceback.format_exc(limit=6)
        _write(report, out_dir)
        return 3

    report["ok"] = not report["errors"]
    report["elapsed_ms"] = int(sum(f.get("elapsed_ms", 0) for f in report["features"]))
    _write(report, out_dir)
    return 0 if report["ok"] else 4


def _write(report, out_dir):
    report["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with open(os.path.join(out_dir, "cad_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print("__CAD_REPORT__" + json.dumps({"ok": report.get("ok", False),
                                         "metrics": report.get("metrics"),
                                         "errors": report.get("errors", [])}, ensure_ascii=False))


try:
    print("[cadir-runner] start ir=%s out=%s" % (os.environ.get("HD2_CAD_IR"), os.environ.get("HD2_CAD_OUT")), flush=True)
    _rc = main(sys.argv)
    print("[cadir-runner] done rc=%s" % _rc, flush=True)
except SystemExit:
    raise
except BaseException:
    traceback.print_exc()
