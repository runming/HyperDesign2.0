# -*- coding: utf-8 -*-
"""知识库种子数据：v1 的 6 条工艺规范原文 + 1 条仅管理者可见的成本基线（用于演示 RBAC）。

所有条款均来自工程文件/RAG 语料原文，**未改写数值**；仅按条款切成可引用片段。
"""
from __future__ import annotations

from .knowledge import Document

DOCS = [
    Document(
        doc_id="spec_injection_v24",
        title="内部注塑工艺规范_v2.4.pdf",
        source_type="pdf", version="v2.4",
        access_roles=("engineer", "admin"),
        content=(
            "我司二号车间海天注塑机加工 PC+ABS 材质工业外壳时，凡外壳最大跨度超过 150mm 的产品，"
            "标准名义壁厚必须设定为 2.4mm（严禁采用通用 2.0mm）。"
            "内侧加强筋厚度不得超过名义壁厚的 60%（即 1.44mm），否则极易产生表面缩水纹。"
            "拔模斜度统一要求 ≥ 1.8°。"
            "若实测存在 < 1.8mm 的薄壁区（注塑欠注风险）或 > 4.5mm 的肥厚积料区（缩水纹风险），直接判定为 rejected。"
            "随机采样 500 个表面点向内发射反向法线射线，取 10% 分位最薄处壁厚作为 p10_thickness 判据。"
        ),
    ),
    Document(
        doc_id="spec_sheetmetal_2025",
        title="钣金折弯展开标准_2025.docx",
        source_type="docx", version="2025",
        access_roles=("engineer", "admin"),
        content=(
            "我司激光切割+数控折弯产线加工 2.0mm 冷轧钢板（SPCC）时，90度折弯统一使用 V12 下模，"
            "内R角按 R1.6 计算，折弯扣除系数（K因子校准值）固定取 3.35mm。"
        ),
    ),
    Document(
        doc_id="brief_sensor_housing",
        title="工程文件_Phase2_产品设计任务书.docx",
        source_type="docx", version="v1.0",
        access_roles=("viewer", "engineer", "admin"),
        content=(
            "产品：工业级无线振动温湿度三合一传感器外壳（安装在电机表面）。"
            "尺寸包络：120mm x 80mm x 45mm。"
            "工艺要求：顶部为 PC+ABS 抗冲击注塑上盖（壁厚 2.4mm，拔模角 1.8 度，带状态指示灯导光柱窗口）。"
            "底部为铝合金 CNC 底座（带两侧 M6 安装耳和磁吸沉孔）。"
            "上下壳通过 4 颗内六角螺钉锁紧并夹持硅胶防水圈。"
        ),
    ),
    Document(
        doc_id="rule_cad_phase5",
        title="工程文件_Phase5_CAD铁律.docx",
        source_type="docx", version="v1.0",
        access_roles=("engineer", "admin"),
        content=(
            "HyperDesign Phase 5 参数化 CAD 建模铁律："
            "必须通过 OpenCascade 底层拓扑检验 solid.isValid() 是否为 True（无自交面、无破洞）。"
            "严禁使用危险的大半径 fillet() 导致 BRep_API: command not done 拓扑崩溃；建议外圆角 R <= 3.0mm，"
            "内圆角 R <= 1.0mm，且在 shell() 抽壳之前先做外部主倒角。"
            "项目基准参数：标准壁厚 2.4mm，顶部状态指示灯导光孔径 8.0mm。"
            "自愈机制：报错或超差自动重试，最多 5 次，失败样本自动捕获为 Phase 7 的 DPO 负样本。"
        ),
    ),
    Document(
        doc_id="rule_drawing_phase6",
        title="工程文件_Phase6_制图规范.docx",
        source_type="docx", version="v1.0",
        access_roles=("engineer", "admin"),
        content=(
            "HyperDesign Phase 6 工程图纸规范（GB/T 14665 机械工程 CAD 制图标准图层体系）："
            "CUT_PROFILE = 1:1 激光切割/CNC 实线外轮廓层（直接导入机床 CAM）。"
            "HIDDEN_LINE = 内部暗孔/抽壳内壁虚线层（供审图看内部壁厚与螺钉柱深度）。"
            "DIMENSIONS = 长宽高检验尺寸标注层（质检员拿卡尺验收的依据）。"
            "TITLE_BLOCK = A3 标准图框、标题栏与来自 Phase 1 RAG 的技术要求文本。"
            "文件格式：激光切割 1:1 净轮廓 DXF（MM, R2010），尺寸线严禁混入切割层。"
            "A3 图幅 420mm x 297mm，标题栏自动打印 WALL / DRAFT: 2.4mm / >= 1.8 deg。"
            "PDF 渲染 figsize=(16.53, 11.69), dpi=300。"
        ),
    ),
    Document(
        doc_id="rule_dfm_phase7",
        title="工程文件_Phase7_DFM双层评判.docx",
        source_type="docx", version="v1.0",
        access_roles=("engineer", "admin"),
        content=(
            "HyperDesign 双层自动评判引擎：客观几何铁律 > VLM 主观审美。"
            "壁厚红线扫描：从零件表面向内发射法向射线测量真实局部壁厚。"
            "拔模角扫描：统计所有近似平行于脱模方向（Z 轴）的立面法向量夹角，识别零度直壁（卡模拉伤风险）。"
            "只有通过第一关几何硬指标的方案，才送 VLM 检查视觉特征是否漏项"
            "（如顶部状态指示灯导光窗口、两侧 M6 安装耳是否在图中清晰可见）。"
        ),
    ),
    Document(
        doc_id="cost_baseline_2026q3",
        title="供应商报价与成本基线_2026Q3（仅管理者可见）",
        source_type="xlsx", version="2026Q3",
        access_roles=("admin",),
        content=(
            "【合成示例数据，仅用于演示权限隔离】二号车间 PC+ABS 注塑件单价 12.8 元/件，"
            "铝 CNC 底座 26.5 元/件，最小起订量 500 件。"
            "本文件对所有非管理者角色不可见，用于验证知识库 RBAC 过滤。"
        ),
    ),
]


def seed(kb) -> int:
    return kb.ingest_many([Document(**{k: v for k, v in d.__dict__.items()}) for d in DOCS])
