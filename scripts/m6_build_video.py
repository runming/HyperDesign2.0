# -*- coding: utf-8 -*-
"""
M6：HyperDesign 2.0 演示视频合成
- 数据卡：PIL 生成（内容取真实门禁数据）
- 界面段：复用 Studio 真机截图（docs/poc/shots）
- 合成：ffmpeg（imageio-ffmpeg 提供二进制）→ 1920x1080 H.264
"""
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
CARDS = DOCS / "demo" / "cards"
SHOTS = DOCS / "poc" / "shots"
OUT = DOCS / "demo" / "HyperDesign2.0_Demo_1080p.mp4"
TMP = DOCS / "demo" / "_seg"
for d in (CARDS, TMP):
    d.mkdir(parents=True, exist_ok=True)

W, H = 1920, 1080
BG, FG, ACCENT, GREEN, DIM, RED, YELLOW = ((15, 18, 22), (225, 232, 238), (0, 168, 255),
                                           (46, 204, 113), (150, 168, 185), (231, 76, 60), (241, 196, 15))
FONTS = [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf", r"C:\Windows\Fonts\Deng.ttf"]


def font(size, bold=False):
    for f in FONTS:
        if Path(f).exists():
            try:
                return ImageFont.truetype(f, size)
            except Exception:
                pass
    return ImageFont.load_default()


def card(name, title, lines, footer=""):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 7], fill=ACCENT)
    d.text((110, 80), title, font=font(52, True), fill=ACCENT)
    y = 200
    for text, color, size in lines:
        d.text((120, y), text, font=font(size), fill=color)
        y += int(size * 1.55)
    if footer:
        d.text((120, H - 90), footer, font=font(26), fill=DIM)
    p = CARDS / f"{name}.png"
    img.save(p)
    return p


def build_cards():
    out = []
    out.append(card("c01_title", "HyperDesign 2.0", [
        ("面向制造落地的自进化工业设计智能体平台", FG, 40),
        ("", DIM, 20),
        ("1.0 证明了「概念图 → 白模 → 实体 → 国标图纸」能跑通", DIM, 30),
        ("2.0 把它装进可审计、可观测、可验收的工程骨架", FG, 34),
        ("", DIM, 20),
        ("六道门禁 · 全部可复跑 · 全部有实测数字", GREEN, 32),
    ], "示范产品：工业无线振动/温湿度三合一传感器外壳 120×80×45mm"))

    out.append(card("c02_why", "为什么需要 2.0：三个结构性缺口", [
        ("缺口一 执行不可审计 —— 模型直接写脚本并在内核执行", RED, 32),
        ("       2.0：受控几何中间表示，执行体是固定白名单解释器，execute_script 一律拒绝", GREEN, 28),
        ("", DIM, 18),
        ("缺口二 结论不可追溯 —— 只有布尔结论，说不出依据", RED, 32),
        ("       2.0：规则带规范文档、条款原文、实测值/限值、建议动作", GREEN, 28),
        ("", DIM, 18),
        ("缺口三 过程不可观测 —— 线性脚本 + 文本日志", RED, 32),
        ("       2.0：持久化 DAG、事件流序号、SSE、人工审批门、断点续跑", GREEN, 28),
    ]))

    out.append(card("c03_arch", "六层架构 · 五类抽象", [
        ("L5 交互层  Studio：工作流 / 三维 / 规则取证 / 知识库 / 审批", FG, 28),
        ("L4 编排层  Workflow Engine（DAG · 事件流 · SSE · 审批门）", FG, 28),
        ("L3 约束层  Harness 规则引擎 + Skill Registry（允许列表）", FG, 28),
        ("L2 表示层  CAD-IR（参数/特征/语义引用/能力声明/禁止任意代码）", ACCENT, 28),
        ("L1 能力层  检索 · 概念发散 · 三维重建 · 毫米对齐 · 测厚 · 仿真 · 制图", FG, 28),
        ("L0 资产层  知识文档 · 设计版本 · 事件审计 · 八级关联标识", FG, 28),
        ("", DIM, 16),
        ("Agent 只决策 / Skill 只执行 / Harness 只裁决 / IR 只承载数据", YELLOW, 26),
    ]))

    out.append(card("c04_gates", "六道工程门禁（全部 PASS）", [
        ("M0 几何表示与解释器   8/8   体积偏差 0.0000% · 包络 120.0×80.0×45.0mm · 拔模 1.8°", GREEN, 28),
        ("M1 准入规则与智能体 13/13   17 条规则带条款引用 · 缺失指标判 invalid", GREEN, 28),
        ("M2 工作流与事件流     8/8   物理不通过 → 审批门 skipped · 事件序号单调", GREEN, 28),
        ("M3 交互界面（真浏览器） 9/9   HUD 实测 120.00×80.00×45.00mm · Z=0.000", GREEN, 28),
        ("M4 数值仿真           7/7   梁误差 0.0000% · 圆孔 Kt=3.128（理论 3.0）", GREEN, 28),
        ("M5 知识资产           10/10  角色可见 1/6/7 篇 · 无证据即拒答", GREEN, 28),
    ], "每道门禁都有独立脚本与报告，任何人可在本机复跑"))

    out.append(card("c05_cae", "自研有限元（零外部依赖）", [
        ("梁单元：Euler-Bernoulli + Hermite 三次形函数", FG, 30),
        ("        端部集中载荷 δ=0.16383mm（解析 0.16383）→ 误差 0.0000%", GREEN, 28),
        ("平面应力：CST 常应变三角形 + 极坐标结构化网格", FG, 30),
        ("        圆孔应力集中 Kt = 3.128（Kirsch 解 3.0，误差 4.25%）", GREEN, 28),
        ("        网格加密：2.377 → 3.128 → 3.121，单调收敛", DIM, 26),
        ("", DIM, 16),
        ("仿真结果进入准入规则：未与理论解对标的结果不得作为设计依据", YELLOW, 26),
    ]))

    out.append(card("c06_end", "交付与落地", [
        ("申报书：按官方模板填写，仿宋GB2312 五号，18 页 / 7,038 中文字", FG, 28),
        ("作品介绍 PDF：6 页，含六层架构、六道门禁、对比与已知限制", FG, 28),
        ("代码仓库：73 个文件 / 4.05MB，含示例、规则包、门禁脚本", FG, 28),
        ("单机 16GB 可跑 · 全离线 · 零构建前端 · STEP/DXF/PDF 标准交付", GREEN, 28),
        ("", DIM, 16),
        ("已知限制如实披露：白模不可直接制造、进化需样本量、部分组件替换", DIM, 24),
    ]))
    return out


SEGMENTS = []   # (path, seconds)


def film(cards):
    S = SEGMENTS
    S.append((cards[0], 6.0))
    S.append((cards[1], 9.0))
    S.append((cards[2], 8.0))
    S.append((SHOTS / "s2_compliant_3d.png", 7.0))     # 三维 + 工作流
    S.append((SHOTS / "s4_rules_passed.png", 7.0))     # 规则取证 + CAE
    S.append((SHOTS / "s6_v1mesh_failed.png", 6.0))    # 物理否决
    S.append((SHOTS / "s8_kb_search.png", 6.0))        # 知识检索
    S.append((SHOTS / "s9_kb_rbac.png", 5.0))          # RBAC + 拒答
    S.append((cards[3], 8.0))
    S.append((cards[4], 7.0))
    S.append((cards[5], 6.0))
    return S


def main():
    cards = build_cards()
    segs = film(cards)
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    scale = ("scale=1920:1080:force_original_aspect_ratio=decrease,"
             "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x0f1216,setsar=1")
    files = []
    for i, (img, dur) in enumerate(segs, 1):
        if not Path(img).exists():
            print("MISSING", img)
            return 1
        seg = TMP / f"seg_{i:02d}.mp4"
        vf = f"{scale},fade=t=in:st=0:d=0.35,fade=t=out:st={max(dur-0.35,0.1):.2f}:d=0.35,format=yuv420p"
        r = subprocess.run([ff, "-y", "-loop", "1", "-t", f"{dur:.2f}", "-i", str(img), "-vf", vf,
                            "-r", "30", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                            "-pix_fmt", "yuv420p", str(seg)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            print("FFMPEG_FAIL", Path(img).name, r.stderr[-500:])
            return 1
        files.append(seg)
        print(f"  seg {i:02d} {Path(img).name:28s} {dur:4.1f}s ok")
    lst = TMP / "list.txt"
    lst.write_text("\n".join(f"file '{s.as_posix()}'" for s in files), encoding="utf-8")
    r = subprocess.run([ff, "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(OUT)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print("CONCAT_FAIL", r.stderr[-500:])
        return 1
    total = sum(d for _, d in segs)
    print(f"\nVIDEO_OK {OUT}  {OUT.stat().st_size/1e6:.1f} MB  {total:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
