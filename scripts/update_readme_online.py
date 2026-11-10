from pathlib import Path

p = Path(r"D:\hyperdesign2\README.md")
s = p.read_text(encoding="utf-8")
head = "# HyperDesign 2.0\n\n"
banner = """> **在线仓库**：https://github.com/runming/HyperDesign2.0 （main）
> **演示视频**：https://github.com/runming/HyperDesign2.0/blob/main/docs/demo/HyperDesign2.0_Demo_1080p.mp4
> **选题**：第三届"兴智杯"全国人工智能创新应用大赛 · 解决方案赛 · 行业赋能

"""
if "在线仓库**：https://github.com/runming/HyperDesign2.0" not in s:
    if s.startswith("# HyperDesign 2.0"):
        s = s.replace(head, head + banner, 1)
    else:
        s = banner + s
    p.write_text(s, encoding="utf-8")
    print("README 已加在线链接横幅")
else:
    print("已存在，跳过")
