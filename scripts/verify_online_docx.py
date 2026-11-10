import json
import urllib.request

BASE = "https://api.github.com/repos/runming/HyperDesign2.0"


def get(path):
    req = urllib.request.Request(BASE + path,
                                 headers={"User-Agent": "hd-check", "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read())


commit = get("/commits/main")
print("最新提交:", commit["sha"][:7], "|", commit["commit"]["message"].splitlines()[0])
print("提交时间:", commit["commit"]["committer"]["date"])

for path in ("/contents/docs/申报书_HyperDesign2.0.docx", "/contents/docs/评测报告_HyperDesign2.0.pdf",
             "/contents/docs/demo/HyperDesign2.0_Demo_1080p.mp4"):
    try:
        f = get(path)
        print(f"{f['name']}: {f['size']/1024:.0f} KB  sha={f['sha'][:8]}")
    except Exception as exc:
        print(path, "ERR", exc)

# 下载 docx 检查正文是否含仓库链接（docx 是 zip，直接找 document.xml 中的字符串）
import io
import zipfile
req = urllib.request.Request(BASE + "/contents/docs/申报书_HyperDesign2.0.docx",
                            headers={"User-Agent": "hd-check", "Accept": "application/vnd.github.raw"})
with urllib.request.urlopen(req, timeout=60) as r:
    raw = r.read()
with zipfile.ZipFile(io.BytesIO(raw)) as z:
    xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
for key in ("github.com/runming/HyperDesign2.0", "HyperDesign2.0_Demo_1080p.mp4", "9232"):
    print(f"  线上申报书含 {key!r}:", key in xml)
