"""门户页验收：筛选/排序交互 + 桌面/移动截图。"""
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
OUT = "C:/tmp/shots"

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    ctx = b.new_context(viewport={"width": 1280, "height": 860}, device_scale_factor=2)
    pg = ctx.new_page()
    errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errs.append(str(e)))

    pg.goto(BASE + "/", wait_until="networkidle")
    pg.fill('input[autocomplete="username"]', "admin")
    pg.fill('input[type="password"]', "admin123")
    pg.click('button[type="submit"]')
    pg.wait_for_url(lambda u: "/login" not in u, timeout=15000)

    pg.goto(BASE + "/portal", wait_until="networkidle")
    pg.wait_for_timeout(300)
    print("cards:", pg.locator(".card").count())
    print("tags:", pg.locator("#tagsbar button").count())
    print("cnt:", pg.inner_text("#cnt"))
    pg.screenshot(path=f"{OUT}/11-portal.png", full_page=True)

    # 按类型筛选
    pg.click('.seg[data-kind] button[data-v="static"]')
    pg.wait_for_timeout(200)
    print("static 后 cnt:", pg.inner_text("#cnt"), "可见:", pg.locator(".card:visible").count())

    # 点第一个标签
    pg.click('.seg[data-kind] button[data-v="all"]')
    first = pg.locator("#tagsbar button").first
    tag = first.inner_text()
    first.click()
    pg.wait_for_timeout(200)
    print(f"标签「{tag}」后:", pg.inner_text("#cnt"), "可见:", pg.locator(".card:visible").count())
    pg.screenshot(path=f"{OUT}/12-portal-filter.png", full_page=True)
    pg.click("#tagsbar button.on")

    # 排序：访问最多
    pg.select_option("#sort", "views")
    pg.wait_for_timeout(200)
    names = [pg.locator(".card:visible .name").nth(i).inner_text() for i in range(pg.locator(".card:visible").count())]
    print("按访问排序:", names)
    pg.select_option("#sort", "exp")
    pg.wait_for_timeout(200)
    names = [pg.locator(".card:visible .name").nth(i).inner_text() for i in range(pg.locator(".card:visible").count())]
    print("按到期排序:", names)

    # 搜索命中/未命中
    pg.fill("#q", "zzz-不存在")
    pg.wait_for_timeout(200)
    print("搜索空结果 空态可见:", pg.locator("#blank").is_visible(), "cnt:", pg.inner_text("#cnt"))
    pg.fill("#q", "")

    # 移动端
    m = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    mp = m.new_page()
    mp.goto(BASE + "/", wait_until="networkidle")
    mp.fill('input[autocomplete="username"]', "admin")
    mp.fill('input[type="password"]', "admin123")
    mp.click('button[type="submit"]')
    mp.wait_for_url(lambda u: "/login" not in u, timeout=15000)
    mp.goto(BASE + "/portal", wait_until="networkidle")
    mp.wait_for_timeout(300)
    mp.screenshot(path=f"{OUT}/13-portal-mobile.png", full_page=True)

    print("console errors:", errs or "none")
    b.close()
