"""批量可见性工具条 + 成员页绑定 Agent 的截图与交互检查。"""
import os

from playwright.sync_api import sync_playwright

BASE = os.environ.get("PV_BASE", "http://127.0.0.1:5173")
USER = os.environ.get("PV_USER", "admin")
PASSWORD = os.environ.get("PV_PASS", "admin123")
OUT = os.environ.get("PV_SHOTS", "C:/tmp/shots")
os.makedirs(OUT, exist_ok=True)


def login(ctx):
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.goto(BASE + "/", wait_until="networkidle")
    pg.fill('input[autocomplete="username"]', USER)
    pg.fill('input[type="password"]', PASSWORD)
    pg.click('button[type="submit"]')
    pg.wait_for_url(lambda u: "/login" not in u, timeout=15000)
    return pg, errs


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")

    ctx = b.new_context(viewport={"width": 1360, "height": 900}, device_scale_factor=2)
    pg, errs = login(ctx)

    # ---------- 项目页：勾选后的批量条 ----------
    pg.goto(BASE + "/", wait_until="networkidle")
    pg.wait_for_timeout(700)
    boxes = pg.locator("tbody tr td.cell-check input")
    print("行数:", boxes.count())
    boxes.nth(0).check()
    boxes.nth(1).check()
    pg.wait_for_timeout(250)
    bar = pg.locator(".bulkbar")
    print("批量条可见:", bar.is_visible() if bar.count() else False)
    for label in ("门户可见", "持链接", "仅自己"):
        print(f"  按钮「{label}」:", pg.locator(f".bulkbar button:has-text('{label}')").count())
    pg.screenshot(path=f"{OUT}/40-bulkbar.png", clip={"x": 0, "y": 300, "width": 1360, "height": 560})
    bar.screenshot(path=f"{OUT}/40b-bulkbar-only.png")
    print("批量条宽度:", bar.bounding_box())

    # 点「门户可见」，等 toast
    pg.locator(".bulkbar button:has-text('门户可见')").first.click()
    pg.wait_for_timeout(700)
    toasts = pg.locator(".toast, .toasts .toast")
    print("提示文案:", [toasts.nth(i).inner_text() for i in range(min(toasts.count(), 3))])
    if toasts.count():
        tb = toasts.first.bounding_box()
        pg.screenshot(path=f"{OUT}/41-bulkbar-toast.png", clip={
            "x": 0, "y": max(0, tb["y"] - 120), "width": 1360,
            "height": min(900 - max(0, tb["y"] - 120), tb["height"] + 200)})
    pg.wait_for_timeout(300)

    # ---------- 成员页：绑定 Agent ----------
    pg.goto(BASE + "/agents", wait_until="networkidle")
    pg.wait_for_timeout(600)
    print("绑定名输入框:", pg.locator("table .keylab").count())
    print("第一行 keymeta:", pg.locator("table .keymeta").first.inner_text())
    pg.screenshot(path=f"{OUT}/42-agents-bind.png", full_page=True)

    # 改名试试
    inp = pg.locator("table .keylab").nth(1)
    before = inp.input_value()
    inp.fill("claude-code")
    inp.press("Enter")
    pg.wait_for_timeout(900)
    print("改名:", before, "->", pg.locator("table .keylab").nth(1).input_value())

    # ---------- 移动端 ----------
    m_ctx = b.new_context(
        viewport={"width": 390, "height": 844}, device_scale_factor=2,
        is_mobile=True, has_touch=True,
    )
    m, _ = login(m_ctx)
    m.goto(BASE + "/", wait_until="networkidle")
    m.wait_for_timeout(700)
    mb = m.locator("tbody tr td.cell-check input")
    if mb.count():
        mb.nth(0).check()
        m.wait_for_timeout(250)
        m.screenshot(path=f"{OUT}/43-bulkbar-mobile.png")
        sw = m.evaluate("document.documentElement.scrollWidth")
        print("移动端 scrollWidth:", sw, "overflow:", sw > 390)
    m.goto(BASE + "/agents", wait_until="networkidle")
    m.wait_for_timeout(600)
    m.screenshot(path=f"{OUT}/44-agents-mobile.png", full_page=True)

    print("JS 报错:", errs[:4] if errs else "无")
    b.close()
