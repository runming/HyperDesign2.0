# M0 门禁报告 · CAD-IR 解释器

- 时间：2026-11-10 01:26:48
- 引擎：freecad_occt 1.1.4（FreeCAD 自带 OpenCascade）
- IR：`examples/sensor_housing.m0.ir.json`（4 个特征，全部走白名单算子）
- 结论：**通过**

| 门禁 | 检查项 | 结果 | 证据 |
|---|---|---|---|
| G0 | 解释器可执行 | ✅ | 引擎 freecad_occt 1.1.4 |
| G1 | 两次重建确定性 | ✅ | 体积偏差 0.0000% / 包围盒最大偏差 0.0000 mm |
| G2 | B-Rep 合法且单实体 | ✅ | isValid=True, solids=1, shells=1, faces=220 |
| G3 | 包络与基准面 | ✅ | 120.0 × 80.0 × 45.0 mm, Z_min=0.0, 体积 67,510.058 mm³ |
| G4 | CAD 几何级拔模角 | ✅ | min=1.8°, median=1.8°, 垂直面=0, 侧壁面数=8 |
| G5 | 拒绝任意代码执行 | ✅ | ok=None, 错误包含 CAD_FEATURE_UNSUPPORTED=True |
| G6 | 算子均被引擎能力声明支持 | ✅ | 使用 ['add_boss_pattern', 'add_cylinder', 'create_tapered_box', 'shell']；缺失 [] |
| G7 | STEP/STL 产物落盘 | ✅ | STEP 388735 B / STL 1387378 B |

## 特征级耗时

| 特征 | 类型 | 耗时(ms) | 状态 |
|---|---|---|---|
| f1_base | create_tapered_box | 58 | ok |
| f2_shell | shell | 269 | ok |
| f3_bosses | add_boss_pattern | 1315 | ok |
| f4_led_window | add_cylinder | 134 | ok |

## 语义引用映射（业务层只用这些名字，不碰 Edge1/Face3）

```json
{
  "body": "body",
  "draft_inset_mm": 1.4142,
  "corner_radius_bottom": 4.5,
  "corner_radius_top": 3.0858,
  "top_span": [
    117.1716,
    77.1716
  ],
  "shell": "cavity_cut",
  "wall_mm": 2.4,
  "inner_corner_r_bottom": 2.13,
  "inner_corner_r_top": 0.76,
  "top_wall_z": 42.599,
  "warnings": [],
  "bosses": "count:4",
  "cut_cylinders": "count:1"
}
```

## 几何元数据

```json
{
  "is_valid": true,
  "volume_mm3": 67510.058,
  "surface_area_mm2": 57579.74,
  "bbox_mm": {
    "x": 120.0,
    "y": 80.0,
    "z": 45.0
  },
  "z_min": 0.0,
  "faces": 220,
  "edges": 627,
  "dfm": {
    "measured": true,
    "planar_side_faces": 8,
    "min_draft_deg": 1.8,
    "median_draft_deg": 1.8,
    "vertical_face_count": 0,
    "pull_direction": "+Z"
  }
}
```
