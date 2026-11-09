# -*- coding: utf-8 -*-
"""
M6 构建器：按《第三届"兴智杯"…申报模版》填写申报书。

做法：**在官方模板上就地填写**（保留封面、填写说明、标题层级与表格骨架），
正文统一设为 仿宋_GB2312 五号（10.5pt），小标题用黑体加粗，首行缩进 2 字符、1.5 倍行距。
"""
from __future__ import annotations

import copy
import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt, Cm, RGBColor
from docx.oxml import OxmlElement

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.materials import content as C  # noqa: E402

TEMPLATE = Path(r"D:\hyperdesign\_ref\submission_template.docx")
OUT = ROOT / "docs" / "申报书_HyperDesign2.0.docx"

BODY_FONT = "仿宋_GB2312"        # 中文正文字体
LATIN_FONT = "Times New Roman"   # 西文字体（必须单独指定，否则英文会被 CJK 字体替换成乱码/希腊字母）
BODY_SIZE = 10.5                 # 五号
HEAD_FONT = "黑体"
HEAD_SIZE = 11.0


# ----------------------------------------------------------------------------- 字体工具
def _set_run(run, font=BODY_FONT, size=BODY_SIZE, bold=False, color=None, latin=LATIN_FONT):
    """中文走 eastAsia 字体，西文走 ascii/hAnsi 字体——这是中文公文的正确排版方式。"""
    run.font.name = latin
    run.font.size = Pt(size)
    run.font.bold = bold
    if color:
        run.font.color.rgb = color
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    rFonts.set(qn("w:ascii"), latin)
    rFonts.set(qn("w:hAnsi"), latin)
    rFonts.set(qn("w:cs"), latin)
    rFonts.set(qn("w:eastAsia"), font)


def _fmt_para(p, indent_chars=2, spacing=1.5, align=WD_ALIGN_PARAGRAPH.JUSTIFY, space_after=0):
    pf = p.paragraph_format
    if indent_chars:
        pf.first_line_indent = Pt(BODY_SIZE * indent_chars)
    pf.line_spacing = spacing
    pf.space_after = Pt(space_after)
    pf.alignment = align


def _write_para(p, text, *, heading=False, indent=2):
    """清空段落并写入一段文本，返回该段落。"""
    for r in list(p.runs):
        r._element.getparent().remove(r._element)
    run = p.add_run(text)
    if heading:
        _set_run(run, font=HEAD_FONT, size=HEAD_SIZE, bold=True)
        _fmt_para(p, indent_chars=0, spacing=1.5, align=WD_ALIGN_PARAGRAPH.LEFT, space_after=3)
    else:
        _set_run(run, font=BODY_FONT, size=BODY_SIZE)
        _fmt_para(p, indent_chars=indent, spacing=1.5)
    return p


def _insert_after(anchor_p, text, *, heading=False):
    """在 anchor 之后插入新段落（克隆锚点以继承其段落样式）。"""
    new_el = copy.deepcopy(anchor_p._p)
    anchor_p._p.addnext(new_el)
    from docx.text.paragraph import Paragraph
    p = Paragraph(new_el, anchor_p._parent)
    _write_para(p, text, heading=heading)
    return p


def _add_table_after(anchor_p, spec, doc):
    header, rows = spec["header"], spec["rows"]
    tbl = doc.add_table(rows=1 + len(rows), cols=len(header))
    tbl.style = "Table Grid"
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    # 表题
    cap_el = copy.deepcopy(anchor_p._p)
    anchor_p._p.addnext(cap_el)
    from docx.text.paragraph import Paragraph
    cap = Paragraph(cap_el, doc)
    for r in list(cap.runs):
        r._element.getparent().remove(r._element)
    run = cap.add_run(spec["title"])
    _set_run(run, font=HEAD_FONT, size=9.5, bold=True)
    _fmt_para(cap, indent_chars=0, spacing=1.0, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2)
    cap._p.addnext(tbl._tbl)
    # 表头：加 tblHeader 使跨页时自动重复
    for j, h in enumerate(header):
        cell = tbl.rows[0].cells[j]
        cell.text = ""
        p = cell.paragraphs[0]
        run = p.add_run(h)
        _set_run(run, font=HEAD_FONT, size=9, bold=True)
        _fmt_para(p, indent_chars=0, spacing=1.0, align=WD_ALIGN_PARAGRAPH.CENTER)
        _shade(cell, "D9E2F3")
    trPr = tbl.rows[0]._tr.get_or_add_trPr()
    if trPr.find(qn("w:tblHeader")) is None:
        th = OxmlElement("w:tblHeader")
        trPr.append(th)
    for i, row in enumerate(rows, start=1):
        for j, val in enumerate(row):
            cell = tbl.rows[i].cells[j]
            cell.text = ""
            p = cell.paragraphs[0]
            run = p.add_run(str(val))
            _set_run(run, font=BODY_FONT, size=9)
            _fmt_para(p, indent_chars=0, spacing=1.0, align=WD_ALIGN_PARAGRAPH.LEFT)
    return tbl


def _shade(cell, hex_color):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcPr.append(shd)


def _add_image_after(anchor_p, img_path, caption, doc, width_cm=15.2):
    """在锚点后插入一张配图 + 图注（图注在图下方，9 磅居中）。"""
    from docx.text.paragraph import Paragraph
    p = Path(img_path)
    if not p.exists():
        return anchor_p
    # 图片段落
    img_el = copy.deepcopy(anchor_p._p)
    anchor_p._p.addnext(img_el)
    img_par = Paragraph(img_el, doc)
    for r in list(img_par.runs):
        r._element.getparent().remove(r._element)
    img_par.add_run().add_picture(str(p), width=Cm(width_cm))
    _fmt_para(img_par, indent_chars=0, spacing=1.0, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2)
    # 图注
    cap_el = copy.deepcopy(anchor_p._p)
    img_par._p.addnext(cap_el)
    cap = Paragraph(cap_el, doc)
    for r in list(cap.runs):
        r._element.getparent().remove(r._element)
    run = cap.add_run(caption)
    _set_run(run, font=BODY_FONT, size=9)
    _fmt_para(cap, indent_chars=0, spacing=1.0, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=6)
    return cap


def _set_cell_text(cell, text, *, font=BODY_FONT, size=10.5, bold=False):
    cell.text = ""
    p = cell.paragraphs[0]
    run = p.add_run(text)
    _set_run(run, font=font, size=size, bold=bold)
    _fmt_para(p, indent_chars=0, spacing=1.0, align=WD_ALIGN_PARAGRAPH.LEFT)


# ----------------------------------------------------------------------------- 主流程
def build():
    doc = Document(str(TEMPLATE))

    # ---- 表0：项目基础信息 ----
    t0 = doc.tables[0]
    _set_cell_text(t0.rows[0].cells[1], C.PROJECT_NAME, bold=True)
    _set_cell_text(t0.rows[1].cells[1], C.TRACK)
    _set_cell_text(t0.rows[2].cells[1], C.TOPIC)
    _set_cell_text(t0.rows[3].cells[1], C.TEAM)
    _set_cell_text(t0.rows[4].cells[1], C.DATE)

    # ---- 表1：核心技术（多选）----
    # 注意：不能用 id(cell._tc) 去重——lxml 代理对象被 GC 后 id 会复用，导致误判为同一单元格。
    # 用「集合持有元素」去重：元素被 set 引用后不会释放，身份才稳定。
    chosen = {"□多模态", "□深度学习", "□知识图谱"}
    t1 = doc.tables[1]
    seen = set()
    for row in t1.rows:
        for cell in row.cells:
            if cell._tc in seen:
                continue
            seen.add(cell._tc)
            txt = cell.text.strip()
            if txt in chosen:
                _set_cell_text(cell, "☑" + txt[1:])
            elif txt.startswith("□其他"):
                _set_cell_text(cell, C.TECH_OTHER, size=10)

    # ---- 表2：应用发展阶段（单选）----
    t2 = doc.tables[2]
    seen2 = set()
    for cell in t2.rows[0].cells:
        if cell._tc in seen2:
            continue
        seen2.add(cell._tc)
        if cell.text.strip() == "□应用示范阶段":
            _set_cell_text(cell, "☑应用示范阶段", bold=True)

    # ---- 应用行业及场景（Heading 2 后插入）----
    paras = doc.paragraphs
    anchor = next(p for p in paras if p.text.strip().startswith("应用行业及场景"))
    _insert_after(anchor, C.INDUSTRY_SCENE)

    # ---- 各小节正文 ----
    for anchor_idx, lines in sorted(C.SECTIONS.items()):
        # 锚点用文本匹配更稳（索引可能因前面的插入而偏移）
        pass

    # 按锚点原文定位（原始模板中的引导语），再逐段替换/插入
    guidance_map = {
        30: "从行业痛点、市场需求、场景价值性等方面阐述",
        32: "介绍项目（产品、解决方案等）的核心功能及主要应用场景",
        34: "从设计理念、核心技术路线、系统架构、软硬件部署等方面",
        36: "介绍项目（产品、解决方案等）的创新点",
        40: "分析项目（产品、解决方案等）的市场需求、趋势、容量",
        42: "分析项目（产品、解决方案等）的市场定位、潜在竞争者",
        44: "对项目（产品、解决方案等）当前的应用情况进行阐述",
        46: "分析项目（产品等）的社会效益",
        49: "1、项目（产品、解决方案等）实物或实际应用图片",
        50: "2、项目（产品、解决方案等）的评估验证证书",
        51: "3、其他相关说明或证明材料",
    }

    for anchor_idx, marker in guidance_map.items():
        lines = C.SECTIONS[anchor_idx]
        target = next((p for p in doc.paragraphs if marker in p.text), None)
        if target is None:
            raise RuntimeError(f"未找到锚点段落：{marker}")

        # 第一段替换原引导语，其余依次插入
        is_head = lines[0].startswith("## ")
        _write_para(target, lines[0][3:] if is_head else lines[0], heading=is_head)
        last = target
        for line in lines[1:]:
            is_head = line.startswith("## ")
            last = _insert_after(last, line[3:] if is_head else line, heading=is_head)

        specs = C.TABLES.get(anchor_idx)
        if specs:
            for spec in (specs if isinstance(specs, list) else [specs]):
                _add_table_after(last, spec, doc)
                last = doc.paragraphs[-1] if False else last   # 表后仍以正文段为锚点

        for img_path, caption in C.IMAGES.get(anchor_idx, []):
            last = _add_image_after(last, img_path, caption, doc)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(OUT))
    return OUT


# ----------------------------------------------------------------------------- 校验
def verify(path: Path):
    doc = Document(str(path))
    text = "\n".join(p.text for p in doc.paragraphs)
    for tb in doc.tables:
        for row in tb.rows:
            for cell in row.cells:
                text += "\n" + cell.text
    cn = len(re.findall(r"[\u4e00-\u9fff]", text))
    total = len(text)

    checks = []
    checks.append(("封面与填写说明保留", "填 写 说 明" in text and "第三届" in text))
    checks.append(("表格数量仍为 6（3 原表 + 3 数据表）", len(doc.tables) == 6))
    checks.append(("附录配图 ≥3 张", len(doc.inline_shapes) >= 3))
    checks.append(("项目名称已填", C.PROJECT_NAME[:12] in doc.tables[0].rows[0].cells[1].text))
    checks.append(("主题赛已填", C.TRACK in doc.tables[0].rows[1].cells[1].text))
    checks.append(("核心技术勾选 ≥3 项", sum(1 for tb in doc.tables for row in tb.rows
                                              for cell in row.cells if "☑" in cell.text) >= 4))
    checks.append(("发展阶段勾选", "☑应用示范阶段" in text))
    for key, marker in [("背景及意义", "行业痛点：生成式人工智能"), ("主要场景", "场景一：注塑结构件"),
                        ("实现方案", "把模型关进工程的笼子"), ("创新点", "创新点一"),
                        ("市场分析", "需求侧"), ("商业模式", "市场定位"),
                        ("应用情况", "当前状态"), ("社会效益", "对制造业数字化"),
                        ("附录", "实物或实际应用图片"), ("参考文献", "arXiv:2412.01506")]:
        checks.append((f"小节内容：{key}", marker in text))
    checks.append(("字数在 6000~30000 之间", 6000 <= cn <= 30000))
    checks.append(("外文全称展开（至少 6 处）",
                   sum(1 for k in ["Computer-Aided Design", "Design for Manufacturing", "Boundary Representation",
                                   "Retrieval-Augmented", "Direct Preference Optimization", "Finite Element"]
                       if k in text) >= 6))

    print("=== 申报书校验 ===")
    ok = True
    for name, passed in checks:
        print(("  PASS " if passed else "  FAIL ") + name)
        ok = ok and passed
    print(f"  中文字数：{cn} ／ 总字符：{total}")
    print(f"  段落数：{len(doc.paragraphs)} ／ 表格数：{len(doc.tables)}")
    print("M6_DOCX:", "PASS" if ok else "FAIL")
    return ok, cn


if __name__ == "__main__":
    out = build()
    print(f"已生成：{out}（{out.stat().st_size/1024:.1f} KB）")
    ok, cn = verify(out)
    sys.exit(0 if ok else 1)
