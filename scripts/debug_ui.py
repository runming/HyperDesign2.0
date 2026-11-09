from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True, channel="chrome",
                           args=["--no-sandbox", "--use-gl=angle", "--use-angle=swiftshader",
                                 "--enable-unsafe-swiftshader"])
    p = b.new_page()
    errs = []
    p.on("pageerror", lambda e: errs.append("PAGEERROR: " + str(e)[:300]))
    p.on("console", lambda m: errs.append(f"console.{m.type}: {m.text[:200]}") if m.type in ("error", "warning") else None)
    p.goto("http://127.0.0.1:8010/", wait_until="domcontentloaded")
    p.wait_for_timeout(1500)
    p.select_option("#preset-select", "compliant")
    p.click("#btn-run")
    p.wait_for_timeout(9000)
    print("pill:", p.inner_text("#run-pill"))
    print("hud:", p.inner_text("#hud")[:90].replace("\n", " / "))
    print("approval:", p.inner_text("#approval-box")[:60].replace("\n", " / "))
    for e in errs[-10:]:
        print("  ", e)
    b.close()
