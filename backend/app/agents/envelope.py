# -*- coding: utf-8 -*-
"""Agent 输出信封与 Agent 定义（对标 05-agent-spec）。

核心纪律：
- Agent 是**有边界的决策单元**，不做数值计算、不做几何运算、不做求解；
- 输出必须通过信封校验，四值状态：completed / needs_input / needs_review / failed；
- 必须披露 assumptions / warnings / citations；
- 只能调用 allowed_skills / allowed_harnesses / allowed_tools 白名单内的能力；
- 无足够证据时必须给 needs_input 或 needs_review，不得伪造 completed。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

STATUSES = ("completed", "needs_input", "needs_review", "failed")
MIN_CONFIDENCE, MAX_CONFIDENCE = 0.0, 1.0


class EnvelopeError(Exception):
    """信封非法（Agent 输出不合格）。"""


@dataclass
class Citation:
    document: str
    clause: Optional[str] = None
    quote: Optional[str] = None
    url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in (("document", self.document), ("clause", self.clause),
                                  ("quote", self.quote), ("url", self.url)) if v}


@dataclass
class AgentEnvelope:
    status: str
    result: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    assumptions: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    citations: List[Citation] = field(default_factory=list)
    next_action: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status, "confidence": self.confidence,
            "assumptions": self.assumptions, "warnings": self.warnings,
            "citations": [c.to_dict() for c in self.citations],
            "result": self.result, "next_action": self.next_action,
        }

    @staticmethod
    def parse(payload: Dict[str, Any]) -> "AgentEnvelope":
        """校验并规范化 Agent 输出；不合格直接抛 EnvelopeError。"""
        if not isinstance(payload, dict):
            raise EnvelopeError("Agent 输出必须是 JSON 对象")
        status = payload.get("status")
        if status not in STATUSES:
            raise EnvelopeError(f"非法 status '{status}'（允许：{', '.join(STATUSES)}）")
        conf = payload.get("confidence", 0.0)
        if isinstance(conf, bool) or not isinstance(conf, (int, float)):
            raise EnvelopeError("confidence 必须是数值")
        if not (MIN_CONFIDENCE <= float(conf) <= MAX_CONFIDENCE):
            raise EnvelopeError(f"confidence 越界：{conf}")
        result = payload.get("result", {})
        if not isinstance(result, dict):
            raise EnvelopeError("result 必须是对象")
        if status == "completed" and not result:
            raise EnvelopeError("status=completed 但 result 为空：不允许空结论冒充完成")
        if status in ("needs_input", "needs_review") and not payload.get("next_action"):
            raise EnvelopeError(f"status={status} 必须给出 next_action（说明需要什么）")
        for key in ("assumptions", "warnings"):
            v = payload.get(key, [])
            if not isinstance(v, list):
                raise EnvelopeError(f"{key} 必须是数组")
        cites = []
        for c in payload.get("citations", []) or []:
            if isinstance(c, str):
                cites.append(Citation(document=c))
            elif isinstance(c, dict) and c.get("document"):
                cites.append(Citation(document=c["document"], clause=c.get("clause"),
                                      quote=c.get("quote"), url=c.get("url")))
            else:
                raise EnvelopeError("citations 项必须是字符串或含 document 的对象")
        return AgentEnvelope(status=status, result=result, confidence=float(conf),
                             assumptions=list(payload.get("assumptions", []) or []),
                             warnings=list(payload.get("warnings", []) or []),
                             citations=cites, next_action=payload.get("next_action"))


@dataclass
class AgentDefinition:
    key: str
    name: str
    version: str
    purpose: str
    not_responsible_for: List[str] = field(default_factory=list)
    input_schema: Optional[str] = None
    output_schema: Optional[str] = None
    allowed_skills: List[str] = field(default_factory=list)
    allowed_harnesses: List[str] = field(default_factory=list)
    allowed_tools: List[str] = field(default_factory=list)
    human_gate: Optional[str] = None
    max_iterations: int = 2
    timeout_s: int = 300

    def can_call_skill(self, skill_key: str) -> bool:
        for allowed in self.allowed_skills:
            if allowed == "*":
                return True
            if allowed.endswith(".*") and skill_key.startswith(allowed[:-1]):
                return True
            if allowed == skill_key:
                return True
        return False

    def assert_allowed(self, skill_key: str) -> None:
        if not self.can_call_skill(skill_key):
            raise EnvelopeError(
                f"Agent '{self.key}' 无权调用技能 '{skill_key}'（允许：{self.allowed_skills or '无'}）")


SUPERVISOR_FORBIDDEN = [
    "绕过人工审批",
    "修改 Harness 规则",
    "把失败的 CAE 结果标记为通过",
    "覆盖已审批的设计版本",
    "直接执行任意代码",
]
