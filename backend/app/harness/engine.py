# -*- coding: utf-8 -*-
"""Harness 规则引擎：受控算子求值 + 裁决聚合。

安全边界：**不使用 eval/exec**。规则只能由受控算子（OPS）组合而成，
任何未知算子直接抛 HarnessConfigError —— 规则不可被用来执行任意代码。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .models import (AGG_FAILED, AGG_INVALID, AGG_PASSED, AGG_WARN, Check, HarnessVerdict,
                     Operand, Rule, RuleResult, VERDICT_FAILED, VERDICT_INVALID, VERDICT_PASSED)

RULES_DIR = Path(__file__).resolve().parent / "rules"
_MISSING = object()


class HarnessConfigError(Exception):
    """规则包本身非法（不是设计不合格）。"""


@dataclass
class RulePack:
    pack_id: str
    version: str
    stage: str
    part_type: str
    rules: List[Rule] = field(default_factory=list)
    source: Optional[str] = None

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "RulePack":
        pack = RulePack(pack_id=d["pack_id"], version=d.get("version", "1.0.0"),
                        stage=d.get("stage", "cad"), part_type=d.get("part_type", "*"),
                        source=d.get("source"))
        errs = []
        for rd in d.get("rules", []):
            r = Rule.from_dict(rd)
            errs.extend(r.validate())
            errs.extend(_validate_ops(r.check, r.rule_id))
            pack.rules.append(r)
        if errs:
            raise HarnessConfigError("; ".join(errs))
        if not pack.rules:
            raise HarnessConfigError(f"{pack.pack_id}: 规则包为空")
        return pack

    @staticmethod
    def load(path: str | Path) -> "RulePack":
        return RulePack.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


# ----------------------------------------------------------------------------------
# 上下文取值
# ----------------------------------------------------------------------------------
def _resolve(op: Operand, ctx: Dict[str, Any]) -> Tuple[Any, bool]:
    """返回 (值, 是否找到)。"""
    if op.kind == "const":
        return op.value, True
    if op.kind == "param":
        params = ctx.get("params") or {}
        if op.path in params:
            return params[op.path], True
        return None, False
    if op.kind == "metric":
        cur: Any = ctx
        for part in (op.path or "").split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return None, False
        return cur, cur is not None
    raise HarnessConfigError(f"未知操作数类型 '{op.kind}'")


def _num(v: Any) -> Optional[float]:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ----------------------------------------------------------------------------------
# 受控算子
# ----------------------------------------------------------------------------------
def _cmp(op_name: str, fn) -> "callable":
    def run(check: Check, ctx):
        a, ok_a = _resolve(check.left, ctx)
        b, ok_b = _resolve(check.right, ctx)
        if not (ok_a and ok_b):
            return VERDICT_INVALID, a, b, f"操作数缺失（left_found={ok_a}, right_found={ok_b}）"
        fa, fb = _num(a), _num(b)
        if fa is None or fb is None:
            if op_name in ("eq", "neq"):
                return (VERDICT_PASSED if fn(a, b) else VERDICT_FAILED), a, b, None
            return VERDICT_INVALID, a, b, "操作数不是数值"
        try:
            ok = fn(fa, fb)
        except ZeroDivisionError:
            return VERDICT_INVALID, a, b, "除零"
        return (VERDICT_PASSED if ok else VERDICT_FAILED), a, b, None
    return run


def _near(check: Check, ctx):
    a, ok_a = _resolve(check.left, ctx)
    b, ok_b = _resolve(check.right, ctx)
    if not (ok_a and ok_b):
        return VERDICT_INVALID, a, b, "操作数缺失"
    fa, fb = _num(a), _num(b)
    if fa is None or fb is None:
        return VERDICT_INVALID, a, b, "操作数不是数值"
    tol = max(float(check.tolerance or 0.0), 1e-9)
    return (VERDICT_PASSED if abs(fa - fb) <= tol else VERDICT_FAILED), a, b, \
        f"允许偏差 ±{tol}"


def _ratio_dev(check: Check, ctx):
    a, ok_a = _resolve(check.left, ctx)
    b, ok_b = _resolve(check.right, ctx)
    if not (ok_a and ok_b):
        return VERDICT_INVALID, a, b, "操作数缺失"
    fa, fb = _num(a), _num(b)
    if fa is None or fb is None:
        return VERDICT_INVALID, a, b, "操作数不是数值"
    if fb == 0:
        return VERDICT_INVALID, a, b, "基准值为 0"
    limit = float(check.max_ratio if check.max_ratio is not None else 0.05)
    dev = abs(fa - fb) / abs(fb)
    return (VERDICT_PASSED if dev <= limit else VERDICT_FAILED), round(dev, 6), limit, \
        f"|实际-目标|/目标 ≤ {limit:.2%}"


def _between(check: Check, ctx):
    a, ok_a = _resolve(check.left, ctx)
    rng, ok_b = _resolve(check.right, ctx)
    if not (ok_a and ok_b) or not isinstance(rng, (list, tuple)) or len(rng) != 2:
        return VERDICT_INVALID, a, rng, "between 需要 [下限, 上限]"
    fa = _num(a)
    lo, hi = _num(rng[0]), _num(rng[1])
    if fa is None or lo is None or hi is None:
        return VERDICT_INVALID, a, rng, "操作数不是数值"
    return (VERDICT_PASSED if lo <= fa <= hi else VERDICT_FAILED), a, [lo, hi], None


def _exists(check: Check, ctx):
    a, ok = _resolve(check.left, ctx)
    return (VERDICT_PASSED if ok else VERDICT_FAILED), a, None, None


def _in_set(check: Check, ctx):
    a, ok_a = _resolve(check.left, ctx)
    s, ok_b = _resolve(check.right, ctx)
    if not (ok_a and ok_b) or not isinstance(s, (list, tuple, set)):
        return VERDICT_INVALID, a, s, "in_set 需要集合"
    return (VERDICT_PASSED if a in s else VERDICT_FAILED), a, list(s), None


def _group(mode: str):
    def run(check: Check, ctx):
        if not check.checks:
            return VERDICT_INVALID, None, None, f"{mode} 无子检查"
        verdicts = []
        details = []
        for sub in check.checks:
            v, a, b, d = _eval_check(sub, ctx)
            verdicts.append((v, a, b, d))
        if any(v == VERDICT_INVALID for v, *_ in verdicts):
            return VERDICT_INVALID, None, None, "子检查存在无法计算项"
        passed = [v == VERDICT_PASSED for v, *_ in verdicts]
        if mode == "all_of":
            ok = all(passed)
        else:
            ok = any(passed)
        for v, a, b, d in verdicts:
            details.append(f"{v}:{a} vs {b}" + (f" ({d})" if d else ""))
        return (VERDICT_PASSED if ok else VERDICT_FAILED), passed, None, "; ".join(details)
    return run


def _not(check: Check, ctx):
    if len(check.checks) != 1:
        return VERDICT_INVALID, None, None, "not 需且仅需一个子检查"
    v, a, b, d = _eval_check(check.checks[0], ctx)
    if v == VERDICT_INVALID:
        return VERDICT_INVALID, a, b, d
    return (VERDICT_FAILED if v == VERDICT_PASSED else VERDICT_PASSED), a, b, d


OPS = {
    "gte": _cmp("gte", lambda a, b: a >= b),
    "lte": _cmp("lte", lambda a, b: a <= b),
    "gt": _cmp("gt", lambda a, b: a > b),
    "lt": _cmp("lt", lambda a, b: a < b),
    "eq": _cmp("eq", lambda a, b: a == b),
    "neq": _cmp("neq", lambda a, b: a != b),
    "near": _near,
    "ratio_dev": _ratio_dev,
    "between": _between,
    "exists": _exists,
    "in_set": _in_set,
    "all_of": _group("all_of"),
    "any_of": _group("any_of"),
    "not": _not,
}


def _eval_check(check: Check, ctx: Dict[str, Any]) -> Tuple[str, Any, Any, Optional[str]]:
    fn = OPS.get(check.op)
    if fn is None:
        raise HarnessConfigError(f"未注册的算子 '{check.op}'（可用：{', '.join(sorted(OPS))}）")
    return fn(check, ctx)


def _validate_ops(check: Check, rule_id: str) -> List[str]:
    """加载期递归校验算子：规则包本身不允许出现白名单外的算子（更不能是 eval/exec）。"""
    errs = []
    if check.op not in OPS:
        errs.append(f"{rule_id}: 未注册的算子 '{check.op}'（可用：{', '.join(sorted(OPS))}）")
    for sub in check.checks:
        errs.extend(_validate_ops(sub, rule_id))
    if check.op in ("all_of", "any_of") and not check.checks:
        errs.append(f"{rule_id}: '{check.op}' 必须带子检查")
    return errs


# ----------------------------------------------------------------------------------
# 裁决聚合
# ----------------------------------------------------------------------------------
def evaluate(pack: RulePack, ctx: Dict[str, Any]) -> HarnessVerdict:
    results: List[RuleResult] = []
    for rule in pack.rules:
        verdict, actual, limit, detail = _eval_check(rule.check, ctx)
        unit = None
        try:
            if rule.check.left is not None:
                unit = rule.check.left.unit
            if unit is None and rule.check.right is not None:
                unit = rule.check.right.unit
        except Exception:
            unit = None
        results.append(RuleResult(
            rule_id=rule.rule_id, title=rule.title, verdict=verdict, severity=rule.severity,
            blocking=rule.is_blocking, message=rule.message, actual=actual, limit=limit,
            unit=unit, citation=rule.citation, suggested_action=rule.suggested_action,
            detail=detail,
        ))

    invalid = [r.rule_id for r in results if r.verdict == VERDICT_INVALID]
    blocking_failed = [r.rule_id for r in results if r.verdict == VERDICT_FAILED and r.blocking]
    soft_failed = [r.rule_id for r in results if r.verdict == VERDICT_FAILED and not r.blocking]
    warnings = [r.message for r in results if r.verdict == VERDICT_FAILED and r.severity == "warning"]

    if invalid:
        agg = AGG_INVALID
    elif blocking_failed:
        agg = AGG_FAILED
    elif soft_failed or warnings:
        agg = AGG_WARN
    else:
        agg = AGG_PASSED

    return HarnessVerdict(pack_id=pack.pack_id, pack_version=pack.version, stage=pack.stage,
                          verdict=agg, results=results, blocking_failures=blocking_failed,
                          invalid_rules=invalid, warnings=warnings)
