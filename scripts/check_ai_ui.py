from playwright.sync_api import sync_playwright

SHOTS = r"D:\hyperdesign2\docs\poc\shots"

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True, channel="chrome",
                           args=["--no-sandbox", "--use-gl=angle", "--use-angle=swiftshader",
                                 "--enable-unsafe-swiftshader"])
    p = b.new_page(viewport={"width": 1680, "height": 1000})
    errs = []
    p.on("pageerror", lambda e: errs.append(str(e)[:160]))
    p.goto("http://127.0.0.1:8010/", wait_until="domcontentloaded", timeout=60000)
    p.wait_for_function("document.querySelector('#health-line').textContent.includes('后端在线')",
                        timeout=30000)
    p.click(".tab[data-tab='ai']")
    p.wait_for_timeout(500)
    for text, wait in [("帮我设计一个 120×80×45 的 PC+ABS 传感器外壳", "已理解需求"),
                       ("把壁厚改成 2.0", "低于企业规范下限"),
                       ("圆角改成 5.0", "已修改"),
                       ("定型", "已定型")]:
        p.fill("#ai-input", text)
        p.click("#ai-send")
        p.wait_for_function(
            f"document.querySelector('#ai-log').textContent.includes({wait!r})", timeout=180000)
        p.wait_for_timeout(300)
    p.screenshot(path=SHOTS + r"\s10_ai_assistant.png")
    log = p.inner_text("#ai-log")
    print("气泡数:", p.eval_on_selector_all(".ai-msg", "els => els.length"))
    print("含 4 个关键回复:", all(k in log for k in ("已理解需求", "低于企业规范下限", "已修改", "已定型")))
    print("错误:", errs[:2] or "无")
    b.close()
