# -*- coding: utf-8 -*-
"""
M3 门禁（UI 实测）：用真浏览器驱动 Studio，走完「运行 → 三维显示 → 规则取证 → 审批」
产出截图到 docs/poc/shots/，并断言关键 DOM 状态。
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "docs" / "poc" / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)
URL = "http://127.0.0.1:8010/"
checks = []


def check(name, passed, detail=""):
    checks.append({"name": name, "passed": passed, "detail": detail})
    print(("  PASS " if passed else "  FAIL ") + f"{name}: {detail}")


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, channel="chrome",
                                     args=["--use-gl=angle", "--use-angle=swiftshader",
                                           "--enable-unsafe-swiftshader", "--no-sandbox"])
        page = browser.new_page(viewport={"width": 1680, "height": 1000}, device_scale_factor=1)
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_function("document.querySelector('#health-line').textContent.includes('后端在线')",
                               timeout=30000)
        check("U1 页面加载并连上后端", True, page.inner_text("#health-line")[:80])

        page.wait_for_function("document.querySelectorAll('.skill').length >= 3", timeout=15000)
        n_skills = page.eval_on_selector_all(".skill", "els => els.length")
        check("U2 Skill 清单渲染", n_skills >= 3, f"{n_skills} 个技能")
        page.screenshot(path=str(SHOTS / "s1_boot.png"))

        # 运行合规章剧
        page.select_option("#preset-select", "compliant")
        page.click("#btn-run")
        page.wait_for_function(
            "document.querySelector('#run-pill').textContent.includes('waiting_approval')", timeout=180000)
        page.wait_for_function(
            "document.querySelector('#hud').textContent.includes('包络')", timeout=60000)
        page.wait_for_timeout(800)   # 等三维首帧渲染稳定
        pill = page.inner_text("#run-pill")
        nodes = page.eval_on_selector_all(".node .t", "els => els.map(e => e.textContent.trim())")
        nodes_m = page.eval_on_selector_all(".node .m", "els => els.map(e => e.textContent.trim())")
        hud = page.inner_text("#hud")
        check("U3 运行到审批门", "waiting_approval" in pill, f"pill={pill}")
        check("U4 节点状态渲染",
              any("n1_cad_build" in n for n in nodes) and any("n4_human_approval" in n for n in nodes)
              and any("ok" in m for m in nodes_m),
              " | ".join(nodes)[:110])
        check("U5 三维包络 HUD", "包络" in hud and "底面 Z" in hud, hud.replace("\n", " / ")[:110])
        page.screenshot(path=str(SHOTS / "s2_compliant_3d.png"))

        # 线框
        page.check("#toggle-wire")
        page.wait_for_timeout(800)
        page.screenshot(path=str(SHOTS / "s3_wireframe.png"))
        page.uncheck("#toggle-wire")

        # 规则取证
        page.click(".tab[data-tab='rules']")
        page.wait_for_timeout(700)
        rows = page.eval_on_selector_all("#rules-body tbody tr", "els => els.length")
        verdicts = page.eval_on_selector_all("#rules-body tbody tr td:nth-child(3)",
                                             "els => els.map(e => e.textContent.trim())")
        check("U6 规则取证表渲染", rows >= 10 and all(v == "passed" for v in verdicts),
              f"{rows} 行, 判定={sorted(set(verdicts))}")
        page.screenshot(path=str(SHOTS / "s4_rules_passed.png"))

        # 审批通过
        page.click("#btn-ok")
        page.wait_for_function("document.querySelector('#run-pill').textContent.includes('succeeded')",
                               timeout=60000)
        check("U7 审批通过后状态 succeeded", True, page.inner_text("#approval-box")[:60])
        page.screenshot(path=str(SHOTS / "s5_approved.png"))

        # 失败剧本：v1 白模
        page.select_option("#preset-select", "v1-mesh")
        page.click("#btn-run")
        page.wait_for_function("document.querySelector('#run-pill').textContent.includes('failed')",
                               timeout=180000)
        page.wait_for_timeout(1200)
        page.click(".tab[data-tab='rules']")
        page.wait_for_timeout(600)
        failed_rows = page.eval_on_selector_all("#rules-body tbody tr.failed", "els => els.length")
        body = page.inner_text("#rules-body")
        check("U8 白模失败剧本：规则表出现失败行且含条款引用",
              failed_rows >= 4 and "内部注塑工艺规范" in body and "2.4mm" in body,
              f"{failed_rows} 行失败, 文档引用={'内部注塑工艺规范' in body}, 条款={'2.4mm' in body}")
        page.screenshot(path=str(SHOTS / "s6_v1mesh_failed.png"))

        # 恶意 IR
        page.select_option("#preset-select", "bad-ir")
        page.click("#btn-run")
        page.wait_for_function("document.querySelector('#run-pill').textContent.includes('failed')",
                               timeout=120000)
        page.wait_for_timeout(800)
        nodes_txt = page.inner_text("#node-list")
        check("U9 恶意 IR 被拒且后续节点跳过",
              "n1_cad_build" in nodes_txt and "skipped" in nodes_txt,
              nodes_txt.replace("\n", " | ")[:140])
        page.screenshot(path=str(SHOTS / "s7_badir_blocked.png"))

        browser.close()

    ok = all(c["passed"] for c in checks)
    report = ROOT / "docs" / "poc" / "M3-GATE-REPORT.md"
    lines = ["# M3 门禁报告 · Studio 前端（真浏览器实测）", "",
             f"- 结论：{'**通过**' if ok else '**未通过**'}",
             f"- 截图：`docs/poc/shots/`（{len(list(SHOTS.glob('*.png')))} 张）", "",
             "| 检查 | 结果 | 证据 |", "|---|---|---|"]
    for c in checks:
        lines.append(f"| {c['name']} | {'✅' if c['passed'] else '❌'} | {c['detail']} |")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n报告写入 {report}")
    print("M3_GATE:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
