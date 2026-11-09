# -*- coding: utf-8 -*-
"""国标/企标标准件与公差表（用于把自由尺寸吸附到工业标准值）。

数据来源与用途：
- 螺纹底孔/通孔：ISO 273 / GB/T 152.2 常用值（塑性材料取偏大者）；
- 常用板厚/型材：企业内部常用序列（示例，可按企业替换）；
- 尺寸公差：GB/T 1800.1 标准公差数值（IT7~IT12，基本尺寸 30~50mm 段）。

所有取值仅用于"吸附建议"，不改变用户明确指定的非标值；吸附结果会在回复中给出偏差。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# 公制粗牙螺纹：通孔 / 底孔（mm）
THREAD_TABLE: Dict[str, Dict[str, float]] = {
    "M2": {"clearance": 2.4, "pilot": 1.6},
    "M2.5": {"clearance": 2.9, "pilot": 2.05},
    "M3": {"clearance": 3.4, "pilot": 2.5},
    "M4": {"clearance": 4.5, "pilot": 3.3},
    "M5": {"clearance": 5.5, "pilot": 4.2},
    "M6": {"clearance": 6.6, "pilot": 5.0},
    "M8": {"clearance": 9.0, "pilot": 6.8},
    "M10": {"clearance": 11.0, "pilot": 8.5},
}

# 常用板厚 / 壁厚序列（mm）
COMMON_THICKNESS = [1.0, 1.2, 1.5, 2.0, 2.4, 3.0, 4.0, 5.0, 6.0, 8.0]

# GB/T 1800.1 标准公差（µm），按基本尺寸段
IT_TABLE: List[Tuple[Tuple[float, float], Dict[str, float]]] = [
    ((0.5, 3), {"IT7": 10, "IT8": 14, "IT9": 25, "IT10": 40, "IT11": 60, "IT12": 100}),
    ((3, 6), {"IT7": 12, "IT8": 18, "IT9": 30, "IT10": 48, "IT11": 75, "IT12": 120}),
    ((6, 10), {"IT7": 15, "IT8": 22, "IT9": 36, "IT10": 58, "IT11": 90, "IT12": 150}),
    ((10, 18), {"IT7": 18, "IT8": 27, "IT9": 43, "IT10": 70, "IT11": 110, "IT12": 180}),
    ((18, 30), {"IT7": 21, "IT8": 33, "IT9": 52, "IT10": 84, "IT11": 130, "IT12": 210}),
    ((30, 50), {"IT7": 25, "IT8": 39, "IT9": 62, "IT10": 100, "IT11": 160, "IT12": 250}),
    ((50, 80), {"IT7": 30, "IT8": 46, "IT9": 74, "IT10": 120, "IT11": 190, "IT12": 300}),
    ((80, 120), {"IT7": 35, "IT8": 54, "IT9": 87, "IT10": 140, "IT11": 220, "IT12": 350}),
    ((120, 180), {"IT7": 40, "IT8": 63, "IT9": 100, "IT10": 160, "IT11": 250, "IT12": 400}),
]

# 常用配合：孔/轴基本偏差（用于工程图公差标注）——仅给出常用几档
FITS = {
    "H7": ("基孔制", "下偏差 0"),
    "g6": ("间隙配合", "上偏差约 -0.009（φ30 段）"),
    "k6": ("过渡配合", "上偏差约 +0.015（φ30 段）"),
    "p6": ("过盈配合", "上偏差约 +0.035（φ30 段）"),
}


def nearest(value: float, table: List[float]) -> Tuple[float, float]:
    """返回最接近的标准值与偏差。"""
    best = min(table, key=lambda v: abs(v - value))
    return best, round(value - best, 4)


def snap_thickness(value: float) -> Dict[str, Any]:
    std, delta = nearest(value, COMMON_THICKNESS)
    return {"input": value, "standard": std, "delta_mm": delta,
            "snapped": abs(delta) > 1e-9,
            "reason": "吸附到常用板厚/壁厚序列" if abs(delta) > 1e-9 else "已是标准值"}


def thread_spec(thread: str) -> Optional[Dict[str, float]]:
    return THREAD_TABLE.get(thread.upper().strip())


def snap_hole(thread: str, kind: str = "pilot") -> Dict[str, Any]:
    """把孔尺寸吸附到指定螺纹的标准底孔/通孔。"""
    spec = thread_spec(thread)
    if spec is None:
        raise ValueError(f"未知螺纹规格 {thread}；支持 {list(THREAD_TABLE)}")
    if kind not in ("pilot", "clearance"):
        raise ValueError("kind 只能是 pilot（底孔）或 clearance（通孔）")
    return {"thread": thread.upper(), "kind": kind, "diameter_mm": spec[kind],
            "source": "ISO 273 / GB/T 152.2 常用值",
            "note": "塑性材料（PC+ABS）取偏大底孔，避免滑牙与开裂"}


def tolerance_for(size_mm: float, grade: str = "IT9") -> Dict[str, Any]:
    """按基本尺寸取标准公差值（µm）。"""
    for (lo, hi), grades in IT_TABLE:
        if lo < size_mm <= hi:
            if grade not in grades:
                raise ValueError(f"不支持的等级 {grade}")
            return {"size_mm": size_mm, "grade": grade, "tolerance_um": grades[grade],
                    "tolerance_mm": round(grades[grade] / 1000.0, 4),
                    "source": "GB/T 1800.1 标准公差数值"}
    raise ValueError(f"基本尺寸 {size_mm}mm 超出表范围（0.5~180mm）")
