# -*- coding: utf-8 -*-
"""
M10：把 9 份门禁报告合并成一份《评测报告》PDF（模板附录 2 要求"评测报告"）。

流程：Markdown（轻量转换）→ HTML（统一排版 + 目录 + 结论汇总）→ Playwright 打印 A4 PDF。
只处理本仓库报告用到的语法：# 标题、## 小节、| 表格 |、- 列表、> 引用、``` 代码块、**加粗**、`行内代码`。
"""
import html
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

DOCS = Path(r"D:\hyperdesign2\docs")
POC = DOCS / "poc"
OUT_HTML = DOCS / "评测报告_HyperDesign2.0.html"
OUT_PDF = DOCS / "评测报告_HyperDesign2.0.pdf"

# 顺序即目录顺序
REPORTS = [
    ("M0", "几何中间表示与解释器", "M0-GATE-REPORT.md"),
    ("M1", "准入规则引擎与智能体信封", "M1-GATE-REPORT.md"),
    ("M2", "工作流引擎、事件流与审批门", "M2-GATE-REPORT.md"),
    ("M3", "交互界面（真浏览器实测）", "M3-GATE-REPORT.md"),
    ("M4", "数值仿真（CAE）与理论解对标", "M4-GATE-REPORT.md"),
    ("M5", "知识资产平台", "M5-GATE-REPORT.md"),
    ("M6", "参赛材料构建（申报书）", "M6-GATE-REPORT.md"),
    ("M7", "设计空间可行性与跨产品族复用", "M7-GATE-REPORT.md"),
    ("M9", "平台层端到端性能", "M9-PERF.md"),
    ("M12", "规则引擎裁决质量评测", "M12-RULE-EVAL.md"),
]


def inline(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return text


def md_to_html(md: str) -> str:
    lines = md.splitlines()
    out, i = [], 0
    in_code = False
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("```"):
            if not in_code:
                out.append("<pre>")
                in_code = True
            else:
                out.append("</pre>")
                in_code = False
            i += 1
            continue
        if in_code:
            out.append(html.escape(line))
            i += 1
            continue
        if re.match(r"^\|\s*-{2,}", line.strip()) or re.match(r"^\|[\s:|-]+\|$", line.strip()):
            i += 1
            continue
        if line.strip().startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not re.match(r"^[\s:|-]+$", "|".join(cells)):
                    rows.append(cells)
                i += 1
            if rows:
                out.append("<table>")
                out.append("<tr>" + "".join(f"<th>{inline(c)}</th>" for c in rows[0]) + "</tr>")
                for r in rows[1:]:
                    out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
                out.append("</table>")
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{inline(m.group(2))}</h{lvl}>")
            i += 1
            continue
        if line.strip().startswith("- "):
            out.append("<ul>")
            while i < len(lines) and lines[i].strip().startswith("- "):
                out.append(f"<li>{inline(lines[i].strip()[2:])}</li>")
                i += 1
            out.append("</ul>")
            continue
        if line.strip().startswith(">"):
            out.append(f"<blockquote>{inline(line.strip()[1:].strip())}</blockquote>")
            i += 1
            continue
        if not line.strip():
            i += 1
            continue
        out.append(f"<p>{inline(line.strip())}</p>")
        i += 1
    if in_code:
        out.append("</pre>")
    return "\n".join(out)


CSS = """
@page { size: A4; margin: 16mm 14mm 14mm 14mm; }
body { font-family: "Microsoft YaHei", "PingFang SC", sans-serif; font-size: 9.6pt; line-height: 1.6;
       color: #16222c; margin: 0; }
h1 { font-size: 17pt; margin: 0 0 6px; color: #0d1b2a; }
h2 { font-size: 13pt; margin: 18px 0 6px; padding: 5px 9px; background: #0d1b2a; color: #fff;
     page-break-after: avoid; border-radius: 3px; }
h3 { font-size: 10.6pt; margin: 12px 0 4px; color: #0a5f8f; page-break-after: avoid; }
h4 { font-size: 9.8pt; margin: 9px 0 3px; color: #0a5f8f; }
p { margin: 4px 0; text-align: justify; }
ul { margin: 3px 0; padding-left: 18px; }
li { margin: 2px 0; }
table { width: 100%; border-collapse: collapse; margin: 6px 0 8px; font-size: 8.8pt; page-break-inside: auto; }
th { background: #e8f0f7; text-align: left; padding: 4px 6px; border: 1px solid #c9d8e4; }
td { padding: 3px 6px; border: 1px solid #dbe6ee; vertical-align: top; word-break: break-word; }
code { font-family: Consolas, monospace; background: #f0f4f7; padding: 0 3px; border-radius: 2px; font-size: 8.6pt; }
pre { background: #0d1b2a; color: #d7e6f2; padding: 8px 10px; border-radius: 4px; font-size: 8pt;
      white-space: pre-wrap; word-break: break-all; }
blockquote { border-left: 4px solid #00a8ff; background: #f4fafd; margin: 6px 0; padding: 5px 10px; color: #2a4457; }
.cover { text-align: center; padding-top: 90px; }
.cover h1 { font-size: 24pt; }
.cover .sub { color: #4a5c6b; font-size: 11pt; margin: 8px 0 30px; }
.cover .meta { font-size: 9.4pt; color: #61727f; line-height: 2; }
.badge { display: inline-block; border: 1px solid #2ecc71; color: #1e8e4a; border-radius: 10px;
         padding: 1px 8px; font-size: 8.6pt; margin: 0 3px; }
.pagebreak { page-break-before: always; }
.toc { font-size: 10pt; line-height: 1.9; }
.toc a { color: #0a5f8f; text-decoration: none; }
"""


def main():
    body_parts = []
    # 封面
    body_parts.append(f"""
<div class="cover">
  <h1>HyperDesign 2.0 评测报告</h1>
  <div class="sub">门禁脚本可复跑 · 结论可追溯 · 数据可复算</div>
  <div><span class="badge">M0 几何</span><span class="badge">M1 准入</span><span class="badge">M2 工作流</span>
  <span class="badge">M3 界面</span><span class="badge">M4 仿真</span><span class="badge">M5 知识</span>
  <span class="badge">M6 材料</span><span class="badge">M7 可行性与复用</span><span class="badge">M9 性能</span></div>
  <div class="meta" style="margin-top:36px">
    被测系统：HyperDesign 2.0（v2.0.0-m3）<br/>
    测试环境：单台工作站（Windows + FreeCAD 1.1 + Python 3.12，无外部服务依赖）<br/>
    测试方式：每个阶段独立脚本 + 真浏览器实测，全部可复跑<br/>
    报告构成：9 份门禁报告原文合并，未做删改
  </div>
</div>
<div class="pagebreak"></div>
""")
    # 目录 + 结论汇总
    toc = ['<h2>目录与总体结论</h2>', '<div class="toc">']
    summary_rows = []
    for mid, title, fname in REPORTS:
        path = POC / fname
        if not path.exists():
            continue
        head = path.read_text(encoding="utf-8")[:600]
        concl = "未通过" if "未通过" in head else ("通过" if "通过" in head else "—")
        toc.append(f'<div>· <b>{mid}</b> {title} —— <span style="color:{"#1e8e4a" if concl == "通过" else "#c0392b"}">{concl}</span></div>')
        summary_rows.append((mid, title, concl))
    toc.append("</div>")
    body_parts.append("\n".join(toc))

    # 各报告
    for mid, title, fname in REPORTS:
        path = POC / fname
        if not path.exists():
            continue
        md = path.read_text(encoding="utf-8")
        md = re.sub(r"^#\s+.*$", "", md, count=1, flags=re.M)   # 去掉原一级标题，用统一标题
        body_parts.append(f'<div class="pagebreak"></div><h1>{mid} · {title}</h1>')
        body_parts.append(md_to_html(md))

    html_doc = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8" />
<title>HyperDesign 2.0 评测报告</title><style>{CSS}</style></head><body>
{''.join(body_parts)}
</body></html>"""
    OUT_HTML.write_text(html_doc, encoding="utf-8")

    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, channel="chrome", args=["--no-sandbox"])
        p = b.new_page(viewport={"width": 800, "height": 1130})
        p.goto(OUT_HTML.as_uri(), wait_until="load", timeout=60_000)
        p.wait_for_timeout(600)
        info = p.evaluate("""() => { const w = document.documentElement.clientWidth; let n = 0;
            document.querySelectorAll('body *').forEach(el => { const r = el.getBoundingClientRect();
              if (r.width > 0 && r.right > w + 1.5) n++; });
            return { w, scroll: document.documentElement.scrollWidth, n }; }""")
        p.pdf(path=str(OUT_PDF), format="A4", print_background=True,
              margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
              prefer_css_page_size=True)
        b.close()

    raw = OUT_PDF.read_bytes()
    pages = raw.count(b"/Type /Page") - raw.count(b"/Type /Pages")
    print(f"评测报告：{OUT_PDF}  {len(raw)/1024:.1f} KB  {pages} 页  溢出={info['n']}  章节={len(summary_rows)}")
    for mid, title, concl in summary_rows:
        print(f"  {mid:3s} {title[:26]:28s} {concl}")
    return 0 if info["n"] == 0 and pages >= 8 else 1


if __name__ == "__main__":
    raise SystemExit(main())
