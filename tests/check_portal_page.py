#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""门户三件事的回归：分页、标签溢出折叠、按成员筛选。

会临时建一批外链项目把门户撑到 2 页以上，跑完删干净。

用法: python tests/check_portal_page.py [--url http://127.0.0.1:8000]
"""
import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_test import Client  # noqa: E402

PASS, FAIL = [], []
TAGS = ["政务", "数据看板", "原型", "设计稿", "移动端", "桌面端",
        "内部", "对外", "验收", "演示", "grafana", "figma",
        "调研", "落地页", "组件库", "图标", "文档", "测试"]


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✓' if cond else '✗'} {name}{('  → ' + str(extra)[:180]) if extra and not cond else ''}")


def seed(c: Client, n: int) -> list[str]:
    """建 n 个门户可见的外链项目，每个挂 3 个标签，用来撑满一页。

    另外固定建一个「标签大户」（6 个长标签），专门验证卡片上的 +N 折叠。
    """
    slugs = []
    plan = [(f"pgtest-{i:02d}", [TAGS[(i * 3 + k) % len(TAGS)] for k in range(3)])
            for i in range(n)]
    plan.append(("pgtest-tags", ["政务公开", "数据可视化看板", "技术调研",
                                 "落地页原型", "组件库文档", "内部演示"]))
    for i, (title, tags) in enumerate(plan):
        code, body = c.req("POST", "/api/projects/link", {
            "title": title,
            "link_url": f"https://example.com/{i}",
            "visibility": "portal",
            "forever": True,
            "tags": tags,
        })
        if code in (200, 201):
            slugs.append(body["slug"])
        else:
            print(f"  ! 建项目失败 {title}: {code} {body}")
    return slugs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="admin123")
    args = ap.parse_args()

    c = Client(args.url)
    code, _ = c.login(args.user, args.password)
    check("登录", code == 200)
    if code != 200:
        return 1

    # 直接数门户页里的卡片，比翻 API 再过滤更接近真实（含可见性/到期过滤）
    code, html = c.req("GET", "/portal", raw=True)
    if isinstance(html, bytes):
        html = html.decode("utf-8", "replace")
    portal_before = html.count('class="card"') + html.count('class="card del"')
    need = max(0, 27 - portal_before)
    print(f"[准备] 门户现有 {portal_before} 个，补建 {need} 个")
    slugs = seed(c, need)

    try:
        run(args, slugs, portal_before)
    finally:
        print("[清理]")
        for s in slugs:
            c.req("DELETE", f"/api/projects/{s}")
        code, html = c.req("GET", "/portal", raw=True)
        if isinstance(html, bytes):
            html = html.decode("utf-8", "replace")
        check("临时项目已清理", not any(s in html for s in slugs))

    print()
    print(f"{len(PASS)}/{len(PASS) + len(FAIL)} 通过")
    if FAIL:
        print("失败：")
        for f in FAIL:
            print("  -", f)
        return 1
    return 0


def run(args, slugs, portal_before):
    total = portal_before + len(slugs)
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")
        ctx = b.new_context(viewport={"width": 1280, "height": 900})
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))

        pg.goto(args.url + "/", wait_until="networkidle")
        pg.fill('input[autocomplete="username"]', args.user)
        pg.fill('input[type="password"]', args.password)
        pg.click('button[type="submit"]')
        pg.wait_for_url(lambda u: "/login" not in u, timeout=15000)

        # 每页条数记在 localStorage，先归位，避免上一次跑的影响
        pg.goto(args.url + "/portal")
        pg.evaluate("localStorage.removeItem('pv_per'); localStorage.removeItem('pv_view')")
        pg.goto(args.url + "/portal", wait_until="networkidle")
        pg.wait_for_timeout(300)

        print("[1] 分页")
        cards = pg.locator("#grid .card").count()
        check("门户项目数够翻页", cards == total, f"{cards} vs {total}")
        if cards < 25:
            print("  (项目太少，跳过分页断言)")
        else:
            vis = pg.eval_on_selector_all("#grid .card", "els => els.filter(e => !e.hidden).length")
            rows_vis = pg.eval_on_selector_all("#rows .row", "els => els.filter(e => !e.hidden).length")
            check("首屏只渲染一页（24）", vis == 24, vis)
            check("列表行同步翻页", rows_vis == 24, rows_vis)
            check("分页器可见", pg.locator("#pager").is_visible())
            nums = pg.eval_on_selector_all("#pgnums button[data-p]", "els => els.map(e => e.textContent.trim())")
            check("有页码与上下页", "上一页" in " ".join(nums) and "下一页" in " ".join(nums), nums)
            check("计数文案带页码", "第 1–24" in pg.inner_text("#cnt"), pg.inner_text("#cnt"))

            pg.click('#pgnums button:has-text("下一页")')
            pg.wait_for_timeout(250)
            vis2 = pg.eval_on_selector_all("#grid .card", "els => els.filter(e => !e.hidden).length")
            check("翻到第二页", 0 < vis2 <= 24 and vis2 != 24, vis2)
            check("第二页计数滚动", "第 25–" in pg.inner_text("#cnt"), pg.inner_text("#cnt"))
            check("翻页后回到列表顶部", pg.evaluate("window.pageYOffset") < 200,
                  pg.evaluate("window.pageYOffset"))
            pg.click('#pgnums button:has-text("1")')
            pg.wait_for_timeout(200)

            # 切到「全部显示」应当一次给全，分页器收起来
            pg.select_option("#per", "0")
            pg.wait_for_timeout(250)
            vis3 = pg.eval_on_selector_all("#grid .card", "els => els.filter(e => !e.hidden).length")
            check("全部显示时卡片全出", vis3 == cards, f"{vis3}/{cards}")
            check("全部显示时收起页码", pg.locator("#pgnums button").count() == 0)
            check("「每页」下拉仍在（能切回来）", pg.locator("#per").is_visible())
            pg.select_option("#per", "24")
            pg.wait_for_timeout(200)

            # 筛选之后页码必须回到第 1 页，否则会出现「筛完是空页」
            pg.click('#pgnums button:has-text("下一页")')
            pg.wait_for_timeout(200)
            pg.fill("#q", "pgtest-0")
            pg.wait_for_timeout(300)
            t = pg.inner_text("#cnt")
            # 结果不足一页时分页器收起，文案是「共 N 个」——同样是第 1 页，不能算翻页残留
            page1 = ("第 1–" in t) or ("共 " in t and pg.locator("#pgnums button.on").count() == 0)
            check("改动筛选后回到第 1 页", page1, t)
            pg.fill("#q", "")
            pg.wait_for_timeout(250)

        print("[2] 按成员筛选")
        has_owner = pg.locator("#owner").count() > 0
        if not has_owner:
            print("  (只有一个归属人，跳过)")
        else:
            opts = pg.eval_on_selector_all("#owner option", "els => els.map(e => [e.value, e.textContent])")
            check("成员下拉有「全部成员」", any(v == "" for v, _ in opts), opts[:3])
            check("成员选项带项目数", any("（" in t for _, t in opts), opts)
            vals = [v for v, _ in opts if v]
            pick = vals[0]
            expect = pg.eval_on_selector_all(
                "#grid .card", f"els => els.filter(e => e.dataset.owner === '{pick}').length")
            pg.select_option("#owner", pick)
            pg.wait_for_timeout(300)
            shown = pg.eval_on_selector_all("#grid .card", "els => els.filter(e => !e.hidden).length")
            check("选中成员后只剩他的项目", shown == min(expect, 24), f"{shown} vs {expect}")
            owners_shown = pg.eval_on_selector_all(
                "#grid .card", "els => [...new Set(els.filter(e => !e.hidden).map(e => e.dataset.oname))]")
            check("可见卡片归属一致", owners_shown == [pg.eval_on_selector(
                f'#owner option[value="{pick}"]', "e => e.textContent").split("（")[0]], owners_shown)
            pg.select_option("#owner", "")
            pg.wait_for_timeout(250)

        print("[3] 标签溢出")
        check("标签条有「全部」入口", pg.locator("#tagsbar button.tball").count() == 1)
        wrap = pg.eval_on_selector("#tagsbar", "e => getComputedStyle(e).flexWrap")
        check("标签条不换行", wrap == "nowrap", wrap)
        scrollable = pg.eval_on_selector("#tagsbar", "e => e.scrollWidth - e.clientWidth")
        check("标签多于一行时可横滑", scrollable > 0 or pg.locator("#tagsbar button").count() <= 10,
              f"overflow={scrollable}px chips={pg.locator('#tagsbar button').count()}")
        if scrollable > 0:
            check("右侧有渐隐提示", "fade-r" in (pg.get_attribute("#tagsbar", "class") or ""),
                  pg.get_attribute("#tagsbar", "class"))
            pg.eval_on_selector("#tagsbar", "e => e.scrollLeft = e.scrollWidth")
            pg.wait_for_timeout(250)
            cls = pg.get_attribute("#tagsbar", "class") or ""
            check("滑到底后左侧出现渐隐", "fade-l" in cls, cls)
            pg.eval_on_selector("#tagsbar", "e => e.scrollLeft = 0")
            pg.wait_for_timeout(200)

        cw = pg.eval_on_selector("#grid .card .tags", "e => getComputedStyle(e).flexWrap")
        check("卡片内标签不换行", cw == "nowrap", cw)
        over = pg.eval_on_selector_all(
            "#grid .card .tags", "els => els.filter(e => e.scrollWidth > e.clientWidth + 1).length")
        check("卡片内标签不溢出裁切", over == 0, f"{over} 张卡溢出")
        more = pg.locator("#grid .card .tag.more").count()
        check("标签过多时折成 +N", more > 0, f"+N 标记 {more} 个")
        if more:
            tip = pg.eval_on_selector("#grid .card .tag.more", "e => e.title")
            check("+N 的 title 列出剩余标签", "还有：" in tip, tip)

        print("[4] 归属不出现「—」")
        bad = pg.eval_on_selector_all(
            "#grid .byline span:first-child", "els => els.map(e => e.textContent).filter(t => !t.trim() || t.trim() === '—')")
        check("卡片署名都有名字", not bad, bad[:5])
        rbad = pg.eval_on_selector_all(
            "#rows .rmeta", "els => els.map(e => e.textContent).filter(t => t.startsWith('—'))")
        check("列表行署名都有名字", not rbad, rbad[:5])

        if errs:
            check("无 JS 报错", False, errs[:3])
        else:
            check("无 JS 报错", True)
        b.close()


if __name__ == "__main__":
    sys.exit(main())
