import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

OUT = Path("/tmp/shots")
OUT.mkdir(parents=True, exist_ok=True)
BASE = "http://127.0.0.1:8010"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2,
                                        locale="zh-CN")
        page = await ctx.new_page()

        await page.goto(f"{BASE}/login", wait_until="networkidle")
        await page.screenshot(path=str(OUT / "01-login.png"))

        await page.fill('input[autocomplete="username"]', "admin")
        await page.fill('input[type="password"]', "admin123")
        await page.click('button[type="submit"]')
        await page.wait_for_url(f"{BASE}/", timeout=15000)
        await page.wait_for_timeout(1200)
        await page.screenshot(path=str(OUT / "02-projects.png"))

        # 抽屉
        await page.click("tbody tr:first-child")
        await page.wait_for_timeout(900)
        await page.screenshot(path=str(OUT / "03-drawer.png"))
        await page.keyboard.press("Escape")
        await page.click(".scrim")
        await page.wait_for_timeout(400)

        # 新建弹窗
        await page.click("text=新建项目")
        await page.wait_for_timeout(600)
        await page.screenshot(path=str(OUT / "04-upload.png"))
        await page.click(".modal-head .btn.ghost")
        await page.wait_for_timeout(300)

        await page.goto(f"{BASE}/agents", wait_until="networkidle")
        await page.wait_for_timeout(700)
        await page.screenshot(path=str(OUT / "05-agents.png"))

        await page.goto(f"{BASE}/settings", wait_until="networkidle")
        await page.wait_for_timeout(700)
        await page.screenshot(path=str(OUT / "06-settings.png"))

        # 访客预览页
        visitor = await ctx.new_page()
        await visitor.goto(f"{BASE}/v/landing-v2", wait_until="networkidle")
        await visitor.wait_for_timeout(900)
        await visitor.screenshot(path=str(OUT / "07-preview.png"))

        # 手机
        mobile = await browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                                           locale="zh-CN", storage_state=await ctx.storage_state())
        mp = await mobile.new_page()
        await mp.goto(f"{BASE}/", wait_until="networkidle")
        await mp.wait_for_timeout(900)
        await mp.screenshot(path=str(OUT / "08-mobile.png"))

        # 错误页
        errp = await ctx.new_page()
        resp = await errp.goto(f"{BASE}/v/not-exist", wait_until="networkidle")
        await errp.screenshot(path=str(OUT / "09-404.png"))
        print("404 status:", resp.status if resp else None)

        # 控制台错误收集
        await browser.close()


asyncio.run(main())
print("shots:", sorted(p.name for p in OUT.glob("*.png")))
