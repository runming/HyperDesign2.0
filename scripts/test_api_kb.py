import json
import sys
import urllib.request

BASE = "http://127.0.0.1:8010"


def post(path, payload):
    req = urllib.request.Request(BASE + path,
                                 data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=60) as r:
        return json.loads(r.read())


h = get("/api/health")
print("health:", h["version"], "skills", h["skills"], "workflow", h["workflow_version"])
s = get("/api/kb/stats")
print("kb stats:", s["documents"], "docs /", s["chunks"], "chunks /", s["embedder"], "/ by_role", s["by_role"])

for q, role in [("PC+ABS 外壳 名义壁厚 多少", "engineer"),
                ("PC+ABS 外壳 名义壁厚 多少", "viewer"),
                ("供应商报价 注塑件 单价 起订量", "engineer"),
                ("供应商报价 注塑件 单价 起订量", "admin"),
                ("量子芯片光刻胶极紫外掩膜", "admin")]:
    r = post("/api/kb/search", {"query": q, "role": role, "top_k": 3})
    top = r["hits"][0]["doc_title"] if r["hits"] else "-"
    clauses = r["hits"][0]["clauses"] if r["hits"] else []
    print(f"  q={q[:18]:20s} role={role:8s} found={r['found']!s:5s} top={top[:22]:24s} clauses={clauses}")

docs = get("/api/kb/documents?role=viewer")["documents"]
print("viewer 可见:", [d["title"][:18] for d in docs])
