# HyperDesign 2.0 —— 面向制造的可验证 AI 设计平台

> 参赛版本（第三届"兴智杯"全国人工智能创新应用大赛 · 解决方案赛）
> 1.0 是"能出活的引擎"，2.0 是"能被工厂验收的系统"：**把生成式造型深度装进平台化工程骨架**。

## 一、2.0 相对 1.0 的六个结构升级

| # | 升级 | 1.0 的问题 | 2.0 的做法 |
|---|---|---|---|
| 1 | **CAD-IR 受控中间表示** | LLM 直接写 FreeCAD Python 并在内核里执行，不可审计、换不了内核 | 智能体只产出 JSON（参数/特征/语义引用），由**固定白名单解释器**执行；`execute_script` 一律拒绝 |
| 2 | **Harness 规则引擎** | DFM 是硬编码 if-else，没有裁决结构 | 规则带 `severity / actual·limit·unit / citation / suggested_action / blocking`，聚合四值（含 `invalid`），**工艺铁律成为可审计条款** |
| 3 | **Agent 输出信封** | 阶段脚本直接吃自由文本 | 强制 `{status, confidence, assumptions, warnings, citations, result, next_action}`，四值状态；空结论不得冒充 completed |
| 4 | **Skill Registry** | 能力埋在脚本里不可枚举 | `key@version` + 输入 Schema + 幂等 + 超时 + 允许列表，Agent 越权调用直接拒绝 |
| 5 | **工作流引擎** | 线性脚本 + 文本日志 | 持久化 DAG + 单调 `seq` 事件流 + SSE + 重试 + **人工审批门**；Harness 判 failed/invalid 时审批门**永不打开** |
| 6 | **几何真实性** | 图纸写"拔模≥1.8°"但实体是直壁（0°） | 几何真正带拔模，并在 **B-Rep 上实测**拔模角；拐角壁厚由"内角随形圆角 R−t"保证 |

## 二、目录结构

```text
hyperdesign2/
├── backend/app/
│   ├── cadir/            # CAD-IR 解释器（固定 Worker，白名单算子，禁止任意代码）
│   │   └── runner_freecad.py
│   ├── harness/          # Harness 规则引擎 + 规则包
│   │   ├── models.py     # 规则/裁决数据模型（四严重级、四聚合值）
│   │   ├── engine.py     # 受控算子求值（无 eval/exec）
│   │   └── rules/        # housing_cad.v1 / housing_mesh.v1 / housing_rib.v1
│   ├── agents/envelope.py# Agent 定义 + 输出信封校验 + 权限白名单
│   ├── skills/registry.py# Skill Registry + 内置技能（CAD 构建 / Harness / 轴强度）
│   └── workflow/         # 事件流（seq/SSE/JSONL）+ DAG 引擎（审批门/续跑/幂等）
├── examples/             # CAD-IR 示例（传感器外壳）
├── scripts/              # M0/M1/M2 门禁脚本
└── docs/
    ├── 00-competitive-analysis-and-v2-blueprint.md
    └── poc/              # 门禁报告（可复跑的证据）
```

## 三、门禁现状（全部可复跑）

```powershell
$py = "E:\hyperdesign\venvs\hd_brain\Scripts\python.exe"
& $py D:\hyperdesign2\scripts\m0_gate.py   # CAD-IR + 确定性 + 安全边界
& $py D:\hyperdesign2\scripts\m1_gate.py   # Harness + Agent 信封 + Skill Registry
& $py D:\hyperdesign2\scripts\m2_gate.py   # 工作流 + 事件流 + 审批门
```

| 阶段 | 门禁 | 结论 | 关键证据 |
|---|---|---|---|
| M0 | 8 项 | ✅ PASS | 两次重建体积偏差 **0.0000%**；B-Rep 合法、120.0×80.0×45.0mm、Z_min=0、体积 67,510.058mm³；**CAD 实测拔模 min=1.8°、垂直面=0**；`execute_script` 被 `CAD_FEATURE_UNSUPPORTED` 拒绝；STEP 388,735B |
| M1 | 13 项 | ✅ PASS | 3 个规则包 17 条规则、17 条带文档引用；真实 CAD 产物 `passed`；v1 白模被判 `failed`（命中 6 条，含薄壁 1.51mm<2.4mm 条款证据）；指标缺失判 `invalid`；非法算子 `eval` 在加载期即拒绝；Agent 越权调用被拒 |
| M2 | 8 项 | ✅ PASS | 合规数据跑到审批门 → approve 成功 / reject 失败；v1 白模在 n3 被否决、**审批节点 skipped**；非法 IR 在 n1 被拒、后续 skipped；12 条事件 seq 单调、可重放、补拉、落盘 JSONL |

## 四、核心不变量（写进代码，不靠自觉）

1. **智能体永不执行代码**：只能产出 CAD-IR；解释器算子白名单，未知算子直接失败。
2. **规则不可编程**：只有 `gte/lte/gt/lt/eq/neq/near/ratio_dev/between/exists/in_set/all_of/any_of/not`。
3. **没有测量就没有通过**：指标缺失 → `invalid`，绝不 `passed`。
4. **物理信号一票否决**：Harness `failed/invalid` → 阻断后续节点与审批门。
5. **审批只能人给**：引擎不存在自动放行路径。

## 五、路线图

| 阶段 | 内容 | 状态 |
|---|---|---|
| M0 | CAD-IR + 解释器 + 几何实测 | ✅ PASS（8 项） |
| M1 | Harness + Agent 信封 + Skill Registry | ✅ PASS（13 项） |
| M2 | 工作流引擎 + 事件流 + 审批门 | ✅ PASS（8 项） |
| M2b | FastAPI REST + SSE 接口层（单进程托管 Studio） | ✅ 已实现（health/presets/runs/events/stream/approve/artifacts） |
| M3 | Studio 前端（零构建、三栏 + 3D + 规则取证 + 审批） | ✅ PASS（9 项，真浏览器实测） |
| M4 | CAE（自包含数值有限元 + 理论解对标） | ✅ PASS（7 项） |
| M5 | 知识资产平台（入库/BM25+向量混合检索/引用溯源/RBAC） | ✅ PASS（10 项） |
| M6 | 参赛材料：申报书（按官方模板填写） | ✅ 已通过校验（20 页 / 6 表 / 3 配图 / 7,386 中文字） |
| M7 | 设计空间可行性判定 + 自动修复 + 跨产品族复用 | ✅ PASS（10 项） |
| M6b | 参赛材料：作品介绍 PDF 2.0、演示视频、代码仓库 | ✅ 已完成（PDF 6 页 / 视频 75 秒 / 仓库 82 文件） |

### 设计空间可行性与跨产品族复用（M7 新增）

- 模块：`backend/app/cadir/feasibility.py`（纯解析，不依赖几何内核）
- 约束：顶部内角半径、顶面平台、壁厚上下限、拔模下限、高厚比；每条带公式与依据
- 实测：外角 R=3.0 → 内角半径 **−0.82mm** 判不可行（真实内核同样报错 −0.740mm）→ 最小改动建议 **4.1mm** → 重建通过
- 复用：同一解释器构建 **CNC 支架**（80×40×44mm，18,789mm³），仅替换 IR 与规则包即通过；
  用注塑规则包判定同一支架则因拔模被判失败（证明规则与工艺绑定，非硬编码）

### 参赛材料（M6 产出）

| 材料 | 文件 |
|---|---|
| 申报书（官方模板填写） | `docs/申报书_HyperDesign2.0.docx` |
| 作品介绍 PDF（2.0） | `docs/作品介绍_HyperDesign2.0.pdf`（6 页） |
| 演示视频（2.0） | `docs/demo/HyperDesign2.0_Demo_1080p.mp4`（75 秒 / 1080p） |
| 材料清单与视频分镜 | `docs/poc/M6-MATERIALS.md` |
| 评测报告（合并本） | `docs/评测报告_HyperDesign2.0.pdf`（17 页，9 章） |
| 门禁报告 | `docs/poc/M0~M7、M9`（9 份） |
| 评审复现指南 | `docs/评审复现指南.md`（5 分钟自证） |
| 离线仓库快照 | `dist/hyperdesign2.bundle`（6.1MB，可 `git clone` 还原） |

构建脚本：`scripts/m6_build_submission.py`（申报书）、`scripts/m6_build_intro_pdf.py`（PDF）、`scripts/m6_build_video.py`（视频）。

### 申报书（M6 新增）

- 产物：`docs/申报书_HyperDesign2.0.docx`
- 做法：在官方模板上**就地填写**，保留封面/填写说明/页眉页脚；正文 中文仿宋_GB2312 + 西文 Times New Roman 五号
- 校验：`python scripts/m6_build_submission.py`（构建 + 18 项校验，含字数、外文全称、章节完整性）
- 需要参赛者确认后替换：团队名称、填报日期

### 知识资产平台（M5 新增）

| 能力 | 实现 | 实测 |
|---|---|---|
| 文档入库与条款切块 | 按句切分为「可独立引用的条款块」 | 7 篇文档 / 13 个条款块 |
| 检索 | BM25(k1=1.5,b=0.75) + 向量 + **RRF 融合** | 双通道命中注塑规范，RRF 分 0.0328 |
| 向量后端 | 默认**确定性 hashing（512 维，无需模型/GPU）**，可切 bge-m3 升级语义 | 相关查询 cos 0.17~0.33，无关查询 ≤0.12 |
| 引用溯源 | 每条命中带 文档 › 章节 › 原文 › 关键条款 | 示例：150mm / 2.4mm / 2.0mm / 1.44mm / 1.8° |
| RBAC | viewer/engineer/admin 三角色 | viewer 1 篇 / engineer 6 篇 / admin 7 篇 |
| 无证据拒答 | 门控：BM25>0 **且** cos≥0.15，否则 `found=false` | 无关查询与闲聊均拒答 → Agent 输出 `needs_input` |

### CAE 能力（M4 新增）

| 求解器 | 单元类型 | 对标 | 实测误差 |
|---|---|---|---|
| 悬臂梁（端部集中/均布载荷） | Euler-Bernoulli Hermite 三次单元 | δ=PL³/3EI、M=PL | **0.0000%**（等截面梁本为精确解） |
| 带孔板应力集中 | CST 常应变三角形 + 极坐标结构化网格 | Kirsch 解 Kt=3 | Kt=3.128（4.25%），网格加密 2.377→3.128 |

工作流已扩到 6 节点：`CAD-IR 构建 → CAD 几何 Harness → 网格物理 DFM Harness → CAE 有限元 → CAE Harness → 人工审批`；
技能清单 5 个（`cad.ir.build` / `harness.evaluate` / `calc.shaft.strength` / `cae.beam.solve` / `cae.hole.plate`）。

## 六、Studio 实测截图

- `docs/poc/shots/s2_compliant_3d.png`（合规链路：真实 STL + 包络 + 审批门）
- `docs/poc/shots/s4_rules_passed.png`（16 条规则取证全通过）
- `docs/poc/shots/s6_v1mesh_failed.png`（白模物理 DFM 被否决，含条款引用与建议动作）
- `docs/poc/shots/s7_badir_blocked.png`（恶意 CAD-IR 被解释器拒绝，后续节点跳过）

## 七、运行依赖与边界（重要）

- **2.0 平台层可独立运行**：CAD-IR 构建、准入规则、工作流、Studio、CAE、知识资产只依赖 Python 标准库 +
  `numpy`（CAE）/ `fastapi`+`uvicorn`（接口）/ 浏览器（前端），无需联网。
- **两条外部依赖（用于复现完整链路）**：
  1. 几何内核：需本机安装 FreeCAD（提供 `freecadcmd`），或通过环境变量 `HD_FREECAD_CMD` 指定路径；
  2. 网格物理门禁（M1/M2/M4 中的 housing_mesh 用例）：读取 1.0 版本产出的白模 DFM 指标（常量 `V1_MANIFEST`）；
     若只验证 2.0 自身能力，可跳过该用例或替换为任意合规数据。
- **生成式环节**（FLUX 概念图 / TRELLIS 三维重建）属于 1.0 能力层，2.0 通过数据契约对接，不重复实现。
- 全部门禁脚本的期望输出与报告结论记录在 `docs/poc/`。

## 八、快速验证

```powershell
$py = "E:\hyperdesign\venvs\hd_brain\Scripts\python.exe"   # 任意装有 numpy/fastapi 的 Python 3.11+
& $py scripts\m0_gate.py    # CAD-IR + 确定性 + 安全边界
& $py scripts\m1_gate.py    # Harness + Agent 信封 + Skill Registry
& $py scripts\m2_gate.py    # 工作流 + 事件流 + 审批门
& $py scripts\m4_gate.py    # CAE 与理论解对标
& $py scripts\m5_gate.py    # 知识资产（需先启动 API）
& $py backend\app\api\server.py    # http://127.0.0.1:8010 -> Studio
```
