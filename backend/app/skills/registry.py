# -*- coding: utf-8 -*-
"""Skill Registry：版本化、可枚举、带输入校验的确定性技能。

纪律：
- 技能必须声明 key@version、输入必填字段、幂等性与超时；
- Agent 只能调用自己被允许的技能（见 agents.envelope.AgentDefinition）；
- 技能是**确定性执行体**，不允许在里面调用 LLM 自由发挥；
- 失败返回结构化错误码，不得用自然语言伪造成功。
"""
from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

SKILL_NOT_FOUND = "SKILL_NOT_FOUND"
SKILL_INPUT_INVALID = "SKILL_INPUT_INVALID"
SKILL_FAILED = "SKILL_FAILED"
SKILL_TIMEOUT = "SKILL_TIMEOUT"


class SkillError(Exception):
    def __init__(self, code: str, message: str, detail: Optional[str] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail

    def to_dict(self) -> Dict[str, Any]:
        return {"code": self.code, "message": self.message, "detail": self.detail}


@dataclass
class SkillResult:
    key: str
    version: str
    ok: bool
    output: Dict[str, Any] = field(default_factory=dict)
    error: Optional[Dict[str, Any]] = None
    elapsed_ms: int = 0


@dataclass
class Skill:
    key: str
    version: str
    description: str
    handler: Callable[[Dict[str, Any]], Dict[str, Any]]
    required: List[str] = field(default_factory=list)
    optional: List[str] = field(default_factory=list)
    deterministic: bool = True
    idempotent: bool = True
    timeout_s: float = 120.0
    tags: List[str] = field(default_factory=list)

    def validate_input(self, payload: Dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            raise SkillError(SKILL_INPUT_INVALID, "输入必须是对象")
        missing = [k for k in self.required if k not in payload]
        if missing:
            raise SkillError(SKILL_INPUT_INVALID, f"缺少必填字段：{', '.join(missing)}")
        unknown = [k for k in payload if k not in self.required and k not in self.optional]
        if unknown:
            raise SkillError(SKILL_INPUT_INVALID, f"出现未声明字段：{', '.join(unknown)}")


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: Dict[str, Dict[str, Skill]] = {}

    def register(self, skill: Skill) -> None:
        self._skills.setdefault(skill.key, {})[skill.version] = skill

    def list(self) -> List[Dict[str, Any]]:
        out = []
        for key, versions in sorted(self._skills.items()):
            for ver, s in sorted(versions.items()):
                out.append({"key": key, "version": ver, "description": s.description,
                            "deterministic": s.deterministic, "idempotent": s.idempotent,
                            "required": s.required, "tags": s.tags})
        return out

    def resolve(self, key: str, version: Optional[str] = None) -> Skill:
        versions = self._skills.get(key)
        if not versions:
            raise SkillError(SKILL_NOT_FOUND, f"未注册的技能 '{key}'")
        if version in (None, "", "*", "latest"):
            return versions[sorted(versions)[-1]]
        if version in versions:
            return versions[version]
        # 支持 "1.x" 主版本匹配
        if version.endswith(".x"):
            major = version[:-2]
            cands = [v for v in versions if v.split(".")[0] == major]
            if cands:
                return versions[sorted(cands)[-1]]
        raise SkillError(SKILL_NOT_FOUND, f"技能 '{key}' 无版本 '{version}'（已有：{sorted(versions)}）")

    def call(self, key: str, payload: Optional[Dict[str, Any]] = None,
             version: Optional[str] = None) -> SkillResult:
        payload = payload or {}
        t0 = time.time()
        try:
            skill = self.resolve(key, version)
            skill.validate_input(payload)
            out = skill.handler(dict(payload))
            if not isinstance(out, dict):
                raise SkillError(SKILL_FAILED, "技能返回值必须是对象")
            # 通用纪律：技能若显式声明 ok=false，即视为失败（不得静默成功）
            if out.get("ok") is False:
                inner = out.get("report", {}).get("errors") if isinstance(out.get("report"), dict) else None
                raise SkillError(SKILL_FAILED,
                                 f"技能 '{skill.key}' 返回 ok=false" + (f"：{inner}" if inner else ""))
            return SkillResult(key=skill.key, version=skill.version, ok=True, output=out,
                               elapsed_ms=int((time.time() - t0) * 1000))
        except SkillError as exc:
            return SkillResult(key=key, version=version or "*", ok=False,
                               error=exc.to_dict(), elapsed_ms=int((time.time() - t0) * 1000))
        except Exception as exc:  # 未预期异常也要结构化，不能吞掉
            return SkillResult(key=key, version=version or "*", ok=False,
                               error={"code": SKILL_FAILED, "message": f"{type(exc).__name__}: {exc}",
                                      "detail": traceback.format_exc(limit=3)},
                               elapsed_ms=int((time.time() - t0) * 1000))


# ----------------------------------------------------------------------------------
# 内置技能
# ----------------------------------------------------------------------------------
def _skill_cad_ir_build(payload: Dict[str, Any]) -> Dict[str, Any]:
    """调用固定 CAD Worker（runner_freecad.py）执行 CAD-IR，返回报告与产物路径。"""
    import json
    import os
    import subprocess
    import tempfile
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    runner = root / "backend" / "app" / "cadir" / "runner_freecad.py"
    freecad = os.environ.get("HD_FREECAD_CMD") or \
        r"C:\Users\omegahyper\AppData\Local\Programs\FreeCAD 1.1\bin\freecadcmd.exe"
    ir = payload["ir"]
    out_dir = payload.get("out_dir") or tempfile.mkdtemp(prefix="hd2_skill_")
    ir_path = Path(out_dir) / "ir.json"
    ir_path.parent.mkdir(parents=True, exist_ok=True)
    ir_path.write_text(json.dumps(ir, ensure_ascii=False), encoding="utf-8")
    env = dict(os.environ, HD2_CAD_IR=str(ir_path), HD2_CAD_OUT=str(out_dir))
    proc = subprocess.run([freecad, str(runner)], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, timeout=300)
    report_path = Path(out_dir) / "cad_report.json"
    if not report_path.exists():
        raise SkillError(SKILL_FAILED, "CAD Worker 未产出报告",
                         detail=(proc.stderr or proc.stdout or "")[-800:])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return {"ok": bool(report.get("ok")), "report": report, "out_dir": str(out_dir)}


def _skill_harness_evaluate(payload: Dict[str, Any]) -> Dict[str, Any]:
    from pathlib import Path

    from ..harness.engine import RulePack, evaluate
    pack_path = Path(payload["pack_path"])
    if not pack_path.is_absolute():
        root = Path(__file__).resolve().parents[3]      # D:\hyperdesign2
        pack_path = root / pack_path
    if not pack_path.exists():
        raise SkillError(SKILL_INPUT_INVALID, f"规则包不存在：{pack_path}")
    pack = RulePack.load(pack_path)
    verdict = evaluate(pack, payload["context"])
    return verdict.to_dict()


def _skill_calc_shaft_strength(payload: Dict[str, Any]) -> Dict[str, Any]:
    """轴静强度与刚度（确定性公式，非 LLM）。"""
    import math
    T = float(payload["torque_nm"])
    M = float(payload["bending_moment_nm"])
    d = float(payload["diameter_mm"])
    sy = float(payload.get("yield_mpa", 355.0))
    L = float(payload.get("span_mm", 200.0))
    E = float(payload.get("young_gpa", 206.0)) * 1000.0
    required = float(payload.get("required_safety", 1.5))
    if d <= 0 or L <= 0:
        raise SkillError(SKILL_INPUT_INVALID, "diameter/span 必须为正")
    W = math.pi * d ** 3 / 32.0                       # 抗弯截面系数 mm³
    Ip = math.pi * d ** 4 / 32.0                      # 极惯性矩 mm⁴
    sigma = M * 1000.0 / W                            # 弯曲应力 MPa (N·mm / mm³)
    tau = T * 1000.0 * (d / 2.0) / Ip                 # 扭转切应力 MPa
    sigma_eq = math.sqrt(sigma ** 2 + 3.0 * tau ** 2)  # von Mises
    n = sy / sigma_eq if sigma_eq > 0 else float("inf")
    I = math.pi * d ** 4 / 64.0
    deflection = (M * 1000.0) * (L ** 2) / (8.0 * E * I) if I > 0 else float("inf")
    return {
        "sigma_bending_mpa": round(sigma, 3),
        "tau_torsion_mpa": round(tau, 3),
        "sigma_von_mises_mpa": round(sigma_eq, 3),
        "safety_factor": round(n, 3),
        "required_safety": required,
        "passed": bool(n >= required),
        "deflection_mm": round(deflection, 4),
        "method": "GB/T 3480 简化：von Mises 等效应力 + 简支梁挠度",
        "assumptions": ["圆截面、无键槽削弱", "同直径简支梁等效模型"],
    }


def _skill_cae_beam(payload: Dict[str, Any]) -> Dict[str, Any]:
    from ..cae.fem import BeamInput, beam_solve
    out = beam_solve(BeamInput(**payload))
    out["ok"] = bool(out.get("passed"))
    return out


def _skill_cae_hole_plate(payload: Dict[str, Any]) -> Dict[str, Any]:
    from ..cae.fem import HolePlateInput, hole_plate_solve
    out = hole_plate_solve(HolePlateInput(**payload))
    out["ok"] = bool(out.get("passed"))
    return out


def _skill_kb_search(payload: Dict[str, Any]) -> Dict[str, Any]:
    from ..kb.service import kb_search
    out = kb_search(payload)
    # 无证据时返回 ok=true 但 found=false —— 调用方（Agent）据此输出 needs_input
    return out


def build_default_registry() -> SkillRegistry:
    reg = SkillRegistry()
    reg.register(Skill(key="cad.ir.build", version="1.0.0",
                       description="执行 CAD-IR（受控解释器 + FreeCAD/OCCT），返回 B-Rep 几何元数据与产物",
                       handler=_skill_cad_ir_build, required=["ir"], optional=["out_dir"],
                       tags=["cad", "occt"]))
    reg.register(Skill(key="harness.evaluate", version="1.0.0",
                       description="对给定上下文执行 Harness 规则包，返回四值裁决与逐条证据",
                       handler=_skill_harness_evaluate, required=["pack_path", "context"],
                       tags=["harness"]))
    reg.register(Skill(key="calc.shaft.strength", version="1.0.0",
                       description="轴静强度（von Mises）与刚度（挠度）确定性计算",
                       handler=_skill_calc_shaft_strength,
                       required=["torque_nm", "bending_moment_nm", "diameter_mm"],
                       optional=["yield_mpa", "span_mm", "young_gpa", "required_safety"],
                       tags=["calculation"]))
    reg.register(Skill(key="cae.beam.solve", version="1.0.0",
                       description="悬臂梁有限元（Hermite 单元），输出挠度/弯矩/应力并与解析解对标",
                       handler=_skill_cae_beam,
                       required=["length_mm", "width_mm", "height_mm"],
                       optional=["young_gpa", "load_n", "distributed_n_per_mm",
                                 "elements", "load_type"],
                       tags=["cae", "fem"]))
    reg.register(Skill(key="cae.hole.plate", version="1.0.0",
                       description="带孔板平面应力有限元（CST），输出孔边应力集中系数并与 Kirsch 解对标",
                       handler=_skill_cae_hole_plate,
                       required=["hole_radius_mm", "outer_radius_mm", "thickness_mm"],
                       optional=["young_gpa", "poisson", "strain", "sectors", "rings"],
                       tags=["cae", "fem"]))
    reg.register(Skill(key="kb.search", version="1.0.0",
                       description="私有工艺知识库混合检索（BM25+向量+RRF），带引用溯源与 RBAC 过滤",
                       handler=_skill_kb_search, required=["query"],
                       optional=["role", "top_k"], tags=["knowledge", "rag"]))
    return reg
