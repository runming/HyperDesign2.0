from pathlib import Path

# 更新材料清单里的最终尺寸
p = Path(r"D:\hyperdesign2\docs\poc\M6-MATERIALS.md")
s = p.read_text(encoding="utf-8")
s = s.replace("| 申报书 | `docs/申报书_HyperDesign2.0.docx` | 20 页 / 8,029 中文字 / 7 表 / 3 配图 / 仿宋GB2312 五号 | 18 项校验 + 渲染核对 |",
              "| 申报书 | `docs/申报书_HyperDesign2.0.docx` | **22 页 / 8,336 中文字 / 7 表 / 4 配图** / 仿宋GB2312 五号 | 18 项校验 + 逐页终检 |")
s = s.replace("| **评测报告** | `docs/评测报告_HyperDesign2.0.pdf` | **17 页 / 9 章（M0–M7、M9 原文合并）** | 溢出 0，章节结论全\"通过\" |",
              "| **评测报告** | `docs/评测报告_HyperDesign2.0.pdf` | **18 页 / 10 章（M0–M7、M9、M12）** | 溢出 0，章节结论全\"通过\" |")
s = s.replace("| 代码仓库 | `D:\\hyperdesign2` | 112 文件 / bundle 6.1MB | 门禁脚本可复跑 |",
              "| 代码仓库 | `D:\\hyperdesign2` | git 已提交 / bundle 就绪 | 门禁脚本可复跑 |")
p.write_text(s, encoding="utf-8")
print("M6-MATERIALS 已更新")

# README 同步
r = Path(r"D:\hyperdesign2\README.md")
t = r.read_text(encoding="utf-8")
t = t.replace("`docs/评测报告_HyperDesign2.0.pdf`（17 页，9 章）", "`docs/评测报告_HyperDesign2.0.pdf`（18 页，10 章）")
t = t.replace("`docs/poc/M0~M7、M9`（9 份）", "`docs/poc/M0~M7、M9、M12`（10 份）")
if "M13" not in t:
    t = t.replace("| 评审复现指南 | `docs/评审复现指南.md`（5 分钟自证） |",
                  "| 评审复现指南 | `docs/评审复现指南.md`（5 分钟自证） |\n"
                  "| 终检报告 | `docs/poc/M13-FINAL-AUDIT.md`（逐页空白页检查） |")
r.write_text(t, encoding="utf-8")
print("README 已更新")
