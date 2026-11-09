from pathlib import Path

# 1) 一页纸速览：材料清单补评测报告与复现指南
one = Path(r"D:\hyperdesign2\docs\一页纸速览_HyperDesign2.0.html")
s = one.read_text(encoding="utf-8")
old = "<li>门禁报告 7 份 + 界面实测截图 9 张</li>"
new = ("<li>评测报告（9 份门禁合并，17 页）+ 界面实测截图 9 张</li>\n"
       "      <li>评审复现指南（5 分钟可自证全部指标）</li>")
if old in s:
    s = s.replace(old, new)
    one.write_text(s, encoding="utf-8")
    print("一页纸：材料清单已补评测报告与复现指南")
else:
    print("一页纸：未找到锚点，跳过")

# 2) 作品介绍 PDF 源：在结尾说明处补评测报告
pdfsrc = Path(r"D:\hyperdesign2\docs\作品介绍_HyperDesign2.0.html")
s2 = pdfsrc.read_text(encoding="utf-8")
old2 = ("所有数字均由本机门禁脚本产出，原始报告见 <code>docs/poc/M0~M6-GATE-REPORT.md</code>；"
        "界面截图见 <code>docs/poc/shots/</code>；演示视频见 <code>docs/demo/</code>。")
new2 = ("所有数字均由本机门禁脚本产出；九份门禁报告已合并为《评测报告》"
        "（<code>docs/评测报告_HyperDesign2.0.pdf</code>，17 页），并附《评审复现指南》"
        "（<code>docs/评审复现指南.md</code>）说明如何 5 分钟内自行验证；"
        "界面截图见 <code>docs/poc/shots/</code>；演示视频见 <code>docs/demo/</code>。")
if old2 in s2:
    s2 = s2.replace(old2, new2)
    pdfsrc.write_text(s2, encoding="utf-8")
    print("作品介绍：结尾说明已补评测报告与复现指南")
else:
    print("作品介绍：未找到锚点，跳过")

# 3) README：材料清单补两行
rm = Path(r"D:\hyperdesign2\README.md")
s3 = rm.read_text(encoding="utf-8")
old3 = "| 门禁报告 | `docs/poc/M0~M6-GATE-REPORT.md`（7 份） |"
new3 = ("| 评测报告（合并本） | `docs/评测报告_HyperDesign2.0.pdf`（17 页，9 章） |\n"
        "| 门禁报告 | `docs/poc/M0~M7、M9`（9 份） |\n"
        "| 评审复现指南 | `docs/评审复现指南.md`（5 分钟自证） |")
if old3 in s3:
    s3 = s3.replace(old3, new3)
    rm.write_text(s3, encoding="utf-8")
    print("README：材料清单已更新")
else:
    print("README：未找到锚点（可能已更新过）")
