# -*- coding: utf-8 -*-
"""Harness 数据模型：规则、检查、裁决。

设计约束（对标 07-harness 规范并做差异化增强）：
- 不使用 eval / exec，不做任意表达式解析；只允许**受控算子集合**（见 engine.OPS）；
- 每条规则必须带 citation（工艺规范文档 + 条款原文），裁决必须可追溯到证据；
- 严重级别四值：info / warning / error / critical；error 与 critical 阻断；
- 聚合结论四值：passed / passed_with_warnings / failed / invalid；
- **输入缺失或无法计算的规则返回 invalid，绝不能按通过处理**。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

SEVERITIES = ("info", "warning", "error", "critical")
BLOCKING_SEVERITIES = ("error", "critical")
STAGES = ("input", "mesh", "dfm", "cad", "drawing", "delivery")

VERDICT_PASSED = "passed"
VERDICT_FAILED = "failed"
VERDICT_INVALID = "invalid"

AGG_PASSED = "passed"
AGG_WARN = "passed_with_warnings"
AGG_FAILED = "failed"
AGG_INVALID = "invalid"


@dataclass
class Operand:
    """算子操作数：指标路径 / 常量 / 参数引用。"""
    kind: str                      # metric | const | param
    path: Optional[str] = None      # kind=metric 时的点号路径，如 "cad.dfm.min_draft_deg"
    value: Any = None               # kind=const 时的字面量
    unit: Optional[str] = None

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Operand":
        if isinstance(d, (int, float, str, bool)):
            return Operand(kind="const", value=d)
        kind = d.get("kind") or ("metric" if "metric" in d else ("param" if "param" in d else "const"))
        return Operand(kind=kind,
                       path=d.get("metric") or d.get("param"),
                       value=d.get("const", d.get("value")),
                       unit=d.get("unit"))


@dataclass
class Check:
    """单个判定。op 必须在 engine.OPS 白名单内。"""
    op: str
    left: Optional[Operand] = None
    right: Optional[Operand] = None
    tolerance: float = 0.0          # near 用
    max_ratio: Optional[float] = None  # ratio_dev 用
    checks: List["Check"] = field(default_factory=list)  # all_of / any_of 用

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Check":
        return Check(
            op=d["op"],
            left=Operand.from_dict(d["left"]) if d.get("left") is not None else None,
            right=Operand.from_dict(d["right"]) if d.get("right") is not None else None,
            tolerance=float(d.get("tolerance", 0.0)),
            max_ratio=(float(d["max_ratio"]) if d.get("max_ratio") is not None else None),
            checks=[Check.from_dict(c) for c in d.get("checks", [])],
        )


@dataclass
class Rule:
    rule_id: str
    title: str
    severity: str
    stage: str
    check: Check
    message: str
    citation: Dict[str, Any] = field(default_factory=dict)
    suggested_action: Optional[str] = None
    blocking: Optional[bool] = None   # 未显式给出时由 severity 推导

    @property
    def is_blocking(self) -> bool:
        if self.blocking is not None:
            return self.blocking
        return self.severity in BLOCKING_SEVERITIES

    def validate(self) -> List[str]:
        errs = []
        if self.severity not in SEVERITIES:
            errs.append(f"{self.rule_id}: 非法 severity '{self.severity}'")
        if self.stage not in STAGES:
            errs.append(f"{self.rule_id}: 非法 stage '{self.stage}'")
        if not self.rule_id or "." not in self.rule_id:
            errs.append(f"{self.rule_id}: rule_id 建议使用 domain.subject 形式")
        return errs

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Rule":
        return Rule(
            rule_id=d["rule_id"],
            title=d.get("title", d["rule_id"]),
            severity=d.get("severity", "error"),
            stage=d.get("stage", "cad"),
            check=Check.from_dict(d["check"]),
            message=d.get("message", ""),
            citation=d.get("citation", {}),
            suggested_action=d.get("suggested_action"),
            blocking=d.get("blocking"),
        )


@dataclass
class RuleResult:
    rule_id: str
    title: str
    verdict: str
    severity: str
    blocking: bool
    message: str
    actual: Any = None
    limit: Any = None
    unit: Optional[str] = None
    citation: Dict[str, Any] = field(default_factory=dict)
    suggested_action: Optional[str] = None
    detail: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id, "title": self.title, "verdict": self.verdict,
            "severity": self.severity, "blocking": self.blocking, "message": self.message,
            "actual": self.actual, "limit": self.limit, "unit": self.unit,
            "citation": self.citation, "suggested_action": self.suggested_action,
            "detail": self.detail,
        }


@dataclass
class HarnessVerdict:
    pack_id: str
    pack_version: str
    stage: str
    verdict: str
    results: List[RuleResult]
    blocking_failures: List[str] = field(default_factory=list)
    invalid_rules: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pack_id": self.pack_id, "pack_version": self.pack_version, "stage": self.stage,
            "verdict": self.verdict,
            "blocking_failures": self.blocking_failures,
            "invalid_rules": self.invalid_rules,
            "warnings": self.warnings,
            "results": [r.to_dict() for r in self.results],
        }
