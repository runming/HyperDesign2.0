# -*- coding: utf-8 -*-
"""M11：全材料数字一致性核对（零额外依赖：docx 用 zipfile 解析，PDF 用 pypdf）。"""
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import imageio_ffmpeg
from pypdf import PdfReader

DOCS = Path(r"D:\hyperdesign2\docs")


def docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
    text = re.sub(r"</w:p>", "\n", xml)
    text = re.sub(r"<[^>]+>", "", text)
    return text


def docx_counts(path: Path):
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
    tables = xml.count("<w:tbl>")
    images = len([n for n in zipfile.ZipFile(path).namelist() if n.startswith("word/media/")])
    return tables, images


def pdf_info(path: Path):
    r = PdfReader(str(path))
    return len(r.pages), "".join((p.extract_text() or "") for p in r.pages)


def video_seconds(path: Path):
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    p = subprocess.run([ff, "-i", str(path)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", p.stderr)
    if not m:
        return None
    return round(int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)), 1)


docx_path = DOCS / "申报书_HyperDesign2.0.docx"
doc_text = docx_text(docx_path)
tables, images = docx_counts(docx_path)
cn = len(re.findall(r"[\u4e00-\u9fff]", doc_text))

texts = {"申报书": doc_text}
info = [("申报书", f"中文 {cn} 字", f"表 {tables} / 图 {images} / {docx_path.stat().st_size/1024:.0f} KB")]

for name in ("作品介绍_HyperDesign2.0.pdf", "一页纸速览_HyperDesign2.0.pdf", "评测报告_HyperDesign2.0.pdf"):
    p = DOCS / name
    pages, text = pdf_info(p)
    texts[name.split("_")[0]] = text
    info.append((name.split("_")[0], f"{pages} 页", f"{p.stat().st_size/1024:.0f} KB"))

mp4 = DOCS / "demo" / "HyperDesign2.0_Demo_1080p.mp4"
info.append(("演示视频", f"{video_seconds(mp4)} 秒", f"{mp4.stat().st_size/1e6:.1f} MB"))

print("=== 材料尺寸 ===")
for a, b, c in info:
    print(f"  {a:10s} {b:16s} {c}")

print("\n=== 关键指标交叉核对 ===")
expect = {
    "七道": ["申报书", "作品介绍", "一页纸速览"],
    "评测报告": ["申报书", "作品介绍", "一页纸速览"],
    "3.128": ["申报书", "作品介绍", "一页纸速览"],
    "0.0000%": ["申报书", "作品介绍", "一页纸速览"],
    "0.82": ["申报书", "作品介绍"],
    "18,789": ["申报书", "作品介绍"],
}
ok = True
for key, where in expect.items():
    hit = [w for w in where if key in texts.get(w, "")]
    status = "OK" if len(hit) == len(where) else "MISSING"
    if status != "OK":
        ok = False
    print(f"  {key:12s} {status:8s} 命中 {hit}")

print("\n=== 旧口径残留 ===")
stale = [(n, bad) for n, t in texts.items() for bad in ("六道门禁", "7 份门禁", "表 3 端到端") if bad in t]
print("  无" if not stale else f"  {stale}")
if stale:
    ok = False

print("\nM11_CONSISTENCY:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
