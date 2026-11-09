import json
import urllib.request

BASE = "http://127.0.0.1:8010"


def post(path, payload):
    req = urllib.request.Request(BASE + path,
                                 data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())


turns = [
    "帮我设计一个 120×80×45 的 PC+ABS 传感器外壳",
    "把壁厚改成 2.0",
    "圆角改成 5.0",
    "安装柱改成 M4 底孔",
    "定型",
]
for t in turns:
    r = post("/api/assistant/message", {"session": "api-test", "text": t})
    kind = r["kind"]
    reply = r["reply"].replace("\n", " ")[:60]
    print(f"  [{kind:9s}] {t[:18]:20s} -> {reply}")

st = post("/api/assistant/state", {}) if False else None
req = urllib.request.Request(BASE + "/api/assistant/state?session=api-test")
with urllib.request.urlopen(req, timeout=60) as resp:
    s = json.loads(resp.read())
print("state:", s["stage"], "turns:", s["turns"], "wall:", s["params"].get("WALL"))
