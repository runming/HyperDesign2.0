from pathlib import Path

p = Path(r"D:\hyperdesign2\docs\poc\M6-MATERIALS.md")
s = p.read_text(encoding="utf-8")
s = s.replace("| 演示视频 | `docs/demo/HyperDesign2.0_Demo_1080p.mp4` | 1920×1080 / 30fps / **92 秒** / 2.9MB | 逐段抽帧核对 |",
              "| 演示视频 | `docs/demo/HyperDesign2.0_Demo_1080p.mp4` | 1920×1080 / 30fps / **122 秒 / 17 段** / 3.5MB | 逐段抽帧核对 |")
s = s.replace("| **评测报告** | `docs/评测报告_HyperDesign2.0.pdf` | **18 页 / 10 章（M0–M7、M9、M12）** | 溢出 0，章节结论全\"通过\" |",
              "| **评测报告** | `docs/评测报告_HyperDesign2.0.pdf` | **23 页 / 14 章（M0–M7、M9、M12、M14–M17）** | 溢出 0，章节结论全\"通过\" |")
s = s.replace("| 申报书 | `docs/申报书_HyperDesign2.0.docx` | **22 页 / 8,336 中文字 / 7 表 / 4 配图** / 仿宋GB2312 五号 | 18 项校验 + 逐页终检 |",
              "| 申报书 | `docs/申报书_HyperDesign2.0.docx` | **23 页 / 9,207 中文字 / 7 表 / 4 配图** / 仿宋GB2312 五号 | 18 项校验 + 逐页终检 |")
extra = """
## 六、AI 协作阶段新增（M14–M17）

| 能力 | 门禁 | 关键实测 |
|---|---|---|
| 交互式 AI 助手（前/中/后） | M14（10 项） | 壁厚 2.0 被拒并引用规范；圆角改 5.0 重建 passed；M4 底孔吸附 Ø3.3；定型冻结 |
| 网格→解析特征 + 误差证书 | M15（6 项） | 长方体三向尺寸误差 0.000mm；圆柱 R5 误差 0.000mm、覆盖 352.5° |
| 工程证据自动修复 | M16（6 项） | 立柱悬空（5 实体）→ 抬立柱高 1 轮通过；包络严重不符时不硬修 |
| DXF 尺寸+公差 | M17（6 项） | 四图层分工；IT9 自动查表；ezdxf 复核 AC1009 零错误 |

### 视频新增片段（第 13–16 段）

| 段 | 内容 |
|---|---|
| 13 | Studio「AI 助手」页签实测对话（真机截图） |
| 14 | 助手前中后期职责与越界拒绝 |
| 15 | 工程证据 → 自动修复（5 实体 → 1 轮通过） |
| 16 | DXF 工程图四图层与 IT9 公差标注 |
"""
if "## 六、AI 协作阶段新增" not in s:
    s = s.rstrip() + "\n" + extra
p.write_text(s, encoding="utf-8")
print("M6-MATERIALS 已更新：", len(s), "字符")
