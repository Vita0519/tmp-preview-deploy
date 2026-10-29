"""验收截图：成员页移动端、设置页、上传对话框。"""
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8010"
OUT = "C:/tmp/shots"


def login(ctx, mobile=False):
    pg = ctx.new_page()
    errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(BASE + "/", wait_until="networkidle")
    pg.fill('input[autocomplete="username"]', "admin")
    pg.fill('input[type="password"]', "admin123")
    pg.click('button[type="submit"]')
    pg.wait_for_url(lambda u: "/login" not in u, timeout=15000)
    return pg, errs


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")

    # 桌面：设置页
    ctx = b.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
    pg, errs = login(ctx)
    pg.goto(BASE + "/settings", wait_until="networkidle")
    pg.wait_for_timeout(400)
    pg.screenshot(path=f"{OUT}/15-settings.png", full_page=True)
    print("settings errors:", errs or "none")

    # 桌面：上传对话框
    pg.goto(BASE + "/", wait_until="networkidle")
    pg.wait_for_timeout(300)
    pg.click('.topbar .btn.primary')
    pg.wait_for_timeout(400)
    pg.screenshot(path=f"{OUT}/16-upload.png")
    print("upload errors:", errs or "none")
    ctx.close()

    # 移动：成员页
    m = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    mp, errs2 = login(m, mobile=True)
    mp.goto(BASE + "/agents", wait_until="networkidle")
    mp.wait_for_timeout(400)
    mp.screenshot(path=f"{OUT}/14-agents-mobile.png", full_page=True)
    print("agents mobile errors:", errs2 or "none")
    print("可见卡片数:", mp.locator(".acard").count(), "表格可见:", mp.locator(".panel.only-wide").is_visible())
    m.close()
    b.close()
