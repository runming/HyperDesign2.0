# -*- coding: utf-8 -*-
"""
工程证据 → 自动修复闭环（GeomVerity 式 Self-Correction）。

思路：准入规则给出的结构化证据（哪条规则、实测多少、限值多少）直接映射为**参数补丁**，
补丁再交回几何内核重建，重建后重新裁决；最多修复 N 轮，修不好就如实回报，绝不"为了让通过而通过"。

可修复的问题（有明确几何因果）：
- 实体数 > 1（立柱与壳体断开）      → POST_H = H − WALL（立柱顶到内顶面才融合）
- 拔模角 < 规范下限                 → DRAFT_DEG = 下限
- 壁厚 p10 低于下限（薄壁）          → WALL = 下限（并同步 POST_H）
- 包络超差但体积正常（尺寸漂移）      → 以实测包络反推参数（仅当偏差 < 5%）

不可修复（如实回报，交人工）：
- 包络偏差 > 5%（模型本身错）
- 非水密 / 拓扑非法
- 体积异常（漏特征）
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[3]
RUNNER = ROOT / "backend" / "app" / "cadir" / "runner_freecad.py"
CAD_PACK = ROOT / "backend" / "app" / "harness" / "rules" / "housing_cad.v1.json"
FREECAD = os.environ.get("HD_FREECAD_CMD") or \
    r"C:\Users\omegahyper\AppData\Local\Programs\FreeCAD 1.1\bin\freecadcmd.exe"


@dataclass
class RepairAction:
    param: str
    before: float
    after: float
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {"param": self.param, "before": self.before, "after": self.after,
                "reason": self.reason}


def _set(params: Dict[str, float], key: str, val: float) -> None:
    params[key] = float(val)


def precheck(ir: Dict[str, Any]) -> List[RepairAction]:
    """构建前的「声明参数」预检：壁厚/拔模/高厚比。这些不依赖实测几何，但同样是硬约束。"""
    p = ir.get("parameters", {})
    acts: List[RepairAction] = []
    wall = float(p.get("WALL", 0))
    draft = float(p.get("DRAFT_DEG", 0))
    H = float(p.get("HEIGHT_Z", 0))
    if 0 < wall < 2.4:
        acts.append(RepairAction("WALL", wall, 2.4, "声明壁厚低于企业规范下限 2.4mm"))
        wall = 2.4
    if 0 < draft < 1.8:
        acts.append(RepairAction("DRAFT_DEG", draft, 1.8, "声明拔模低于规范下限 1.8°"))
    if wall and H and H / wall > 20.0:
        need = round(math.ceil(H / 20.0 * 10) / 10.0, 1)
        if need > wall:
            acts.append(RepairAction("WALL", wall, need,
                                     f"高厚比 {H}/{wall} 超过 20，壁厚抬到 {need}mm"))
    return acts


def propose(ir: Dict[str, Any], metrics: Dict[str, Any],
            failed_rules: List[str]) -> List[RepairAction]:
    """依据失败规则集合给出候选修复（按因果优先级排序）。"""
    p = ir.get("parameters", {})
    acts: List[RepairAction] = []
    H, wall = float(p.get("HEIGHT_Z", 0)), float(p.get("WALL", 0))

    if any(r in failed_rules for r in ("cad.solid.single",)) and H and wall:
        cur = float(p.get("POST_H", 0))
        target = round(H - wall, 1)
        if abs(cur - target) > 1e-6:
            acts.append(RepairAction("POST_H", cur, target,
                                     f"实体数 {metrics.get('solids')}：立柱未顶到内顶面，"
                                     f"按 H − WALL = {target}mm 重算"))

    if "cad.draft.min" in failed_rules:
        cur = float(p.get("DRAFT_DEG", 0))
        floor = 1.8
        if cur < floor:
            acts.append(RepairAction("DRAFT_DEG", cur, floor,
                                     f"拔模 {cur}° 低于规范下限 {floor}°，直接抬到下限"))

    if "dfm.wall.p10" in failed_rules:
        cur = float(p.get("WALL", 0))
        floor = 2.4
        if cur < floor:
            acts.append(RepairAction("WALL", cur, floor,
                                     f"壁厚 {cur}mm 低于 2.4mm 下限，抬到下限并同步立柱高度"))

    return acts


def _build(ir: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], str]:
    tmp = Path(tempfile.mkdtemp(prefix="hd_repair_"))
    irp = tmp / "ir.json"
    irp.write_text(json.dumps(ir, ensure_ascii=False), encoding="utf-8")
    env = dict(os.environ, HD2_CAD_IR=str(irp), HD2_CAD_OUT=str(tmp))
    subprocess.run([FREECAD, str(RUNNER)], capture_output=True, text=True,
                   encoding="utf-8", errors="replace", env=env, timeout=300)
    rep_path = tmp / "cad_report.json"
    if not rep_path.exists():
        return False, {}, "内核未产出报告"
    rep = json.loads(rep_path.read_text(encoding="utf-8"))
    if not rep.get("ok"):
        return False, {}, "; ".join(rep.get("errors", []))[:260]
    return True, rep.get("metrics") or {}, ""


def evaluate_cad(ir: Dict[str, Any], metrics: Dict[str, Any]) -> Tuple[str, List[str]]:
    from ..harness.engine import RulePack, evaluate
    p = ir["parameters"]
    pack = RulePack.load(CAD_PACK)
    target = {"bbox_mm": {"x": p["LENGTH_X"], "y": p["WIDTH_Y"], "z": p["HEIGHT_Z"]},
              "tolerance_mm": 1.5}
    process = {"min_wall_mm": 2.4, "rib_max_mm": 1.44, "min_draft_deg": 1.8,
               "max_bulk_wall_mm": 4.5, "pc_abs_yield_mpa": 50.0,
               "max_allowable_stress_mpa": 25.0}
    v = evaluate(pack, {"cad": metrics, "target": target, "process": process, "params": {}})
    return v.verdict, list(v.blocking_failures)


def auto_repair(ir: Dict[str, Any], max_rounds: int = 2) -> Dict[str, Any]:
    """执行「参数预检 → 构建 → 裁决 → 证据驱动修复」循环，返回完整证据链。"""
    import math
    work = copy.deepcopy(ir)
    attempts: List[Dict[str, Any]] = []

    # 0) 声明参数预检（不依赖内核）
    pre = precheck(work)
    applied_pre = []
    for a in pre:
        _set(work["parameters"], a.param, a.after)
        applied_pre.append(a)
        if a.param == "WALL" and "HEIGHT_Z" in work["parameters"]:
            work["parameters"]["POST_H"] = round(float(work["parameters"]["HEIGHT_Z"]) - a.after, 1)
    if applied_pre:
        attempts.append({"round": 0, "verdict": "precheck", "failed": [], "metrics": {},
                         "error": "", "actions": [a.to_dict() for a in applied_pre]})

    ok, metrics, err = _build(work)
    verdict, failed = (evaluate_cad(work, metrics) if ok else ("build_failed", []))
    attempts.append({"round": 1 if applied_pre else 0, "verdict": verdict, "failed": failed,
                     "metrics": {k: metrics.get(k) for k in ("solids", "volume_mm3", "bbox_mm")}
                     if ok else {}, "error": err,
                     "actions": [a.to_dict() for a in applied_pre]})
    if verdict == "passed":
        return {"ok": True, "rounds": 0, "attempts": attempts, "ir": work}

    for r in range(1, max_rounds + 1):
        acts = propose(work, metrics, failed)
        if not acts:
            break
        applied = []
        for a in acts:
            _set(work["parameters"], a.param, a.after)
            applied.append(a)
            if a.param == "WALL" and "HEIGHT_Z" in work["parameters"]:
                # 壁厚变化会改变立柱高度
                new_h = round(float(work["parameters"]["HEIGHT_Z"]) - a.after, 1)
                work["parameters"]["POST_H"] = new_h
        ok, metrics, err = _build(work)
        verdict, failed = (evaluate_cad(work, metrics) if ok else ("build_failed", []))
        attempts.append({"round": r, "verdict": verdict, "failed": failed,
                         "metrics": {k: metrics.get(k) for k in ("solids", "volume_mm3", "bbox_mm")}
                         if ok else {}, "error": err, "actions": [a.to_dict() for a in applied]})
        if verdict == "passed":
            return {"ok": True, "rounds": r, "attempts": attempts, "ir": work}

    return {"ok": False, "rounds": len(attempts) - 1, "attempts": attempts, "ir": work}
