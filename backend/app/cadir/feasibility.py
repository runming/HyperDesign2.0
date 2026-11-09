# -*- coding: utf-8 -*-
"""设计空间可行性判定与自动修复（纯解析，不依赖几何内核）。

背景：M0 实测发现一个真实约束——外角半径 R 在「拔模 + 壁厚」联合作用下会失效：
    顶部内角半径 r_top = R − H·tan(d) − wall/cos(d)
若 r_top 过小，内腔无法做出等壁厚圆角，拐角壁厚会掉到远低于名义值（R=3 时约 0.44mm）。
2.0 的做法不是"报错了事"，而是：**判定不可行 → 给出最小改动建议 → 自动重建 → 复验**。

约束集（每条都对应可引用的工艺/几何依据）：
  C1 顶面内角半径      r_top = R − H·tan(d) − wall/cos(d) ≥ 0.2mm
  C2 顶面平台宽度      flat_top = (L − 2H·tan d) − 2(R − H·tan d) ≥ 2.0mm
  C3 名义壁厚下限      wall ≥ 2.4mm（企业注塑规范）
  C4 壁厚上限          wall ≤ 4.5mm（避免肥厚积料）
  C5 拔模角下限        draft ≥ 1.8°（企业注塑规范）
  C6 高厚比            H / wall ≤ 20（避免深腔抽芯困难）
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Dict, List

R_MIN = 0.2          # 顶面内角最小半径（可接受的最小圆角）
FLAT_MIN = 2.0       # 顶面最小平台
WALL_MIN = 2.4
WALL_MAX = 4.5
DRAFT_MIN = 1.8
SLENDER_MAX = 20.0


@dataclass
class HousingParams:
    length_mm: float
    width_mm: float
    height_mm: float
    wall_mm: float
    draft_deg: float
    corner_r_mm: float

    def copy(self, **kw) -> "HousingParams":
        d = asdict(self)
        d.update(kw)
        return HousingParams(**d)


def _constraint(name: str, required: str, actual: float, ok: bool, formula: str,
                hint: str = "") -> Dict[str, Any]:
    return {"name": name, "required": required, "actual": round(actual, 4), "ok": bool(ok),
            "formula": formula, "hint": hint}


def evaluate(p: HousingParams) -> Dict[str, Any]:
    """逐条判定，返回可直接展示的约束表与结论。"""
    tan_d = math.tan(math.radians(p.draft_deg))
    cos_d = math.cos(math.radians(p.draft_deg))
    r_top = p.corner_r_mm - p.height_mm * tan_d - p.wall_mm / cos_d
    flat_top = (p.length_mm - 2 * p.height_mm * tan_d) - 2 * (p.corner_r_mm - p.height_mm * tan_d)
    slender = p.height_mm / p.wall_mm if p.wall_mm else float("inf")

    r_required = p.height_mm * tan_d + p.wall_mm / cos_d + R_MIN      # 反解 C1
    flat_required_r = ((p.length_mm - 2 * p.height_mm * tan_d) - FLAT_MIN) / 2 + p.height_mm * tan_d

    cs = [
        _constraint("顶面内角半径", f"≥ {R_MIN} mm", r_top, r_top >= R_MIN,
                    "r_top = R − H·tan(d) − wall/cos(d)",
                    f"需 R ≥ {r_required:.2f} mm（当前 {p.corner_r_mm:.2f} mm）"),
        _constraint("顶面平台宽度", f"≥ {FLAT_MIN} mm", flat_top, flat_top >= FLAT_MIN,
                    "flat_top = (L − 2H·tan d) − 2(R − H·tan d)",
                    f"需 R ≤ {flat_required_r:.2f} mm 或增大 L"),
        _constraint("名义壁厚下限", f"≥ {WALL_MIN} mm", p.wall_mm, p.wall_mm >= WALL_MIN,
                    "企业注塑规范：跨度>150mm 件名义壁厚 2.4mm，严禁 2.0mm",
                    "把壁厚提到 2.4mm 及以上"),
        _constraint("壁厚上限", f"≤ {WALL_MAX} mm", p.wall_mm, p.wall_mm <= WALL_MAX,
                    ">4.5mm 为肥厚积料区（缩水纹风险）", "减小壁厚或改筋板结构"),
        _constraint("拔模角下限", f"≥ {DRAFT_MIN}°", p.draft_deg, p.draft_deg >= DRAFT_MIN,
                    "企业注塑规范：拔模斜度统一要求 ≥1.8°", "把拔模角提到 1.8° 及以上"),
        _constraint("高厚比", f"≤ {SLENDER_MAX:.0f}", slender, slender <= SLENDER_MAX,
                    "H/wall 过大时深腔抽芯困难", "降低高度或加厚壁"),
    ]
    ok = all(c["ok"] for c in cs)
    return {
        "feasible": ok,
        "params": asdict(p),
        "derived": {"r_top_mm": round(r_top, 4), "flat_top_mm": round(flat_top, 4),
                    "slenderness": round(slender, 3),
                    "draft_inset_mm": round(p.height_mm * tan_d, 4)},
        "constraints": cs,
        "violations": [c["name"] for c in cs if not c["ok"]],
    }


def suggest_repair(p: HousingParams, max_steps: int = 3) -> Dict[str, Any]:
    """
    给出**最小改动集**并返回修复后的参数与每一步理由。
    策略优先级：调圆角 → 调高度 → 调壁厚（优先动"造型自由度最大"的参数）。
    """
    steps: List[Dict[str, Any]] = []
    cur = p.copy()
    for _ in range(max_steps):
        rep = evaluate(cur)
        if rep["feasible"]:
            break
        viol = set(rep["violations"])
        if "顶面内角半径" in viol:
            tan_d = math.tan(math.radians(cur.draft_deg))
            cos_d = math.cos(math.radians(cur.draft_deg))
            need = cur.height_mm * tan_d + cur.wall_mm / cos_d + R_MIN
            need = math.ceil(need * 10) / 10.0                     # 向上取 0.1mm，便于加工
            if need <= 20.0 and need > cur.corner_r_mm:
                # 同时保证顶面平台仍够
                flat_r = ((cur.length_mm - 2 * cur.height_mm * tan_d) - FLAT_MIN) / 2 + cur.height_mm * tan_d
                target = min(need, math.floor(flat_r * 10) / 10.0)
                steps.append({"param": "corner_r_mm", "from": cur.corner_r_mm, "to": target,
                              "reason": f"顶面内角半径 {rep['derived']['r_top_mm']}mm < {R_MIN}mm；"
                                        f"按 R ≥ H·tan d + wall/cos d + {R_MIN} 反解得 {need:.2f}mm，"
                                        f"取 {target:.2f}mm（同时受顶面平台约束 ≤{flat_r:.2f}mm）"})
                cur = cur.copy(corner_r_mm=target)
                continue
            # 圆角到顶仍不行 → 降高度
            h_max = (cur.corner_r_mm - cur.wall_mm / cos_d - R_MIN) / tan_d if tan_d > 0 else cur.height_mm
            target_h = max(5.0, math.floor(h_max * 10) / 10.0)
            if target_h < cur.height_mm:
                steps.append({"param": "height_mm", "from": cur.height_mm, "to": target_h,
                              "reason": f"圆角已到上限，按 H ≤ (R − wall/cos d − {R_MIN}) / tan d 反解得 {h_max:.2f}mm"})
                cur = cur.copy(height_mm=target_h)
                continue
        if "名义壁厚下限" in viol:
            steps.append({"param": "wall_mm", "from": cur.wall_mm, "to": WALL_MIN,
                          "reason": "企业规范要求名义壁厚 ≥2.4mm（大跨距件）"})
            cur = cur.copy(wall_mm=WALL_MIN)
            continue
        if "拔模角下限" in viol:
            steps.append({"param": "draft_deg", "from": cur.draft_deg, "to": DRAFT_MIN,
                          "reason": "企业规范要求拔模斜度 ≥1.8°"})
            cur = cur.copy(draft_deg=DRAFT_MIN)
            continue
        if "壁厚上限" in viol:
            steps.append({"param": "wall_mm", "from": cur.wall_mm, "to": WALL_MAX,
                          "reason": "壁厚超过 4.5mm 属肥厚积料区，需降到上限"})
            cur = cur.copy(wall_mm=WALL_MAX)
            continue
        break   # 无法自动修复的约束（如高厚比），交给人工

    after = evaluate(cur)
    return {
        "repaired": after["feasible"],
        "before": evaluate(p),
        "after": after,
        "steps": steps,
        "changed_params": {s["param"]: {"from": s["from"], "to": s["to"]} for s in steps},
    }
