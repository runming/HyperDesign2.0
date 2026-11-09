# M3 门禁报告 · Studio 前端（真浏览器实测）

- 结论：**通过**
- 截图：`docs/poc/shots/`（9 张）

| 检查 | 结果 | 证据 |
|---|---|---|
| U1 页面加载并连上后端 | ✅ | 后端在线 · v2.0.0-m3 · 工作流 housing.design-to-delivery@1.1.0 · CAD 引擎 freecad_occt |
| U2 Skill 清单渲染 | ✅ | 6 个技能 |
| U3 运行到审批门 | ✅ | pill=waiting_approval |
| U4 节点状态渲染 | ✅ | n1_cad_build | n2_cad_harness | n3_mesh_dfm | n3b_cae | n3c_cae_harness | n4_human_approval |
| U5 三维包络 HUD | ✅ | 包络 (mm)  X 120.00   Y 80.00   Z 45.00 / 底面 Z = 0.000   质心 (0.0, 0.0, 22.5) / 单位 mm · 左键旋转 / 右键平移 / 滚轮缩放 |
| U6 规则取证表渲染 | ✅ | 19 行, 判定=['passed'] |
| U7 审批通过后状态 succeeded | ✅ | 审批结论：通过 · 审批人 工程师
几何与工艺达标，放行 |
| U8 白模失败剧本：规则表出现失败行且含条款引用 | ✅ | 6 行失败, 文档引用=True, 条款=True |
| U9 恶意 IR 被拒且后续节点跳过 | ✅ |  n1_cad_build | failed · 105 ms | NODE_FAILED: WorkflowError: SKILL_FAILED: 技能 'cad.ir.build' 返回 ok=false：[ |  n2_cad_harness | skipped · —  |
