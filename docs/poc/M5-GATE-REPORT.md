# M5 门禁报告 · 知识资产平台

- 结论：**通过**
- 检索栈：BM25(k1=1.5,b=0.75) + 向量（hashing-ngram-512）+ RRF 融合 + RBAC 过滤 + 条款级引用

| 门禁 | 结果 | 证据 |
|---|---|---|
| K1 文档入库与切块 | ✅ | 7 份文档 / 13 个条款块 / 向量模型 hashing-ngram-512 |
| K2 BM25 单路检索 | ✅ | top1=内部注塑工艺规范_v2.4.pdf / 片段=我司二号车间海天注塑机加工 PC+ABS 材质工业外壳时，凡外壳最大跨度超过 150… |
| K3 向量单路检索 | ✅ | top5 文档=['spec_injection_v24']（hashing 向量无语义能力，仅保证确定性） |
| K4 混合 RRF 融合 | ✅ | top1=内部注塑工艺规范_v2.4.pdf / 命中通道=['bm25', 'vector'] / score=0.032787 |
| K5 引用溯源完整 | ✅ | 1 条命中均带 文档/章节/原文/条款；示例条款=['150mm', '2.4mm', '2.0mm', '1.44mm', '1.8°'] |
| K6 RBAC 角色隔离 | ✅ | 可见文档数 viewer=1/engineer=6/admin=7；viewer 查工艺规范=False（应 False）/ engineer 查规范=True（应 True）/ engineer 查成本=False（应 False）/ admin 查成本=True（应 True） |
| K7 无证据即拒答 | ✅ | 无关查询 found=False（max cos=0.0585）/闲聊 found=False（max cos=0.1209）—— Agent 据此输出 needs_input |
| K8 切块与分词质量 | ✅ | 切块=['壁厚必须设定为 2.4mm。加强筋不超过 1.44mm。', '拔模斜度 ≥ 1.8°。'] / 分词含中文二元组=True / 条款抽取=['2.4mm', '1.44mm', '1.8°'] |
| K9 知识库页签实测（检索 + 引用展示） | ✅ | 结果含规范名与 2.4mm 条款 |
| K10 RBAC 在界面生效（访客→无证据提示） | ✅ | 访客角色被 RBAC 拦截，界面提示 Agent 应输出 needs_input |

## 知识库清单

| 文档 | 来源类型 | 版本 | 可见角色 | 条款块 |
|---|---|---|---|---|
| 内部注塑工艺规范_v2.4.pdf | pdf | v2.4 | engineer/admin | 2 |
| 钣金折弯展开标准_2025.docx | docx | 2025 | engineer/admin | 1 |
| 工程文件_Phase2_产品设计任务书.docx | docx | v1.0 | viewer/engineer/admin | 2 |
| 工程文件_Phase5_CAD铁律.docx | docx | v1.0 | engineer/admin | 2 |
| 工程文件_Phase6_制图规范.docx | docx | v1.0 | engineer/admin | 3 |
| 工程文件_Phase7_DFM双层评判.docx | docx | v1.0 | engineer/admin | 2 |
| 供应商报价与成本基线_2026Q3（仅管理者可见） | xlsx | 2026Q3 | admin | 1 |

## 示例检索结果（engineer / 混合检索）

```json
[
  {
    "chunk_id": "spec_injection_v24#1",
    "doc_id": "spec_injection_v24",
    "doc_title": "内部注塑工艺规范_v2.4.pdf",
    "section": "§1",
    "quote": "我司二号车间海天注塑机加工 PC+ABS 材质工业外壳时，凡外壳最大跨度超过 150mm 的产品，标准名义壁厚必须设定为 2.4mm（严禁采用通用 2.0mm）。内侧加强筋厚度不得超过名义壁厚的 60%（即 1.44mm），否则极易产生表面缩水纹。拔模斜度统一要求 ≥ 1.8°。",
    "clauses": [
      "150mm",
      "2.4mm",
      "2.0mm",
      "1.44mm",
      "1.8°"
    ],
    "score": 0.032787,
    "channels": [
      "bm25",
      "vector"
    ]
  }
]
```

> 说明：默认向量为确定性 hashing（无模型、离线可用），语义能力需 bge-m3；
> 检索结果一律带「文档 › 章节 › 原文 › 关键条款」，供 Harness 引用与前端展示。
