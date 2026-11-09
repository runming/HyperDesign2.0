# M12 规则引擎裁决质量评测

- 结论：**通过**
- 用例：20 个（应通过 8 / 应失败 10 / 应无效 2），覆盖 4 个规则包
- 准确率：**20/20 = 100.0%**；误报 0、漏报 0

## 分规则包

| 规则包 | 用例 | 判对 | 准确率 |
|---|---|---|---|
| housing_cad | 7 | 7 | 100% |
| housing_mesh | 7 | 7 | 100% |
| housing_cae | 4 | 4 | 100% |
| bracket_cad | 2 | 2 | 100% |

## 逐用例

| 规则包 | 用例 | 说明 | 期望 | 实得 | 结论 |
|---|---|---|---|---|---|
| housing_cad | 合规注塑件（基准） | 全部指标达标 | passed | passed | ✅ |
| housing_cad | X 向包络超差 3mm | 超出 ±1.5mm | failed | failed | ✅ |
| housing_cad | 底面未坐平 | Z_min=1.0 超出 ±0.01 | failed | failed | ✅ |
| housing_cad | 实体数为 2（未合并） | 应为单实体 | failed | failed | ✅ |
| housing_cad | 拔模角 1.2° 不足 | 低于 1.8° | failed | failed | ✅ |
| housing_cad | 存在零度直壁 2 处 | 卡模风险 | failed | failed | ✅ |
| housing_cad | 缺失实测拔模数据 | 无测量不得判通过 | invalid | invalid | ✅ |
| housing_mesh | 合规网格 | 全部达标 | passed | passed | ✅ |
| housing_mesh | 非水密网格 | 不可切片 | failed | failed | ✅ |
| housing_mesh | 薄壁 p10=1.51 | 低于 2.4mm | failed | failed | ✅ |
| housing_mesh | 肥厚 p90=5.2 | 缩水纹风险 | failed | failed | ✅ |
| housing_mesh | 拔模中位 0.84° | 低于 1.8° | failed | failed | ✅ |
| housing_mesh | Y 向包络漂移 64% | 严重失配 | failed | failed | ✅ |
| housing_mesh | 缺失 p10 壁厚 | 无测量不得判通过 | invalid | invalid | ✅ |
| housing_cae | 合规仿真结果 | 已对标且应力达标 | passed | passed | ✅ |
| housing_cae | 仿真未与理论解对标 | 结果不可信 | failed | failed | ✅ |
| housing_cae | Kt=5.0 偏离经典解 | 超出 [2,4] | failed | failed | ✅ |
| housing_cae | 孔边应力 31MPa 超许用 | 许用 25MPa | failed | failed | ✅ |
| bracket_cad | 合规铝合金支架 | 全部达标 | passed | passed | ✅ |
| bracket_cad | 支架 Z 向包络 48（应 44） | 超出 ±0.5mm | failed | failed | ✅ |

> 意义：规则引擎的价值不在于规则条数，而在于**判得对且不乱报**。本评测用人工标注用例给出误报/漏报，任何人可复跑 `scripts/m12_rule_eval.py` 复核。
