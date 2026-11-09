# -*- coding: utf-8 -*-
"""
M5 门禁：知识资产平台（入库 / BM25+向量混合检索 / 引用溯源 / RBAC / 无证据拒答）

门禁项：
  K1 入库：7 份文档、切片数、条款抽取
  K2 BM25 单路：查询 "PC+ABS 外壳 名义壁厚" 命中注塑规范
  K3 向量单路：同一查询同样命中（hashing 向量，确定性）
  K4 混合 RRF：top1 为注塑规范，且片段含 2.4mm 条款
  K5 引用溯源：每条命中都带 doc_title/section/quote/clauses
  K6 RBAC：viewer 看不到注塑规范与成本基线；engineer 看得到规范但看不到成本基线；admin 全可见
  K7 无证据拒答：无关查询 found=False（供 Agent 输出 needs_input）
  K8 分词与切块质量：条款切分不跨句、每块可独立引用
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.kb.knowledge import HashingEmbedder, KnowledgeBase, extract_clauses, split_chunks, tokenize  # noqa: E402
from app.kb.seed import seed  # noqa: E402

REPORT = ROOT / "docs" / "poc" / "M5-GATE-REPORT.md"
CHECKS = []


def check(name, passed, detail=""):
    CHECKS.append({"name": name, "passed": passed, "detail": detail})
    print(("  PASS " if passed else "  FAIL ") + f"{name}: {detail}")


def main():
    kb = KnowledgeBase(HashingEmbedder())
    n = seed(kb)
    stats = kb.stats()

    # K1
    check("K1 文档入库与切块", n == 7 and stats["chunks"] >= 10,
          f"{n} 份文档 / {stats['chunks']} 个条款块 / 向量模型 {stats['embedder']}")

    query = "PC+ABS 外壳 名义壁厚 多少"

    # K2 BM25
    r_bm = kb.search(query, top_k=3, role="engineer", use_bm25=True, use_vector=False)
    top_bm = r_bm["hits"][0] if r_bm["hits"] else {}
    check("K2 BM25 单路检索", top_bm.get("doc_id") == "spec_injection_v24" and "2.4mm" in top_bm.get("quote", ""),
          f"top1={top_bm.get('doc_title')} / 片段={(top_bm.get('quote') or '')[:42]}…")

    # K3 向量
    r_v = kb.search(query, top_k=5, role="engineer", use_bm25=False, use_vector=True)
    ids_v = [h["doc_id"] for h in r_v["hits"]]
    check("K3 向量单路检索", "spec_injection_v24" in ids_v,
          f"top5 文档={ids_v}（hashing 向量无语义能力，仅保证确定性）")

    # K4 混合 RRF
    r_h = kb.search(query, top_k=3, role="engineer")
    top_h = r_h["hits"][0] if r_h["hits"] else {}
    check("K4 混合 RRF 融合", top_h.get("doc_id") == "spec_injection_v24"
          and len(top_h.get("channels", [])) == 2 and "2.4mm" in top_h.get("quote", ""),
          f"top1={top_h.get('doc_title')} / 命中通道={top_h.get('channels')} / score={top_h.get('score')}")

    # K5 引用完整性
    allcited = all(h.get("doc_title") and h.get("section") and h.get("quote") and h.get("clauses")
                   for h in r_h["hits"])
    check("K5 引用溯源完整", allcited and r_h["hits"],
          f"{len(r_h['hits'])} 条命中均带 文档/章节/原文/条款；示例条款={r_h['hits'][0]['clauses']}")

    # K6 RBAC：分别用「工艺规范查询」和「成本查询」验证角色隔离
    rbac_q1 = "PC+ABS 外壳 名义壁厚 多少"
    rbac_q2 = "供应商报价 注塑件 单价 起订量 成本"
    v1 = kb.search(rbac_q1, top_k=20, role="viewer")
    e1 = kb.search(rbac_q1, top_k=20, role="engineer")
    a2 = kb.search(rbac_q2, top_k=20, role="admin")
    e2 = kb.search(rbac_q2, top_k=20, role="engineer")
    st = kb.stats()["by_role"]
    rbac_ok = (not v1["found"]) and e1["found"] \
        and any(h["doc_id"] == "spec_injection_v24" for h in e1["hits"]) \
        and (not e2["found"]) \
        and any(h["doc_id"] == "cost_baseline_2026q3" for h in a2["hits"]) \
        and (st["viewer"], st["engineer"], st["admin"]) == (1, 6, 7)
    check("K6 RBAC 角色隔离", rbac_ok,
          f"可见文档数 viewer={st['viewer']}/engineer={st['engineer']}/admin={st['admin']}；"
          f"viewer 查工艺规范={v1['found']}（应 False）/ engineer 查规范={e1['found']}（应 True）/ "
          f"engineer 查成本={e2['found']}（应 False）/ admin 查成本={a2['found']}（应 True）")

    # K7 无证据拒答
    r_none = kb.search("量子芯片光刻胶的极紫外掩膜缺陷", top_k=3, role="engineer")
    r_off = kb.search("今天天气怎么样", top_k=3, role="engineer")
    no_hit = (not r_none["found"]) and (not r_off["found"])
    check("K7 无证据即拒答", no_hit,
          f"无关查询 found={r_none['found']}（max cos={r_none.get('max_similarity')}）/"
          f"闲聊 found={r_off['found']}（max cos={r_off.get('max_similarity')}）—— Agent 据此输出 needs_input")

    # K8 切块质量
    sample = "壁厚必须设定为 2.4mm。加强筋不超过 1.44mm。拔模斜度 ≥ 1.8°。"
    chunks = split_chunks(sample, max_len=30)
    toks = tokenize("PC+ABS 外壳壁厚 2.4mm")
    ok8 = len(chunks) >= 2 and all(len(c) <= 40 for c in chunks) and "pc" in toks and "壁厚" in toks
    check("K8 切块与分词质量", ok8,
          f"切块={chunks} / 分词含中文二元组={'壁厚' in toks} / 条款抽取={extract_clauses(sample)}")

    # K9/K10 浏览器实测（需 API 服务已在 8010 运行）
    ui_ok, ui_detail = ui_checks()
    check("K9 知识库页签实测（检索 + 引用展示）", ui_ok.get("search", False), ui_detail.get("search", ""))
    check("K10 RBAC 在界面生效（访客→无证据提示）", ui_ok.get("rbac", False), ui_detail.get("rbac", ""))

    return write_report(all(c["passed"] for c in CHECKS), stats, r_h)


def ui_checks():
    """用真浏览器验证 Studio 的知识库页签。"""
    from playwright.sync_api import sync_playwright
    ok, detail = {}, {}
    shots = ROOT / "docs" / "poc" / "shots"
    shots.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(headless=True, channel="chrome", args=["--no-sandbox"])
            p = b.new_page(viewport={"width": 1680, "height": 1000})
            p.goto("http://127.0.0.1:8010/", wait_until="domcontentloaded", timeout=60000)
            p.wait_for_function("document.querySelector('#health-line').textContent.includes('后端在线')",
                                timeout=30000)
            p.click(".tab[data-tab='kb']")
            p.wait_for_timeout(800)
            p.select_option("#kb-role", "engineer")
            p.fill("#kb-query", "PC+ABS 外壳 名义壁厚 多少")
            p.click("#kb-search")
            p.wait_for_function("document.querySelector('#kb-results').textContent.includes('内部注塑工艺规范')",
                                timeout=30000)
            body = p.inner_text("#kb-results")
            ok["search"] = ("2.4mm" in body) and ("条款" in body)
            detail["search"] = "结果含规范名与 2.4mm 条款" if ok["search"] else body[:80]
            p.screenshot(path=str(shots / "s8_kb_search.png"))

            p.select_option("#kb-role", "viewer")
            p.fill("#kb-query", "PC+ABS 外壳 名义壁厚 多少")
            p.click("#kb-search")
            p.wait_for_function("document.querySelector('#kb-results').textContent.includes('needs_input')",
                                timeout=30000)
            ok["rbac"] = True
            detail["rbac"] = "访客角色被 RBAC 拦截，界面提示 Agent 应输出 needs_input"
            p.screenshot(path=str(shots / "s9_kb_rbac.png"))
            b.close()
    except Exception as exc:
        detail.setdefault("search", f"{type(exc).__name__}: {exc}")
        ok.setdefault("search", False)
    return ok, detail


def write_report(ok_all, stats, sample_result):
    lines = ["# M5 门禁报告 · 知识资产平台", "",
             "- 结论：" + ("**通过**" if ok_all else "**未通过**"),
             f"- 检索栈：BM25(k1=1.5,b=0.75) + 向量（{stats['embedder']}）+ RRF 融合 + RBAC 过滤 + 条款级引用", "",
             "| 门禁 | 结果 | 证据 |", "|---|---|---|"]
    for c in CHECKS:
        lines.append(f"| {c['name']} | {'✅' if c['passed'] else '❌'} | {c['detail']} |")
    lines += ["", "## 知识库清单", "", "| 文档 | 来源类型 | 版本 | 可见角色 | 条款块 |", "|---|---|---|---|---|"]
    for d in stats["docs"]:
        lines.append(f"| {d['title']} | {d['source_type']} | {d['version']} | "
                     f"{'/'.join(d['access_roles'])} | {d['chunks']} |")
    lines += ["", "## 示例检索结果（engineer / 混合检索）", "",
              "```json", json_dump(sample_result["hits"][:3]), "```",
              "", "> 说明：默认向量为确定性 hashing（无模型、离线可用），语义能力需 bge-m3；",
              "> 检索结果一律带「文档 › 章节 › 原文 › 关键条款」，供 Harness 引用与前端展示。"]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n报告写入 {REPORT}")
    print("M5_GATE:", "PASS" if ok_all else "FAIL")
    return 0 if ok_all else 1


def json_dump(obj):
    import json
    return json.dumps(obj, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    sys.exit(main())
