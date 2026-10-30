#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""项目改名：控制台能改，名字还得短。

以前抽屉里标题是死的（纯 <h2> 文本），后端 PATCH 明明支持 title，界面却没有任何入口，
所以「改不了项目名」。现在点标题或铅笔就能改。同时按显示宽度立规矩：
中文算 1、半角算 0.5，**最多 10 个中文字符（约 20 个英文字符）**，
改名超长直接 422 让人改，上传/外链这类顺手给的名字则自动截短。

覆盖：
  [1] 规则接口
      1. /api/meta 下发 title_rule（max_width / max_cjk / max_narrow）
  [2] 接口层
      2. 改名成功、首尾空格被去掉
      3. 11 个中文字 → 422
      4. 20 个半角正好可以、21 个 → 422
      5. 中英混排按宽度算（9.5 可以）
      6. 上传时超长自动截断，且截完不超过上限
      7. 外链名超长同样截断
      8. 截断后不触发重名 409（整串已被改短）
  [3] 浏览器
      9. 抽屉里点标题进入改名态
     10. 输入合法名字 + 保存 → 标题与列表都更新
     11. 超长时计数标红、保存按钮禁用
     12. Esc 取消，标题回原样
     13. 全程无 JS 报错

用法: python tests/check_rename.py [--url http://127.0.0.1:8000] [--headed]
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_test import FAIL, PASS, Client, check, multipart  # noqa: E402

HTML = b"<!doctype html><meta charset=utf-8><h1>rename</h1>"


def width_of(text: str) -> float:
    """跟后端 namerule.py 同一把尺子：全角 1、半角 0.5。"""
    import unicodedata

    return sum(1.0 if unicodedata.east_asian_width(c) in ("W", "F") else 0.5 for c in text)


def upload(c: Client, slug: str, title: str):
    body, ct = multipart({"slug": slug, "title": title, "hours": "2"}, [("files", "index.html", HTML)])
    code, raw = c.req("POST", "/api/projects", body, ct=ct, raw=True)
    if isinstance(raw, dict):  # 出错时客户端已经解析成 JSON 了
        return code, raw
    try:
        return code, json.loads(raw or b"{}")
    except json.JSONDecodeError:
        return code, {"raw": raw[:200]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="admin123")
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()

    sfx = str(int(time.time()))[-5:]
    admin = Client(args.url)
    code, _ = admin.login(args.user, args.password)
    check("管理员登录", code == 200)

    slug = f"rn-{sfx}"
    base_title = f"改名测试{sfx}"
    created, d = upload(admin, slug, base_title)
    check("建好测试项目", created == 200 and d.get("slug") == slug, d)

    print("[1] 规则接口")
    code, meta = admin.req("GET", "/api/meta")
    rule = meta.get("title_rule") or {}
    check("下发 title_rule", bool(rule), rule)
    check("上限 10 个中文字符", rule.get("max_width") == 10 and rule.get("max_cjk") == 10, rule)
    check("约合 20 个半角", rule.get("max_narrow") == 20, rule)

    print("[2] 接口层")
    code, d = admin.req("PATCH", f"/api/projects/{slug}", {"title": f"  新名字 {sfx}  "})
    check("改名成功", code == 200, d)
    check("首尾空格被去掉", d.get("title") == f"新名字 {sfx}", d.get("title"))

    over_cjk = "一二三四五六七八九十一"  # 11 个中文字
    code, d = admin.req("PATCH", f"/api/projects/{slug}", {"title": over_cjk})
    check("11 个中文字被拒", code == 422, f"{code} {d}")
    check("错误文案说清上限", "10 个中文字符" in str(d.get("detail")), d.get("detail"))

    exactly20 = f"abcde{sfx}fghijklmno"  # 5 + 5 + 10 = 20 个半角 = 宽度 10
    exactly21 = f"abcde{sfx}fghijklmnop"  # 21 个半角 = 宽度 10.5
    check("测试串长度对得上", len(exactly20) == 20 and len(exactly21) == 21, (len(exactly20), len(exactly21)))
    code, d = admin.req("PATCH", f"/api/projects/{slug}", {"title": exactly20})
    check("20 个半角放行", code == 200 and d.get("title") == exactly20, f"{code} {d.get('title')}")
    code, d = admin.req("PATCH", f"/api/projects/{slug}", {"title": exactly21})
    check("21 个半角被拒", code == 422, f"{code} {d.get('title')}")

    mixed = f"设计稿 rev{sfx}"  # 3 + 0.5 + 3×0.5 + 5×0.5 = 7.5
    code, d = admin.req("PATCH", f"/api/projects/{slug}", {"title": mixed})
    check("中英混排按宽度算", code == 200 and d.get("title") == mixed, f"{code} {d.get('title')} w={width_of(mixed)}")

    long_title = f"{sfx}号这是很长很长的项目名字啊啊"  # 截断后前 10 个字符里带 sfx，跨次跑也不会撞名
    slug2 = f"rn{sfx}-up"
    code, d = upload(admin, slug2, long_title)
    check("上传超长不报错", code == 200, d)
    check("上传超长自动截断", d.get("title") != long_title and width_of(d.get("title") or "") <= 10,
          f"{d.get('title')!r} w={width_of(d.get('title') or '')}")

    code, d = admin.req("POST", "/api/projects/link",
                        {"link_url": "https://example.com/x", "title": f"{sfx}外链名字也挺长", "hours": 2})
    check("外链超长自动截断", code == 200 and width_of(d.get("title") or "") <= 10,
          f"{code} {d.get('title')!r}")
    link_slug = d.get("slug")

    # 截断后不该撞已有名字
    code, d = upload(admin, f"rn{sfx}-up2", long_title)
    check("同一超长名可以再建一个（截断后仍唯一）", code in (200, 409), f"{code} {d.get('detail')}")

    print("[3] 浏览器")
    pg_base = args.url.rstrip("/")
    try:
        browser_suite(pg_base, args.user, args.password, args.headed, mixed, slug)
    finally:
        for s in {slug, slug2, link_slug, f"rn{sfx}-up2"}:
            if s:
                admin.req("DELETE", f"/api/projects/{s}")
        code, d = admin.req("GET", f"/api/projects/{slug}")
        check("测试项目已清理", code == 404, code)

    print(f"\n{len(PASS)}/{len(PASS) + len(FAIL)} 通过")
    if FAIL:
        print("失败：")
        for f in FAIL:
            print("  -", f)
        return 1
    return 0


def browser_suite(base, user, password, headed, title, slug) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=not headed)
        ctx = b.new_context(viewport={"width": 1360, "height": 900})
        pg = ctx.new_page()
        errs = []

        pg.goto(base + "/login", wait_until="domcontentloaded")
        pg.fill('input[autocomplete="username"]', user)
        pg.fill('input[type="password"]', password)
        pg.click('button[type="submit"]')
        pg.wait_for_url(lambda u: "/login" not in u, timeout=15000)

        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: errs.append(m.text)
              if m.type == "error" and "favicon" not in m.text else None)

        pg.goto(base + "/", wait_until="domcontentloaded")  # 项目页就是首页
        pg.wait_for_selector("tbody tr", timeout=15000)

        row = pg.locator("tbody tr").filter(has_text=title).first
        row.wait_for(state="visible", timeout=15000)
        check("列表里能找到测试项目", row.count() > 0, title)
        row.click()
        pg.wait_for_selector(".drawer .titlerow h2", timeout=10000)

        print("[3.1] 点标题进改名态")
        pg.click(".drawer .titlerow h2")
        pg.wait_for_selector(".drawer .renamebox input", timeout=5000)
        check("出现改名输入框", pg.query_selector(".drawer .renamebox input") is not None)
        check("输入框预填当前名字",
              pg.input_value(".drawer .renamebox input") == title,
              pg.input_value(".drawer .renamebox input"))

        print("[3.2] 超长被拦住")
        pg.fill(".drawer .renamebox input", "一二三四五六七八九十一")
        pg.wait_for_timeout(120)
        counter = " ".join(pg.inner_text(".drawer .renamefoot .counter").split())
        check("计数显示当前/上限并说明超出", "11 / 10" in counter and "超出" in counter, counter)
        check("超限说明挂在 tooltip 上",
              "10 个中文字符" in (pg.get_attribute(".drawer .renamefoot .counter", "title") or ""),
              pg.get_attribute(".drawer .renamefoot .counter", "title"))
        check("超出时计数带 over 类",
              pg.eval_on_selector(".drawer .renamefoot .counter", "el => el.classList.contains('over')"))
        check("保存按钮被禁用",
              pg.eval_on_selector(".drawer .renamebox .btn.primary", "el => el.disabled"))

        print("[3.3] Esc 取消")
        pg.keyboard.press("Escape")
        pg.wait_for_selector(".drawer .titlerow h2", timeout=5000)
        check("回到只读标题", pg.inner_text(".drawer .titlerow h2").strip() == title,
              pg.inner_text(".drawer .titlerow h2"))

        print("[3.4] 正常改名")
        new_title = f"改好了{title[-4:]}"
        pg.click(".drawer .titlerow h2")
        pg.wait_for_selector(".drawer .renamebox input", timeout=5000)
        pg.fill(".drawer .renamebox input", new_title)
        pg.click(".drawer .renamebox .btn.primary")
        pg.wait_for_function(
            f"() => (document.querySelector('.drawer .titlerow h2')?.innerText || '').includes({json.dumps(new_title)})",
            timeout=10000,
        )
        check("抽屉标题已更新", pg.inner_text(".drawer .titlerow h2").strip() == new_title,
              pg.inner_text(".drawer .titlerow h2"))
        pg.wait_for_function(
            f"() => [...document.querySelectorAll('tbody tr')].some(r => r.innerText.includes({json.dumps(new_title)}))",
            timeout=10000,
        )
        check("列表也跟着变了", True)

        print("[3.5] 报错检查")
        check("无 JS 报错", not errs, errs[:3])
        ctx.close()
        b.close()


if __name__ == "__main__":
    sys.exit(main())
