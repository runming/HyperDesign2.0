# -*- coding: utf-8 -*-
"""
DXF 工程图导出（R12 ASCII，自带写出器，无第三方依赖）。

与"只导出光轮廓"的常见做法不同，这里按图层分工并**带公差语义**：
  CUT_PROFILE  1:1 激光切割/CNC 外轮廓（直接进 CAM）
  HIDDEN_LINE  内腔与不可见边（虚线）
  DIMENSIONS   尺寸线 + 尺寸文本（含公差，如 120 ±0.062）
  TITLE_BLOCK  图框标题栏（材料/壁厚/拔模/公差等级/来源）
公差取值来自 `app/standards/tables.py` 的 GB/T 1800.1 标准公差表，按 IT 等级自动查表。
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from ..standards.tables import tolerance_for

LAYERS = [
    ("CUT_PROFILE", 7, "CONTINUOUS", 0.35),
    ("HIDDEN_LINE", 8, "DASHED", 0.18),
    ("DIMENSIONS", 5, "CONTINUOUS", 0.13),
    ("TITLE_BLOCK", 2, "CONTINUOUS", 0.25),
]


class DxfBuilder:
    """最小可用的 R12 DXF 写出器。"""

    def __init__(self, width: float = 420.0, height: float = 297.0):
        self.width, self.height = width, height
        self.entities: List[str] = []

    # ---------------- 基本图元 ----------------
    def _fmt(self, v: float) -> str:
        return f"{v:.4f}".rstrip("0").rstrip(".") or "0"

    def line(self, x1, y1, x2, y2, layer: str = "CUT_PROFILE") -> None:
        self.entities.append(
            "\n".join(["0", "LINE", "8", layer,
                       "10", self._fmt(x1), "20", self._fmt(y1), "30", "0",
                       "11", self._fmt(x2), "21", self._fmt(y2), "31", "0"]))

    def circle(self, cx, cy, r, layer: str = "CUT_PROFILE") -> None:
        self.entities.append(
            "\n".join(["0", "CIRCLE", "8", layer,
                       "10", self._fmt(cx), "20", self._fmt(cy), "30", "0",
                       "40", self._fmt(r)]))

    def text(self, x, y, s: str, height: float = 2.5, layer: str = "DIMENSIONS",
             align: str = "LEFT") -> None:
        # DXF R12 无 UTF-8 官方支持：非 ASCII 统一转 \U+XXXX（AutoCAD/CAXA 可正确还原）
        esc = "".join(ch if ord(ch) < 128 else f"\\U+{ord(ch):04X}" for ch in s)
        self.entities.append(
            "\n".join(["0", "TEXT", "8", layer,
                       "10", self._fmt(x), "20", self._fmt(y), "30", "0",
                       "40", self._fmt(height), "1", esc, "72", "0" if align == "LEFT" else "1",
                       "73", "0"]))

    def rect(self, x0, y0, x1, y1, layer: str = "CUT_PROFILE") -> None:
        for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)),
                     ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
            self.line(a[0], a[1], b[0], b[1], layer)

    # ---------------- 输出 ----------------
    def to_string(self) -> str:
        out: List[str] = ["0", "SECTION", "2", "HEADER",
                          "9", "$ACADVER", "1", "AC1009",
                          "9", "$EXTMIN", "10", "0", "20", "0", "30", "0",
                          "9", "$EXTMAX", "10", self._fmt(self.width), "20", self._fmt(self.height),
                          "30", "0", "0", "ENDSEC"]
        out += ["0", "SECTION", "2", "TABLES"]
        out += ["0", "TABLE", "2", "LTYPE", "70", "2"]
        out += ["0", "LTYPE", "2", "CONTINUOUS", "70", "64", "3", "Solid line",
                "72", "65", "73", "0", "40", "0"]
        out += ["0", "LTYPE", "2", "DASHED", "70", "64", "3", "__ __ __",
                "72", "65", "73", "2", "40", "7.5", "49", "5.0", "49", "-2.5"]
        out += ["0", "ENDTAB"]
        out += ["0", "TABLE", "2", "LAYER", "70", str(len(LAYERS))]
        for name, color, ltype, lw in LAYERS:
            out += ["0", "LAYER", "2", name, "70", "0", "62", str(color), "6", ltype,
                    "370", str(int(lw * 100))]
        out += ["0", "ENDTAB", "0", "ENDSEC"]
        out += ["0", "SECTION", "2", "ENTITIES"]
        out += self.entities
        out += ["0", "ENDSEC", "0", "EOF"]
        return "\n".join(out) + "\n"

    def save(self, path: Path) -> Path:
        """UTF-8 写出：几何坐标为纯 ASCII 数值；标题栏含中文，需 UTF-8 才不丢字。"""
        path = Path(path)
        path.write_text(self.to_string(), encoding="utf-8")
        return path


# -------------------------------------------------------------------------------- 工程图
def _fmt_tol(size_mm: float, grade: str = "IT9") -> Tuple[str, float]:
    """公差文本用 AutoCAD 控制码 %%p（=±），保持 DXF 纯 ASCII。"""
    tol = tolerance_for(size_mm, grade)
    return f"%%p{tol['tolerance_mm']:.3f}", tol["tolerance_um"]


def export_part_drawing(ir: dict, metrics: dict, out_path: Path,
                        sheet: Tuple[float, float] = (420.0, 297.0)) -> dict:
    """
    由 CAD-IR 参数与实测指标生成 1:1 工程图 DXF（带公差标注）。
    返回结构化摘要，供门禁与界面使用。
    """
    p = ir.get("parameters", {})
    L, W, H = float(p["LENGTH_X"]), float(p["WIDTH_Y"]), float(p["HEIGHT_Z"])
    wall = float(p.get("WALL", 2.4))
    draft = float(p.get("DRAFT_DEG", 1.8))
    led_d = float(p.get("LED_D", 8.0))
    post_od = float(p.get("POST_OD", 8.0))
    inset = float(p.get("POST_INSET", 10.0))

    b = DxfBuilder(*sheet)
    # 1) 外轮廓（1:1，左下角置于图框内留白处）
    ox, oy = 60.0, 90.0
    b.rect(ox, oy, ox + L, oy + W, "CUT_PROFILE")
    # 2) 内腔（虚线）
    b.rect(ox + wall, oy + wall, ox + L - wall, oy + W - wall, "HIDDEN_LINE")
    # 3) 孔位：导光孔（中心）+ 4 根安装柱
    holes: List[Tuple[float, float, float]] = [(ox + L / 2, oy + W / 2, led_d / 2)]
    for sx in (-1, 1):
        for sy in (-1, 1):
            holes.append((ox + L / 2 + sx * (L / 2 - inset),
                          oy + W / 2 + sy * (W / 2 - inset), post_od / 2))
    for cx, cy, r in holes:
        b.circle(cx, cy, r, "CUT_PROFILE")

    # 4) 尺寸 + 公差
    tol_l, tol_l_um = _fmt_tol(L)
    tol_w, tol_w_um = _fmt_tol(W)
    tol_h, tol_h_um = _fmt_tol(H)
    tol_d, tol_d_um = _fmt_tol(led_d)

    # 水平总长
    b.line(ox, oy - 12, ox + L, oy - 12, "DIMENSIONS")
    b.line(ox, oy - 4, ox, oy - 16, "DIMENSIONS")
    b.line(ox + L, oy - 4, ox + L, oy - 16, "DIMENSIONS")
    b.text(ox + L / 2 - 14, oy - 20, f"{L:.1f} {tol_l}", 3.0)
    # 垂直总宽
    b.line(ox - 12, oy, ox - 12, oy + W, "DIMENSIONS")
    b.line(ox - 4, oy, ox - 16, oy, "DIMENSIONS")
    b.line(ox - 4, oy + W, ox - 16, oy + W, "DIMENSIONS")
    b.text(ox - 42, oy + W / 2, f"{W:.1f} {tol_w}", 3.0)
    # 导光孔直径（引线 + 文本）
    cx, cy, r = holes[0]
    b.line(cx + r, cy + r, cx + 26, cy + 26, "DIMENSIONS")
    b.text(cx + 28, cy + 24, f"2-%%c{led_d:.1f} {tol_d}", 3.0)
    # 厚度说明（注在标题栏）

    # 5) 标题栏（图框右下）
    tx, ty = sheet[0] - 200.0, 20.0
    b.rect(tx, ty, tx + 180, ty + 62, "TITLE_BLOCK")
    b.line(tx, ty + 46, tx + 180, ty + 46, "TITLE_BLOCK")
    b.line(tx, ty + 32, tx + 180, ty + 32, "TITLE_BLOCK")
    b.line(tx, ty + 18, tx + 180, ty + 18, "TITLE_BLOCK")
    b.text(tx + 4, ty + 52, "HyperDesign 2.0  工程图（1:1）", 3.4, "TITLE_BLOCK")
    b.text(tx + 4, ty + 36, f"材料 PC+ABS   壁厚 {wall}mm   拔模 ≥{draft}°   高度 {H:.1f} {tol_h}", 2.8, "TITLE_BLOCK")
    b.text(tx + 4, ty + 22, f"公差等级 IT9（GB/T 1800.1）：{tol_l_um}/{tol_w_um}/{tol_h_um}µm", 2.6, "TITLE_BLOCK")
    b.text(tx + 4, ty + 6,
           f"实测：体积 {metrics.get('volume_mm3', 0):.1f}mm3  包络 "
           f"{metrics.get('bbox_mm', {}).get('x', L):.1f}×{metrics.get('bbox_mm', {}).get('y', W):.1f}"
           f"×{metrics.get('bbox_mm', {}).get('z', H):.1f}mm", 2.4, "TITLE_BLOCK")

    out_path = b.save(Path(out_path))
    return {"path": str(out_path), "layers": [l[0] for l in LAYERS],
            "holes": len(holes), "dimensions": 3,
            "tolerances": {"length": tol_l, "width": tol_w, "height": tol_h, "hole": tol_d,
                           "grade": "IT9", "um": {"length": tol_l_um, "width": tol_w_um,
                                                 "height": tol_h_um, "hole": tol_d_um}},
            "outline_mm": [L, W], "sheet_mm": list(sheet)}


# -------------------------------------------------------------------------------- 解析（自检）
def parse_entities(path: Path) -> dict:
    """极简 DXF 解析：按图层统计图元数量、收集 TEXT 内容。"""
    raw = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    counts: dict = {}
    texts: List[str] = []
    layer = None
    i = 0
    while i < len(raw) - 1:
        code, val = raw[i].strip(), raw[i + 1].strip()
        if code == "0":
            ent = val
            if ent in ("LINE", "CIRCLE", "TEXT"):
                layer = None
                j = i + 2
                content = None
                while j < len(raw) - 1 and raw[j].strip() != "0":
                    if raw[j].strip() == "8":
                        layer = raw[j + 1].strip()
                    if ent == "TEXT" and raw[j].strip() == "1":
                        content = raw[j + 1].strip()
                    j += 2
                key = f"{ent}@{layer}"
                counts[key] = counts.get(key, 0) + 1
                if content:
                    texts.append(content)
                i = j
                continue
        i += 2
    return {"counts": counts, "texts": texts,
            "total": sum(counts.values()), "layers": sorted({k.split("@")[1] for k in counts
                                                            if "@" in k and k.split("@")[1] != "None"})}
