# M1 门禁报告 · Harness + Agent 信封 + Skill Registry

- 时间：2026-11-10 01:38:12
- 结论：**通过**
- 规则包：`housing_cad.v1`（CAD 几何）/ `housing_mesh.v1`（网格物理）/ `housing_rib.v1`（加强筋）

| 门禁 | 检查项 | 结果 | 证据 |
|---|---|---|---|
| H1 | 规则包可加载且条款引用完整 | ✅ | 3 包 / 17 条规则 / 17 条带文档引用 |
| H2 | 真实 CAD-IR 产物通过 CAD 规则包 | ✅ | verdict=passed, 规则 10 条, 阻断失败=[] |
| H2b | 拔模规则取到实测值（非图纸标注） | ✅ | actual=1.8° vs limit=1.8°, citation=拔模斜度统一要求 ≥ 1.8° |
| H3 | v1 生成式白模被物理规则否决 | ✅ | verdict=failed, 命中=['dfm.draft.median', 'dfm.envelope.drift_y', 'dfm.envelope.drift_z', 'dfm.mesh.watertight', 'dfm.wall.p10', 'dfm.wall.p90'] |
| H3b | 薄壁证据可追溯（实测 1.51mm vs 2.4mm 条款） | ✅ | actual=1.51mm limit=2.4mm action=增加薄壁处料厚至 ≥2.4mm，或更换为更大壁厚的基体方案 |
| H4 | 规则方向正确（合规数据可通过） | ✅ | verdict=passed（对照：证明 H3 的失败来自数据而非规则写死） |
| H5 | 指标缺失判 invalid（绝不按通过处理） | ✅ | verdict=invalid, invalid 规则=['dfm.wall.p10', 'dfm.wall.p90', 'dfm.draft.median'] |
| H6 | 非法算子被拒绝（规则不能执行代码） | ✅ | evil.exec: 未注册的算子 'eval'（可用：all_of, any_of, between, eq, exists, gt, gte, in_set, lt, lte, near, neq, not, ratio_dev） |
| H7 | 加强筋 60% 规则（1.60 失败 / 1.40 通过） | ✅ | 1.60mm -> failed; 1.40mm -> passed |
| H8 | Agent 信封合法通过 / 非法拒绝 | ✅ | 合法 envelope citations=1；非法用例=全部正确拒绝 |
| H9 | Agent 越权调用被拒（白名单生效） | ✅ | Agent 'cad_agent' 无权调用技能 'phase5.raw_python'（允许：['cad.ir.*', 'harness.evaluate']） |
| H10 | Skill Registry 错误码与确定性计算 | ✅ | 未知技能=SKILL_NOT_FOUND / 缺字段=SKILL_INPUT_INVALID / σ_vm=137.737MPa n=2.577 |
| H11 | 技能串联（CAD 构建 -> Harness 判定） | ✅ | build.ok=True, verdict=passed, 耗时 2.1s |

## CAD 规则包逐条裁决（真实 CAD-IR 产物）

| 规则 | 级别 | 判定 | 实测 | 限值 | 单位 |
|---|---|---|---|---|---|
| cad.brep.valid | critical | passed | True | True | bool |
| cad.solid.single | error | passed | 1 | 1 |  |
| cad.envelope.x | error | passed | 120.0 | 120.0 | mm |
| cad.envelope.y | error | passed | 80.0 | 80.0 | mm |
| cad.envelope.z | error | passed | 45.0 | 45.0 | mm |
| cad.seat.flat | error | passed | 0.0 | 0.0 | mm |
| cad.draft.measured | error | passed | True | True |  |
| cad.draft.min | error | passed | 1.8 | 1.8 | deg |
| cad.draft.vertical_faces | error | passed | 0 | 0 |  |
| cad.volume.sane | warning | passed | 67510.058 | [1000.0, 5000000.0] | mm³ |

## 网格规则包逐条裁决（v1 生成式白模实测数据）

| 规则 | 级别 | 判定 | 实测 | 限值 | 建议动作 |
|---|---|---|---|---|---|
| dfm.mesh.watertight | error | failed | False | True | 运行 remesh / 补洞，或改用 CAD 实体回投白模 |
| dfm.wall.p10 | error | failed | 1.51 | 2.4 | 增加薄壁处料厚至 ≥2.4mm，或更换为更大壁厚的基体方案 |
| dfm.wall.p90 | error | failed | 5.99 | 4.5 | 掏空积料或改为筋板结构 |
| dfm.draft.median | error | failed | 0.84 | 1.8 | 重构造型或改用 CAD 实体（带拔模）作为最终交付 |
| dfm.envelope.drift_y | error | failed | 0.637125 | 0.08 | 以白模仅作造型锚点，改由 CAD-IR 按目标包络重建 |
| dfm.envelope.drift_z | error | failed | 3.292667 | 0.08 | 同上：白模降级为造型锚点 |

> 说明：规则只允许受控算子（`gte/lte/near/ratio_dev/between/in_set/all_of/any_of/not`），
> 未知算子直接抛 `HarnessConfigError`；指标缺失一律判 `invalid`，不会按通过处理。
