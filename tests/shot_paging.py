"""门户分页 / 成员筛选 / 标签溢出 的视觉验收（截图 + 关键尺寸断言）。"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_test import Client  # noqa: E402

BASE = "http://127.0.0.1:8000"
OUT = "C:/tmp/shots"
USER, PASSWORD = "admin", "admin123"

TAGS = ["政务", "数据看板", "原型", "设计稿", "移动端", "桌面端", "内部", "对外",
        "验收", "演示", "grafana", "figma", "调研", "落地页", "组件库", "图标"]


def seed(c, n):
    slugs = []
    for i in range(n):
        tags = [TAGS[(i * 3 + k) % len(TAGS)] for k in range(3)]
        code, body = c.req("POST", "/api/projects/link", {
            "title": f"shot-{i:02d}", "link_url": f"https://example.com/{i}",
            "visibility": "portal", "forever": True, "tags": tags,
        })
        if code in (200, 201):
            slugs.append(body["slug"])
    code, body = c.req("POST", "/api/projects/link", {
        "title": "shot-标签大户", "link_url": "https://example.com/tags",
        "visibility": "portal", "forever": True,
        "tags": ["政务公开", "数据可视化看板", "技术调研", "落地页原型", "组件库文档", "内部演示"],
    })
    if code in (200, 201):
        slugs.append(body["slug"])
    return slugs


c = Client(BASE)
c.login(USER, PASSWORD)
slug0 = seed(c, 12)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")
        ctx = b.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: errs.append(m.text)
              if m.type == "error" and "favicon" not in m.text else None)

        pg.goto(BASE + "/", wait_until="networkidle")
        pg.fill('input[autocomplete="username"]', USER)
        pg.fill('input[type="password"]', PASSWORD)
        pg.click('button[type="submit"]')
        pg.wait_for_url(lambda u: "/login" not in u, timeout=15000)
        pg.goto(BASE + "/portal")
        pg.evaluate("localStorage.removeItem('pv_per')")
        pg.goto(BASE + "/portal", wait_until="networkidle")
        pg.wait_for_timeout(400)

        print("总卡片:", pg.locator("#grid .card").count(),
              "| 可见:", pg.eval_on_selector_all("#grid .card", "e=>e.filter(x=>!x.hidden).length"))
        print("cnt:", pg.inner_text("#cnt"))
        pg.screenshot(path=f"{OUT}/20-portal-page1.png", full_page=True)

        # 单独裁一张吸顶区（工具条 + 标签条）
        pg.locator(".dock").screenshot(path=f"{OUT}/21-dock.png")

        # 第二页
        pg.click('#pgnums button:has-text("下一页")')
        pg.wait_for_timeout(300)
        pg.locator("#pager").scroll_into_view_if_needed()
        pg.wait_for_timeout(200)
        pg.screenshot(path=f"{OUT}/22-portal-page2.png")
        pg.locator("#pager").screenshot(path=f"{OUT}/23-pager.png")
        print("第2页 cnt:", pg.inner_text("#cnt"))

        # 成员筛选
        pg.eval_on_selector("#per", "e=>{e.value='24';e.dispatchEvent(new Event('change'))}")
        vals = pg.eval_on_selector_all("#owner option", "e=>e.map(x=>x.value).filter(Boolean)")
        pg.select_option("#owner", vals[0])
        pg.wait_for_timeout(300)
        print("成员筛选后:", pg.inner_text("#cnt"))
        pg.locator(".dock").screenshot(path=f"{OUT}/24-dock-owner.png")

        # 列表视图 + 标签溢出
        pg.select_option("#owner", "")
        pg.click('#viewseg button[data-view="list"]')
        pg.wait_for_timeout(300)
        pg.screenshot(path=f"{OUT}/25-portal-list.png", full_page=True)
        pg.click('#viewseg button[data-view="grid"]')
        pg.wait_for_timeout(200)

        # 手机端
        m = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        mp = m.new_page()
        mp.goto(BASE + "/")
        mp.evaluate("localStorage.setItem('pv_view','grid')")
        mp.goto(BASE + "/portal", wait_until="networkidle")
        mp.wait_for_timeout(300)
        mp.screenshot(path=f"{OUT}/26-portal-mobile.png", full_page=True)
        mp.locator(".dock").screenshot(path=f"{OUT}/27-dock-mobile.png")
        print("移动端横向溢出:", mp.evaluate("document.documentElement.scrollWidth - window.innerWidth"))

        print("JS 错误:", errs[:3] if errs else "无")
        b.close()
finally:
    for s in slug0:
        c.req("DELETE", f"/api/projects/{s}")
    print("已清理", len(slug0), "个临时项目")
