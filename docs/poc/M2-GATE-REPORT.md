# M2 门禁报告 · 工作流引擎（DAG / 事件流 / 审批门）

- 时间：2026-11-10 01:40:18
- 结论：**通过**
- 工作流：`housing.design-to-delivery@1.0.0`（4 节点：CAD 构建 → CAD Harness → 网格 DFM Harness → 人工审批）

| 门禁 | 检查项 | 结果 | 证据 |
|---|---|---|---|
| W1 | 工作流定义可加载、拓扑无环 | ✅ | housing.design-to-delivery@1.1.0 节点 ['n1_cad_build', 'n2_cad_harness', 'n3_mesh_dfm', 'n3b_cae', 'n3c_cae_harness', 'n4_human_approval'] |
| W2 | 合规数据跑到审批门 | ✅ | run=waiting_approval nodes={'n1_cad_build': 'ok', 'n2_cad_harness': 'ok', 'n3_mesh_dfm': 'ok', 'n3b_cae': 'ok', 'n3c_cae_harness': 'ok', 'n4_human_approval': 'waiting_approval'} |
| W3 | 审批通过后 run 成功 | ✅ | run=succeeded approver=张工 |
| W4 | 审批驳回后 run 失败 | ✅ | run=failed error=审批驳回：外观评审未过 |
| W5 | 白模物理 DFM 不达标即阻断（审批门永不打开） | ✅ | run=failed, n3=failed, 违规规则=['dfm.mesh.watertight', 'dfm.wall.p10', 'dfm.wall.p90', 'dfm.draft.median', 'dfm.envelope.drift_y', 'dfm.envelope.drift_z'], 审批节点=skipped |
| W6 | 非法 CAD-IR 在 n1 被拒且后续节点跳过 | ✅ | run=failed, n1=failed, n2=skipped, n4=skipped |
| W7 | 事件流单调/可重放/可补拉/落盘/SSE | ✅ | 16 事件, seq 1..16 单调=True, 补拉 7 条, jsonl=True |
| W8 | 幂等约束（重复 run_id / 已结束续跑均拒绝） | ✅ | 重复 run_id 被拒=True, 已结束续跑被拒=True |

## 事件流（合规数据这一跑）

| seq | 事件 | 节点 | 关键负载 |
|---|---|---|---|
| 1 | run.created | - | {"workflow": "housing.design-to-delivery", "version": "1.1.0"} |
| 2 | run.started | - | {} |
| 3 | node.started | n1_cad_build | {"type": "skill", "skill": "cad.ir.build"} |
| 4 | node.finished | n1_cad_build | {"status": "ok", "elapsed_ms": 2091} |
| 5 | node.started | n2_cad_harness | {"type": "harness", "skill": "backend/app/harness/rules/housing_cad.v1.json"} |
| 6 | node.finished | n2_cad_harness | {"status": "ok", "elapsed_ms": 4} |
| 7 | node.started | n3_mesh_dfm | {"type": "harness", "skill": "backend/app/harness/rules/housing_mesh.v1.json"} |
| 8 | node.finished | n3_mesh_dfm | {"status": "ok", "elapsed_ms": 0} |
| 9 | node.started | n3b_cae | {"type": "skill", "skill": "cae.hole.plate"} |
| 10 | node.finished | n3b_cae | {"status": "ok", "elapsed_ms": 303} |
| 11 | node.started | n3c_cae_harness | {"type": "harness", "skill": "backend/app/harness/rules/housing_cae.v1.json"} |
| 12 | node.finished | n3c_cae_harness | {"status": "ok", "elapsed_ms": 0} |
| 13 | run.approval_required | n4_human_approval | {"role": "mechanical_engineer", "title": "⑥ 人工验收（工程师签字放行）"} |
| 14 | run.approved | - | {"approver": "张工", "comment": "几何与工艺均达标，放行"} |
| 15 | run.started | - | {} |
| 16 | run.succeeded | - | {} |
