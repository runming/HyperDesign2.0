# -*- coding: utf-8 -*-
"""
交互式 AI 助手（前期需求建模 / 中期参数修改 / 后期定型）。

设计原则与 2.0 一致：**助手只做决策与解释，重建与裁决交给确定性执行体**。
- 意图解析：默认用本地确定性规则（离线可用）；若本地大模型可用则优先（见 llm.py），
  但无论哪条路径，最终都落到同一套「参数补丁 → 几何重建 → 准入裁决」流程；
- 越界即拒：壁厚低于规范、拔模低于规范、圆角导致内角失效时，助手不改参数，
  而是给出依据与可行下限（把"AI 幻觉"挡在参数之外）；
- 每次修改都带证据：改了哪几个参数、可行性复算、内核实测、规则裁决。
"""
from __future__ import annotations

import copy
import json
import os
import re
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[3]

PARAM_ALIASES: Dict[str, Tuple[str, ...]] = {
    "LENGTH_X": ("长度", "长向", "X向", "长"),
    "WIDTH_Y": ("宽度", "宽向", "Y向", "宽"),
    "HEIGHT_Z": ("高度", "高向", "Z向", "高"),
    "WALL": ("壁厚", "厚度", "肉厚"),
    "DRAFT_DEG": ("拔模", "斜度", "脱模角"),
    "CORNER_R": ("圆角", "倒角半径", "转角"),
    "POST_PILOT_D": ("底孔", "螺纹孔", "安装孔", "螺丝孔", "螺孔"),
    "LED_D": ("导光孔", "指示孔", "灯孔"),
}

DRAFT_MIN = 1.8
WALL_MIN = 2.4
SPAN_LIMIT = 150.0

PROCESS = {"min_wall_mm": 2.4, "rib_max_mm": 1.44, "min_draft_deg": 1.8,
           "max_bulk_wall_mm": 4.5, "pc_abs_yield_mpa": 50.0, "max_allowable_stress_mpa": 25.0}

_RUNNER = ROOT / "backend" / "app" / "cadir" / "runner_freecad.py"
_EXAMPLE_IR = ROOT / "examples" / "sensor_housing.m0.ir.json"
_CAD_PACK = ROOT / "backend" / "app" / "harness" / "rules" / "housing_cad.v1.json"
_FREECAD = os.environ.get("HD_FREECAD_CMD") or \
    r"C:\Users\omegahyper\AppData\Local\Programs\FreeCAD 1.1\bin\freecadcmd.exe"


def _set_path(d: Dict[str, Any], path: str, value: Any) -> None:
    node = d
    keys = path.split(".")
    for k in keys[:-1]:
        node = node.setdefault(k, {})
    node[keys[-1]] = value


@dataclass
class Session:
    sid: str
    stage: str = "brief"                 # brief → designing → frozen
    ir: Dict[str, Any] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)
    last: Dict[str, Any] = field(default_factory=dict)

    @property
    def params(self) -> Dict[str, float]:
        return dict(self.ir.get("parameters", {}))

    def to_dict(self) -> Dict[str, Any]:
        return {"session": self.sid, "stage": self.stage, "params": self.params,
                "turns": len(self.history), "last": self.last}


class Assistant:
    """单会话助手；多个会话由服务层按 sid 维护。"""

    def __init__(self, session: Session):
        self.s = session
        if not self.s.ir:
            self.s.ir = json.loads(_EXAMPLE_IR.read_text(encoding="utf-8"))

    # ---------------------------------------------------------------- 对外入口
    def message(self, text: str) -> Dict[str, Any]:
        text = (text or "").strip()
        if not text:
            return self._reply("请输入设计需求或修改指令。", kind="empty")

        self.s.history.append({"role": "user", "text": text})

        if self.s.stage == "frozen" and not re.search(r"解冻|重新开始|重来", text):
            return self._reply("当前方案已定型（frozen），参数不再接受修改。"
                               "如需调整请说「解冻」或「重新开始」。", kind="frozen")

        if re.search(r"解冻|重新开始|重来", text):
            self.s.stage = "designing"
            return self._reply("已解冻，可继续修改参数。", kind="unfreeze")

        if re.search(r"定型|定稿|冻结|就这样|确认方案", text):
            return self._finalize()

        if self.s.stage == "brief" and re.search(r"设计|做一?个|外壳|上盖|支架|传感器|包络|尺寸", text):
            return self._brief(text)

        return self._modify(text)

    # ---------------------------------------------------------------- 前期：需求建模
    def _brief(self, text: str) -> Dict[str, Any]:
        changed = []
        # 优先识别「130×90×50」这类包络三元组；否则退回带单位的数字序列
        triple = re.findall(r"(\d+(?:\.\d+)?)\s*(?:mm|毫米)?\s*[×xX*]\s*(\d+(?:\.\d+)?)\s*"
                            r"(?:mm|毫米)?\s*[×xX*]\s*(\d+(?:\.\d+)?)", text)
        if triple:
            nums = [float(v) for v in triple[0]]
        else:
            nums = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*(?:mm|毫米)", text)]
        if len(nums) >= 3:
            for key, val in zip(("LENGTH_X", "WIDTH_Y", "HEIGHT_Z"), nums[:3]):
                old = self.s.params.get(key)
                _set_path(self.s.ir, f"parameters.{key}", val)
                changed.append({"key": key, "from": old, "to": val})
        material = "PC+ABS" if re.search(r"PC\+?ABS|塑料|注塑", text, re.I) else \
            ("6061-T6" if re.search(r"铝|CNC|铣", text) else self._material())
        self.s.ir.setdefault("metadata", {})["material"] = material
        self.s.stage = "designing"

        # 包络变化后自动修正派生参数，避免 IR 自相矛盾（这是"AI 辅助建立"的关键一步）
        derived = self._reconcile_envelope()

        brief = {
            "product": "传感器外壳（注塑上盖 + CNC 底座）" if "外壳" in text or "传感器" in text else "结构件",
            "envelope_mm": [self.s.params.get("LENGTH_X"), self.s.params.get("WIDTH_Y"),
                            self.s.params.get("HEIGHT_Z")],
            "material": material,
            "process": "注塑（二号车间）" if material == "PC+ABS" else "CNC 铣削",
            "key_params": {"WALL": self.s.params.get("WALL"), "DRAFT_DEG": self.s.params.get("DRAFT_DEG"),
                           "CORNER_R": self.s.params.get("CORNER_R")},
        }
        fea = self._feasibility()
        build = self._rebuild()
        hint = ""
        if derived:
            hint = "\n已自动调整派生参数：" + "、".join(f"{d['key']} {d['from']}→{d['to']}" for d in derived)
        reply = (f"已理解需求：{brief['product']}，包络 "
                 f"{brief['envelope_mm'][0]}×{brief['envelope_mm'][1]}×{brief['envelope_mm'][2]}mm，"
                 f"材料 {material}，工艺 {brief['process']}。\n"
                 f"当前关键参数：壁厚 {brief['key_params']['WALL']}mm、拔模 {brief['key_params']['DRAFT_DEG']}°、"
                 f"外角 R{brief['key_params']['CORNER_R']}mm。" + hint + "\n"
                 f"可行性判定：{'通过' if fea.get('feasible') else '存在风险 ' + str(fea.get('violations'))}；"
                 f"重建：{'成功' if build.get('ok') else '失败'}。\n"
                 f"接下来可以直接说：把壁厚改成 2.6、圆角改 5、安装孔改 M4 底孔、或者定型。")
        return self._reply(reply, kind="brief", changed=changed, brief=brief,
                           feasibility=fea, build=build)

    # ---------------------------------------------------------------- 中期：参数修改
    def _modify(self, text: str) -> Dict[str, Any]:
        changed: List[Dict[str, Any]] = []
        notes: List[str] = []
        standards: List[Dict[str, Any]] = []
        fea_before = self._feasibility()

        # 1) 螺纹/标准件吸附
        m = re.search(r"(M\s?\d+(?:\.\d+)?)", text, re.I)
        if m and re.search(r"孔|螺纹|螺丝", text):
            from ..standards.tables import snap_hole
            thread = m.group(1).replace(" ", "")
            kind = "pilot" if re.search(r"底孔|螺纹|攻丝", text) else "clearance"
            try:
                spec = snap_hole(thread, kind)
            except ValueError as exc:
                return self._reply(f"无法识别：{exc}", kind="error")
            old = self.s.params.get("POST_PILOT_D")
            _set_path(self.s.ir, "parameters.POST_PILOT_D", spec["diameter_mm"])
            changed.append({"key": "POST_PILOT_D", "from": old, "to": spec["diameter_mm"]})
            standards.append({**spec, "applied_to": "POST_PILOT_D"})
            notes.append(f"{thread} {'底孔' if kind == 'pilot' else '通孔'}按标准取 Ø{spec['diameter_mm']}mm"
                         f"（{spec['source']}）")

        # 2) 包络三连
        triple = re.findall(r"(\d+(?:\.\d+)?)\s*(?:mm|毫米)?\s*[×xX*]\s*(\d+(?:\.\d+)?)\s*"
                            r"(?:mm|毫米)?\s*[×xX*]\s*(\d+(?:\.\d+)?)", text)
        if triple:
            for key, val in zip(("LENGTH_X", "WIDTH_Y", "HEIGHT_Z"), [float(v) for v in triple[0]]):
                old = self.s.params.get(key)
                if old != val:
                    _set_path(self.s.ir, f"parameters.{key}", val)
                    changed.append({"key": key, "from": old, "to": val})

        # 3) 单参数
        if not triple and not (m and "孔" in text):
            for key, aliases in PARAM_ALIASES.items():
                if any(a in text for a in aliases):
                    num = re.search(r"(\d+(?:\.\d+)?)", text)
                    if not num:
                        continue
                    val = float(num.group(1))
                    old = self.s.params.get(key)
                    if old == val:
                        continue
                    _set_path(self.s.ir, f"parameters.{key}", val)
                    changed.append({"key": key, "from": old, "to": val})
                    break

        if not changed:
            return self._reply("我没听懂这条指令。可以这样说：把壁厚改成 2.6 / 圆角改 5 / "
                               "包络改 130×90×50 / 安装孔改 M4 底孔 / 检查可行性 / 定型。",
                               kind="unclear")

        # 4) 规范守卫
        rejection = self._guard(changed)
        if rejection:
            for c in changed:                       # 回滚
                _set_path(self.s.ir, f"parameters.{c['key']}", c["from"])
            return self._reply(rejection, kind="rejected", changed=changed)

        # 4b) 包络变了 → 自动重算派生参数（立柱高度/导光窗位置/高厚比壁厚）
        if any(c["key"] in ("LENGTH_X", "WIDTH_Y", "HEIGHT_Z") for c in changed):
            derived = self._reconcile_envelope()
            changed.extend(derived)
            if derived:
                notes.append("自动重算派生参数：" +
                             "、".join(f"{d['key']} {d['from']}→{d['to']}" for d in derived))

        # 5) 可行性与重建（只回滚"因本次修改新增"的违反项，基线本身的问题保留并提示）
        fea_before = fea_before or {}
        fea = self._feasibility()
        new_viol = set(fea.get("violations", [])) - set(fea_before.get("violations", []))
        if new_viol:
            for c in changed:
                _set_path(self.s.ir, f"parameters.{c['key']}", c["from"])
            return self._reply(
                f"这组参数会让以下约束失效：{'、'.join(sorted(new_viol))}。"
                f"内角半径将变为 {fea['derived']['r_top_mm']}mm（要求 ≥0.2），"
                f"建议圆角 ≥{self._min_radius():.1f}mm。已回滚，参数未变。",
                kind="infeasible", changed=changed, feasibility=fea)

        build = self._rebuild()
        if not build.get("ok"):
            for c in changed:
                _set_path(self.s.ir, f"parameters.{c['key']}", c["from"])
            return self._reply(f"内核重建失败，已回滚：{build.get('error', '')[:160]}",
                               kind="build_failed", changed=changed, build=build)

        verdict, evidence = self._harness(build.get("metrics") or {})
        if verdict != "passed":
            # 工程证据闭环：本次修改导致准入不通过 → 回滚并回报证据（不把坏方案留在会话里）
            for c in changed:
                _set_path(self.s.ir, f"parameters.{c['key']}", c["from"])
            metrics = build.get("metrics") or {}
            return self._reply(
                f"这次修改会让方案不可交付：准入裁决为 {verdict}。未通过项：{'、'.join(evidence[:4])}。"
                f"实测实体数 {metrics.get('solids')}（要求 1）、包络 {metrics.get('bbox_mm')}。"
                f"已回滚到修改前状态。若确实需要该尺寸，需同步调整立柱布局或壁厚。",
                kind="regression", changed=changed, feasibility=fea, build=build,
                verdict=verdict, evidence=evidence)
        desc = "、".join(f"{c['key']} {c['from']}→{c['to']}" for c in changed)
        reply = f"已修改：{desc}。" + ("".join("\n" + n for n in notes) if notes else "")
        reply += (f"\n重建成功：体积 {build.get('metrics', {}).get('volume_mm3')}mm³，"
                  f"包络 {build.get('metrics', {}).get('bbox_mm')}，"
                  f"实测拔模 {build.get('metrics', {}).get('dfm', {}).get('min_draft_deg')}°。")
        reply += f"\n准入裁决：**{verdict}**。" + ("" if verdict == "passed"
                                                 else "\n未通过项：" + "、".join(evidence[:4]))
        if not fea.get("feasible"):
            reply += (f"\n提示：基线仍有未消除的约束风险 {'、'.join(fea.get('violations', []))}，"
                      f"建议一并调整（例如高厚比超限时抬高壁厚）。")
        return self._reply(reply, kind="modified", changed=changed, feasibility=fea,
                           build=build, verdict=verdict, evidence=evidence, standards=standards)

    # ---------------------------------------------------------------- 后期：定型
    def _finalize(self) -> Dict[str, Any]:
        fea = self._feasibility()
        build = self._rebuild()
        verdict, evidence = self._harness(build.get("metrics") or {}) if build.get("ok") else ("invalid", [])
        if build.get("ok") and verdict == "passed" and fea.get("feasible"):
            self.s.stage = "frozen"
            p = self.s.params
            reply = (f"已定型。定版参数：包络 {p['LENGTH_X']}×{p['WIDTH_Y']}×{p['HEIGHT_Z']}mm，"
                     f"壁厚 {p['WALL']}mm，拔模 {p['DRAFT_DEG']}°，外角 R{p['CORNER_R']}mm，"
                     f"导光孔 Ø{p['LED_D']}mm，安装柱底孔 Ø{p['POST_PILOT_D']}mm。\n"
                     f"交付物：STEP / STL / 工程图（含公差标注）。后续修改需先说「解冻」。")
            return self._reply(reply, kind="frozen", feasibility=fea, build=build,
                               verdict=verdict, evidence=evidence)
        return self._reply(f"定不了型：可行性={fea.get('feasible')}，重建={build.get('ok')}，"
                           f"准入={verdict}。请先处理上述问题。",
                           kind="finalize_blocked", feasibility=fea, build=build,
                           verdict=verdict, evidence=evidence)

    # ---------------------------------------------------------------- 派生参数自洽
    def _reconcile_envelope(self) -> List[Dict[str, Any]]:
        """包络变化后，按几何关系修正依赖参数，避免"改尺寸后立柱穿顶/孔跑到面外"。"""
        p = self.s.params
        L, W, H = p["LENGTH_X"], p["WIDTH_Y"], p["HEIGHT_Z"]
        wall, draft = p["WALL"], p["DRAFT_DEG"]
        target: Dict[str, float] = {
            "POST_INSET": max(6.0, min(10.0, min(L, W) / 4.0)),   # 立柱内缩
            "POST_H": round(H - wall, 1),                          # 必须顶到内顶面才与壳体融合
            "LED_DEPTH": round(wall + 2.0, 1),                     # 穿透顶壁的导光窗
            "LED_Z": round(H - 3.4, 1),
        }
        # 高厚比超限时自动抬高壁厚（H/wall ≤ 20）
        if H / wall > 20.0:
            import math
            need = math.ceil(H / 20.0 * 10) / 10.0
            target["WALL"] = max(wall, need)
            target["POST_H"] = round(H - target["WALL"], 1)        # 壁厚变了，立柱高度随之重算
        changed = []
        for key, val in target.items():
            old = self.s.params.get(key)
            if old is None or abs(float(old) - float(val)) < 1e-6:
                continue
            _set_path(self.s.ir, f"parameters.{key}", val)
            changed.append({"key": key, "from": old, "to": val})
        return changed

    # ---------------------------------------------------------------- 守卫与执行
    def _guard(self, changed: List[Dict[str, Any]]) -> Optional[str]:
        p = self.s.params
        span = max(p["LENGTH_X"], p["WIDTH_Y"])
        for c in changed:
            if c["key"] == "WALL" and c["to"] < WALL_MIN:
                return (f"壁厚 {c['to']}mm 低于企业规范下限：跨度 {span:.0f}mm 的 PC+ABS 注塑件"
                        f"名义壁厚必须 ≥2.4mm（严禁 2.0mm），否则缩水与欠注风险高。已拒绝，参数未变。")
            if c["key"] == "DRAFT_DEG" and c["to"] < DRAFT_MIN:
                return (f"拔模 {c['to']}° 低于规范下限 1.8°，会出现卡模拉伤。已拒绝，参数未变。")
            if c["key"] in ("LENGTH_X", "WIDTH_Y", "HEIGHT_Z") and c["to"] <= 0:
                return "尺寸必须为正数。已拒绝。"
        return None

    def _material(self) -> str:
        return self.s.ir.get("metadata", {}).get("material", "PC+ABS")

    def _feasibility(self) -> Dict[str, Any]:
        from ..cadir.feasibility import HousingParams, evaluate
        p = self.s.params
        return evaluate(HousingParams(length_mm=p["LENGTH_X"], width_mm=p["WIDTH_Y"],
                                      height_mm=p["HEIGHT_Z"], wall_mm=p["WALL"],
                                      draft_deg=p["DRAFT_DEG"], corner_r_mm=p["CORNER_R"]))

    def _min_radius(self) -> float:
        import math
        p = self.s.params
        need = p["HEIGHT_Z"] * math.tan(math.radians(p["DRAFT_DEG"])) + \
            p["WALL"] / math.cos(math.radians(p["DRAFT_DEG"])) + 0.2
        return math.ceil(need * 10) / 10.0

    def _rebuild(self) -> Dict[str, Any]:
        tmp = Path(tempfile.mkdtemp(prefix="hd_assist_"))
        ir_path = tmp / "ir.json"
        ir_path.write_text(json.dumps(self.s.ir, ensure_ascii=False), encoding="utf-8")
        env = dict(os.environ, HD2_CAD_IR=str(ir_path), HD2_CAD_OUT=str(tmp))
        subprocess.run([_FREECAD, str(_RUNNER)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env, timeout=300)
        rep_path = tmp / "cad_report.json"
        if not rep_path.exists():
            return {"ok": False, "error": "内核未产出报告"}
        rep = json.loads(rep_path.read_text(encoding="utf-8"))
        if not rep.get("ok"):
            return {"ok": False, "error": "; ".join(rep.get("errors", []))[:300]}
        return {"ok": True, "metrics": rep.get("metrics") or {}}

    def _harness(self, metrics: Dict[str, Any]) -> Tuple[str, List[str]]:
        from ..harness.engine import RulePack, evaluate
        p = self.s.params
        pack = RulePack.load(_CAD_PACK)
        target = {"bbox_mm": {"x": p["LENGTH_X"], "y": p["WIDTH_Y"], "z": p["HEIGHT_Z"]},
                  "tolerance_mm": 1.5}
        v = evaluate(pack, {"cad": metrics, "target": target, "process": PROCESS, "params": {}})
        return v.verdict, list(v.blocking_failures)[:6]

    # ---------------------------------------------------------------- 回复封装
    def _reply(self, text: str, *, kind: str, **extra) -> Dict[str, Any]:
        payload = {"session": self.s.sid, "stage": self.s.stage, "kind": kind,
                   "reply": text, "params": self.s.params}
        payload.update({k: v for k, v in extra.items() if v is not None})
        self.s.history.append({"role": "assistant", "text": text, "kind": kind})
        self.s.last = payload
        return payload
