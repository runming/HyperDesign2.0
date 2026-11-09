# -*- coding: utf-8 -*-
"""HyperDesign 2.0 —— 自包含有限元核心（仅依赖 numpy，无 Gmsh/CalculiX 也可离线跑 CAE）。

包含：
- Euler-Bernoulli 梁单元（Hermite 三次形函数），2 自由度/节点（挠度 w、转角 θ）
- 平面应力 CST 常应变三角形单元（Delaunay 无关：本文件只用结构化网格）

定位：这些求解器是**确定性技能**（Skill），不是 Agent；Agent 只能给出工况与网格参数，
求解与校核由本模块完成，结论必须带方法与误差对标。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np


# ======================================================================================
# 通用：稀疏/稠密求解（本规模用稠密即可，n<5000）
# ======================================================================================
def solve_dirichlet(K: np.ndarray, F: np.ndarray, fixed: Dict[int, float]) -> np.ndarray:
    """施加 Dirichlet 边界（fixed: dof -> 位移）后求解 K u = F。"""
    n = K.shape[0]
    u = np.zeros(n)
    free = np.ones(n, dtype=bool)
    for dof, val in fixed.items():
        u[dof] = val
        free[dof] = False
    if not free.any():
        return u
    Kf = K[np.ix_(free, free)]
    rhs = F[free] - K[np.ix_(free, list(fixed.keys()))] @ np.array(list(fixed.values())) if fixed else F[free]
    u[free] = np.linalg.solve(Kf, rhs)
    return u


# ======================================================================================
# 梁：Euler-Bernoulli（Hermite 单元）
# ======================================================================================
@dataclass
class BeamInput:
    length_mm: float
    width_mm: float
    height_mm: float
    young_gpa: float = 206.0
    load_n: float = 0.0                 # 端部集中载荷
    distributed_n_per_mm: float = 0.0   # 均布载荷
    elements: int = 40
    load_type: str = "tip"              # tip | distributed

    def validate(self) -> None:
        if min(self.length_mm, self.width_mm, self.height_mm) <= 0:
            raise ValueError("梁尺寸必须为正")
        if self.elements < 2 or self.elements > 2000:
            raise ValueError("elements 应在 [2, 2000]")
        if self.load_type not in ("tip", "distributed"):
            raise ValueError("load_type 只能是 tip / distributed")


def beam_solve(inp: BeamInput) -> Dict[str, object]:
    """悬臂梁（固定端 x=0）有限元求解，返回挠度/弯矩/应力并与解析解对标。"""
    inp.validate()
    L, b, h = inp.length_mm, inp.width_mm, inp.height_mm
    E = inp.young_gpa * 1000.0            # MPa = N/mm²
    I = b * h ** 3 / 12.0                 # mm⁴
    EI = E * I
    n_elem = inp.elements
    le = L / n_elem
    ndof = 2 * (n_elem + 1)

    def k_elem(le: float) -> np.ndarray:
        c = EI / le ** 3
        return c * np.array([
            [12, 6 * le, -12, 6 * le],
            [6 * le, 4 * le ** 2, -6 * le, 2 * le ** 2],
            [-12, -6 * le, 12, -6 * le],
            [6 * le, 2 * le ** 2, -6 * le, 4 * le ** 2],
        ], dtype=float)

    K = np.zeros((ndof, ndof))
    F = np.zeros(ndof)
    ke = k_elem(le)
    for e in range(n_elem):
        dofs = [2 * e, 2 * e + 1, 2 * e + 2, 2 * e + 3]
        K[np.ix_(dofs, dofs)] += ke
        if inp.load_type == "distributed" and inp.distributed_n_per_mm:
            q = inp.distributed_n_per_mm
            F[dofs] += np.array([q * le / 2, q * le ** 2 / 12, q * le / 2, -q * le ** 2 / 12])
    if inp.load_type == "tip":
        F[2 * n_elem] += inp.load_n

    u = solve_dirichlet(K, F, {0: 0.0, 1: 0.0})

    # 弯矩：由单元节点曲率反算，取绝对值最大
    Mmax = 0.0
    for e in range(n_elem):
        dofs = [2 * e, 2 * e + 1, 2 * e + 2, 2 * e + 3]
        ue = u[dofs]
        # Hermite 二阶导在单元两端
        d2N = np.array([[6 / le ** 2, 4 / le, -6 / le ** 2, 2 / le],
                        [-6 / le ** 2, -2 / le, 6 / le ** 2, -4 / le]])
        M = EI * (d2N @ ue)
        Mmax = max(Mmax, float(np.max(np.abs(M))))

    tip = float(u[2 * n_elem])
    sigma = Mmax * (h / 2.0) / I if I > 0 else float("inf")

    # 解析解对标
    if inp.load_type == "tip":
        w_analytic = inp.load_n * L ** 3 / (3 * EI) if EI else 0.0
        M_analytic = inp.load_n * L
    else:
        q = inp.distributed_n_per_mm
        w_analytic = q * L ** 4 / (8 * EI) if EI else 0.0
        M_analytic = q * L ** 2 / 2

    err_w = abs(tip - w_analytic) / w_analytic * 100 if w_analytic else 0.0
    err_M = abs(Mmax - M_analytic) / M_analytic * 100 if M_analytic else 0.0
    return {
        "method": "Euler-Bernoulli 梁单元（Hermite 三次）/ 40+ 单元",
        "tipped_deflection_mm": round(tip, 5),
        "analytic_deflection_mm": round(w_analytic, 5),
        "deflection_error_pct": round(err_w, 4),
        "max_bending_moment_nmm": round(Mmax, 2),
        "analytic_moment_nmm": round(M_analytic, 2),
        "moment_error_pct": round(err_M, 4),
        "max_bending_stress_mpa": round(sigma, 3),
        "section_modulus_mm3": round(b * h ** 2 / 6, 3),
        "inertia_mm4": round(I, 3),
        "elements": n_elem,
        "passed": bool(err_w < 0.5 and err_M < 0.5),
    }


# ======================================================================================
# 平面应力：CST 三角形（带孔板，位移边界给均匀应变远场）
# ======================================================================================
@dataclass
class HolePlateInput:
    hole_radius_mm: float
    outer_radius_mm: float
    thickness_mm: float
    young_gpa: float = 2.4          # PC+ABS 约 2.3~2.5 GPa
    poisson: float = 0.39
    strain: float = 1.0e-3          # 远场均匀应变
    sectors: int = 32
    rings: int = 8

    def validate(self) -> None:
        if self.hole_radius_mm <= 0 or self.outer_radius_mm <= self.hole_radius_mm:
            raise ValueError("外半径必须大于孔半径且为正")
        if not (0.0 < self.poisson < 0.5):
            raise ValueError("泊松比应在 (0,0.5)")
        if self.sectors < 8 or self.rings < 2:
            raise ValueError("网格过粗：sectors≥8, rings≥2")


def _cst_D(E: float, nu: float) -> np.ndarray:
    return E / (1 - nu ** 2) * np.array([[1, nu, 0], [nu, 1, 0], [0, 0, (1 - nu) / 2]])


def _cst_B(x: np.ndarray, y: np.ndarray) -> Tuple[np.ndarray, float]:
    """x,y 为三个节点坐标（逆时针）。返回 B 与面积。"""
    x1, x2, x3 = x
    y1, y2, y3 = y
    A = 0.5 * ((x2 - x1) * (y3 - y1) - (x3 - x1) * (y2 - y1))
    if A <= 0:
        A = abs(A)
        x2, x3 = x3, x2
        y2, y3 = y3, y2
    b1, b2, b3 = y2 - y3, y3 - y1, y1 - y2
    c1, c2, c3 = x3 - x2, x1 - x3, x2 - x1
    B = np.array([[b1, 0, b2, 0, b3, 0],
                  [0, c1, 0, c2, 0, c3],
                  [c1, b1, c2, b2, c3, b3]], dtype=float) / (2 * A)
    return B, A


def hole_plate_solve(inp: HolePlateInput) -> Dict[str, object]:
    """
    带中心孔板在单轴拉伸下的应力集中系数（Kirsch 解 Kt=3）。

    边界处理：外圆环上施加**单轴拉伸等效面力**（σ∞ 沿 x），只约束刚体位移。
    用位移边界把整圈钉死会过度约束、显著低估孔边应力（实测仅 1.26），因此改面力。
    """
    inp.validate()
    E = inp.young_gpa * 1000.0
    nu = inp.poisson
    a, b = inp.hole_radius_mm, inp.outer_radius_mm
    ns, nr = inp.sectors, inp.rings
    ratio = b / a
    sig_inf = E * inp.strain
    radii = [a * (ratio ** (i / nr)) for i in range(nr + 1)]
    nodes: List[Tuple[float, float]] = []
    idx = {}
    for i, r in enumerate(radii):
        for j in range(ns):
            th = 2 * math.pi * j / ns
            idx[(i, j)] = len(nodes)
            nodes.append((r * math.cos(th), r * math.sin(th)))

    tris: List[Tuple[int, int, int]] = []
    for i in range(nr):
        for j in range(ns):
            j2 = (j + 1) % ns
            n1, n2 = idx[(i, j)], idx[(i, j2)]
            n3, n4 = idx[(i + 1, j2)], idx[(i + 1, j)]
            tris.append((n1, n2, n3))
            tris.append((n1, n3, n4))

    nn = len(nodes)
    K = np.zeros((2 * nn, 2 * nn))
    D = _cst_D(E, nu)
    t = inp.thickness_mm
    for (n1, n2, n3) in tris:
        xs = np.array([nodes[n1][0], nodes[n2][0], nodes[n3][0]])
        ys = np.array([nodes[n1][1], nodes[n2][1], nodes[n3][1]])
        B, A = _cst_B(xs, ys)
        Ke = t * A * (B.T @ D @ B)
        dofs = [2 * n1, 2 * n1 + 1, 2 * n2, 2 * n2 + 1, 2 * n3, 2 * n3 + 1]
        K[np.ix_(dofs, dofs)] += Ke

    # 面力：外圆环每条边界边上的等效节点力（traction = σ∞ · n_x）
    F = np.zeros(2 * nn)
    for j in range(ns):
        j2 = (j + 1) % ns
        p1, p2 = np.array(nodes[idx[(nr, j)]]), np.array(nodes[idx[(nr, j2)]])
        Le = float(np.linalg.norm(p2 - p1))
        nx = float((p1[1] + p2[1]) / 2.0) / b      # 单位外法向 x 分量
        fx = sig_inf * t * Le * nx / 2.0
        F[2 * idx[(nr, j)]] += fx
        F[2 * idx[(nr, j2)]] += fx

    # 仅约束刚体位移：外环上两点分别固定 x / y
    fixed = {2 * idx[(nr, 0)]: 0.0, 2 * idx[(nr, ns // 4)] + 1: 0.0}
    u = solve_dirichlet(K, F, fixed)

    # 单元应力（取孔边一层单元的环向应力最大值）
    sig_max_hoop, sig_max_xx = 0.0, 0.0
    for (n1, n2, n3) in tris:
        xs = np.array([nodes[n1][0], nodes[n2][0], nodes[n3][0]])
        ys = np.array([nodes[n1][1], nodes[n2][1], nodes[n3][1]])
        B, A = _cst_B(xs, ys)
        ue = np.array([u[2 * n1], u[2 * n1 + 1], u[2 * n2], u[2 * n2 + 1], u[2 * n3], u[2 * n3 + 1]])
        sxx, syy, txy = D @ (B @ ue)
        sig_max_xx = max(sig_max_xx, sxx)
        cx, cy = xs.mean(), ys.mean()
        r = math.hypot(cx, cy)
        if r < a * 1.3:                       # 孔边第一层
            th = math.atan2(cy, cx)
            sth = sxx * math.sin(th) ** 2 + syy * math.cos(th) ** 2 - 2 * txy * math.sin(th) * math.cos(th)
            sig_max_hoop = max(sig_max_hoop, sth)

    kt = sig_max_hoop / sig_inf if sig_inf else 0.0
    return {
        "method": "CST 常应变三角形 / 结构化极坐标网格 / 外环面力单轴拉伸",
        "mesh": {"sectors": ns, "rings": nr, "elements": len(tris), "nodes": nn,
                 "b_over_a": round(ratio, 2)},
        "far_field_stress_mpa": round(sig_inf, 4),
        "sigma_max_hoop_mpa": round(sig_max_hoop, 4),
        "sigma_max_xx_mpa": round(sig_max_xx, 4),
        "stress_concentration_kt": round(kt, 3),
        "analytic_kt": 3.0,
        "kt_error_pct": round(abs(kt - 3.0) / 3.0 * 100, 2),
        "passed": bool(2.2 <= kt <= 3.8),
        "note": "CST 常应变单元偏刚，孔边应力略低于理论；加密网格 Kt 应单调上升逼近 3.0",
    }
