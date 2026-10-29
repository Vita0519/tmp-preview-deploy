"""验收截图：成员页（桌面/移动）、角色控件、设置页、上传对话框、门户卡片。"""
import os

from playwright.sync_api import sync_playwright

BASE = os.environ.get("PV_BASE", "http://127.0.0.1:8000")
USER = os.environ.get("PV_USER", "admin")
PASSWORD = os.environ.get("PV_PASS", "admin123")
OUT = os.environ.get("PV_SHOTS", "C:/tmp/shots")
os.makedirs(OUT, exist_ok=True)


def login(ctx):
    pg = ctx.new_page()
    errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(BASE + "/", wait_until="networkidle")
    pg.fill('input[autocomplete="username"]', USER)
    pg.fill('input[type="password"]', PASSWORD)
    pg.click('button[type="submit"]')
    pg.wait_for_url(lambda u: "/login" not in u, timeout=15000)
    return pg, errs


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")

    # ---------- 桌面 ----------
    ctx = b.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
    pg, errs = login(ctx)

    pg.goto(BASE + "/agents", wait_until="networkidle")
    pg.wait_for_timeout(400)
    pg.screenshot(path=f"{OUT}/20-agents-desktop.png", full_page=True)
    print("角色控件数:", pg.locator("table .rolesel").count(),
          "其中禁用（自己）:", pg.locator("table .rolesel[disabled]").count())
    sel = pg.locator("table .rolesel:not([disabled])").first
    before = sel.input_value()
    print("第一个可改角色 =", before)
    sel.select_option("viewer")
    pg.wait_for_timeout(900)
    pg.screenshot(path=f"{OUT}/21-agents-after-role.png")
    print("改后仍能读取:", pg.locator("table .rolesel:not([disabled])").first.input_value())
    pg.locator("table .rolesel:not([disabled])").first.select_option(before)
    pg.wait_for_timeout(800)

    pg.click(".topbar .btn.primary")
    pg.wait_for_timeout(400)
    pg.screenshot(path=f"{OUT}/22-agent-create.png")
    print("创建框角色选项:", pg.locator(".rolepick .rp").count())
    print("agents/创建框 errors:", errs or "none")
    ctx.close()

    # ---------- 设置页 ----------
    ctx = b.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
    pg, errs = login(ctx)
    pg.goto(BASE + "/settings", wait_until="networkidle")
    pg.wait_for_timeout(500)
    pg.screenshot(path=f"{OUT}/23-settings.png", full_page=True)
    pg.locator(".ts-btn").first.click()
    pg.wait_for_timeout(300)
    pg.screenshot(path=f"{OUT}/24-settings-typesel.png")
    pop = pg.locator(".ts-pop").first
    print("类型下拉可见:", pop.is_visible(), "选项数:", pop.locator("button").count())
    box = pop.bounding_box()
    print("浮层位置:", {k: round(v) for k, v in box.items()})
    print("是否被裁（scrollH>clientH）:",
          pg.evaluate("(() => { const e = document.querySelector('.ts-pop');"
                      " return e.scrollHeight > e.clientHeight + 1 })()"))
    print("底部是否超出视口:", round(box["y"] + box["height"]) > 900)
    pg.mouse.click(5, 5)
    pg.wait_for_timeout(200)

    pg.goto(BASE + "/", wait_until="networkidle")
    pg.wait_for_timeout(300)
    pg.click(".topbar .btn.primary")
    pg.wait_for_timeout(400)
    pg.screenshot(path=f"{OUT}/25-upload.png")
    print("settings/upload errors:", errs or "none")
    ctx.close()

    # ---------- 移动 ----------
    m = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    mp, errs2 = login(m)
    mp.goto(BASE + "/agents", wait_until="networkidle")
    mp.wait_for_timeout(500)
    mp.screenshot(path=f"{OUT}/26-agents-mobile.png", full_page=True)
    print("移动卡片数:", mp.locator(".acard").count(),
          "角色下拉数:", mp.locator(".acard .rolesel").count(),
          "表格可见:", mp.locator(".panel.only-wide").is_visible())
    print("成员页移动端溢出:", mp.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1"))
    mp.goto(BASE + "/settings", wait_until="networkidle")
    mp.wait_for_timeout(400)
    mp.screenshot(path=f"{OUT}/27-settings-mobile.png", full_page=True)
    print("设置页移动端溢出:", mp.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1"))
    print("agents/settings 移动 errors:", errs2 or "none")
    m.close()

    # ---------- 门户 ----------
    pctx = b.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
    lg = pctx.new_page()
    lg.goto(BASE + "/", wait_until="networkidle")
    lg.fill('input[autocomplete="username"]', USER)
    lg.fill('input[type="password"]', PASSWORD)
    lg.click('button[type="submit"]')
    lg.wait_for_url(lambda u: "/login" not in u, timeout=15000)
    pp = pctx.new_page()
    pp.goto(BASE + "/portal", wait_until="networkidle")
    pp.wait_for_timeout(600)
    pp.screenshot(path=f"{OUT}/28-portal.png", full_page=True)
    print("卡片数:", pp.locator(".card").count(),
          "右上圆环:", pp.locator(".card .top .ring").count(),
          "底部倒计时:", pp.locator(".card .foot .cd").count())

    pm = pctx.new_page()
    pm.set_viewport_size({"width": 390, "height": 844})
    pm.goto(BASE + "/portal", wait_until="networkidle")
    pm.wait_for_timeout(500)
    pm.screenshot(path=f"{OUT}/29-portal-mobile.png", full_page=True)
    print("门户移动端溢出:", pm.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1"))
    pctx.close()
    b.close()
