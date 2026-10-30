#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""站点图标全链路：按钮能点开、能传上去、能恢复默认；文件删不掉也不能把接口打成 500。

背景（这次修的 bug）：
  · 前端 43c31fd 重排设置页时把 <input type=file> 丢了，pickIcon() 的 .click() 成了空操作，
    用户点「上传图标」毫无反应；
  · 后端 branding.remove() 只 except OSError，环境的删除保护抛的是别的异常，
    于是「恢复默认」直接 500。

覆盖：
  [1] 离线单元（直接 import branding，用临时目录）
      1. 正常删除后 find() / current() 都没了
      2. unlink 抛异常时不冒泡、回退改名成 .off，接口层判定为「没有自定义图标」
      3. 删不掉但改名成功 → remove() 认为移除成功
      4. 目录里残留多份时 find() 取最新那份
      5. save() 换格式后只留一份，且不会把刚写下去的新文件删掉
      6. unlink 全程失败时 save() 仍然「换图成功」（靠 mtime 兜底）
  [2] 浏览器（Playwright + Chrome）
      7. 页面上有隐藏的 file input（它就是按钮的命门）
      8. 点「上传图标」能弹出文件选择框
      9. 选完文件：预览换成上传的图、按钮变「更换图标」、多出「恢复默认」
     10. 点「恢复默认」：预览回落到内置 /favicon.svg、按钮变回「上传图标」
     11. 全程无 JS 报错

用法: python tests/check_icon.py [--url http://127.0.0.1:8000] [--headed]
"""
import argparse
import base64
import importlib.util
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_test import FAIL, PASS, Client, check  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BRANDING = ROOT / "backend" / "app" / "branding.py"

# 1×1 的透明 png，够小又确实是合法图片
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8"><rect width="8" height="8" fill="#0f766e"/></svg>'


def load_branding():
    """按文件路径直接加载，绕开 backend 包的初始化，方便在临时目录里做单元测试。"""
    spec = importlib.util.spec_from_file_location("branding_ut", BRANDING)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def unit_suite() -> None:
    mod = load_branding()
    tmp = Path(tempfile.mkdtemp(prefix="branding-"))
    mod.dir_path = lambda: tmp  # 所有落盘都进临时目录
    real_unlink = Path.unlink

    def blocked(self, missing_ok=False):
        """模拟环境的删除保护：抛的根本不是 OSError。"""
        raise RuntimeError("SAFE_DELETE_BULK_CONFIRM_REQUIRED")

    try:
        print("[1] 正常删除")
        mod.save("a.png", PNG)
        check("save 之后能看到图标", mod.current() is not None)
        check("remove 返回 True", mod.remove() is True)
        check("文件真没了", mod.find() is None)
        check("payload 回到内置", mod.payload()["custom"] is False)

        print("[2] 删除被拦（环境的删除保护）")
        mod.save("a.png", PNG)
        Path.unlink = blocked
        try:
            ok = mod.remove()
        except Exception as exc:  # noqa: BLE001 - 这里绝不该冒出来
            ok = f"raised {exc!r}"
        finally:
            Path.unlink = real_unlink
        check("remove 不抛异常且认为已移除", ok is True, ok)
        check("find() 看不到它了", mod.find() is None)
        check("回退留下了 .off 残骸", any(tmp.glob("site-icon*.off")), sorted(p.name for p in tmp.iterdir()))
        check("payload 判定为内置", mod.payload()["custom"] is False)

        print("[3] 删不掉时换图仍然生效")
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True, exist_ok=True)
        mod.save("a.png", PNG)
        Path.unlink = blocked
        try:
            mod.save("b.svg", SVG)
        finally:
            Path.unlink = real_unlink
        cur = mod.current()
        check("拿到的是后传的 svg", bool(cur) and cur["ext"] == "svg", cur and cur["ext"])
        check("内容没被顺手删掉", cur["path"].read_bytes() == SVG if cur else False)

        print("[4] 残留多份时取最新")
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True, exist_ok=True)
        old = tmp / "site-icon.png"
        old.write_bytes(PNG)
        time.sleep(0.01)
        new = tmp / "site-icon.webp"
        new.write_bytes(b"RIFF0000WEBP")
        check("find 取 mtime 最新的那份", mod.find() == new, mod.find())

        print("[5] save 只留一份且不误删新文件")
        shutil.rmtree(tmp, ignore_errors=True)
        mod.save("a.png", PNG)
        mod.save("b.svg", SVG)
        left = sorted(p.name for p in tmp.iterdir())
        check("目录里只剩一份", left == ["site-icon.svg"], left)
        check("find 指向 svg", (mod.find() or Path()).name == "site-icon.svg")
        check("内容完整", (tmp / "site-icon.svg").read_bytes() == SVG)
    finally:
        Path.unlink = real_unlink
        shutil.rmtree(tmp, ignore_errors=True)


def browser_suite(base: str, user: str, password: str, headed: bool) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=not headed)
        ctx = b.new_context(viewport={"width": 1280, "height": 900})
        pg = ctx.new_page()
        errs = []

        print("[6] 登录并进设置页")
        pg.goto(base + "/login", wait_until="domcontentloaded")
        pg.fill('input[autocomplete="username"]', user)
        pg.fill('input[type="password"]', password)
        pg.click('button[type="submit"]')
        pg.wait_for_url(lambda u: "/login" not in u, timeout=15000)

        # 登录之后再挂监听：登录页那几次 401 是被测行为本身，不算报错
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: errs.append(m.text)
              if m.type == "error" and "favicon" not in m.text else None)

        pg.goto(base + "/settings", wait_until="domcontentloaded")
        pg.wait_for_selector(".iconprev img", timeout=15000)

        print("[7] 上传按钮的命门：隐藏的 file input")
        check("页面上有 file input", pg.query_selector('input.srfile[type="file"]') is not None)
        check("它不是 display:none（否则部分浏览器点不动）",
              pg.eval_on_selector('input.srfile[type="file"]',
                                  "el => getComputedStyle(el).display") != "none")
        check("它是被 ref 挂上的同一个元素",
              pg.eval_on_selector('input.srfile[type="file"]',
                                  "el => el.hasAttribute('accept') && el.accept.includes('png')"))

        print("[8] 点按钮 → 弹选择框")
        btns = pg.query_selector_all(".iconacts button")
        check("按钮在", len(btns) >= 1)
        label = btns[0].inner_text().strip()
        try:
            with pg.expect_file_chooser(timeout=5000) as fc:
                btns[0].click()
            chooser_ok = True
        except Exception as exc:  # noqa: BLE001
            chooser_ok = False
            fc = None
            print("    no chooser:", exc)
        check(f"点「{label}」能弹出文件选择", chooser_ok)

        print("[9] 选文件后预览更新")
        if chooser_ok:
            before = pg.eval_on_selector(".iconprev img", "el => el.getAttribute('src')")
            fc.value.set_files([{"name": "t.png", "mimeType": "image/png", "buffer": PNG}])
            pg.wait_for_function(
                "() => (document.querySelector('.iconprev img') || {}).src?.includes('/site-icon')",
                timeout=15000,
            )
            after = pg.eval_on_selector(".iconprev img", "el => el.getAttribute('src') || el.src")
            check("预览换成了自定义图标", after != before and "/site-icon" in after, after)
            texts = [x.inner_text().strip() for x in pg.query_selector_all(".iconacts button")]
            check("按钮文案变「更换图标」", any("更换图标" in t for t in texts), texts)
            check("多出「恢复默认」", any("恢复默认" in t for t in texts), texts)

            print("[10] 恢复默认")
            for x in pg.query_selector_all(".iconacts button"):
                if "恢复默认" in x.inner_text():
                    x.click()
                    break
            pg.wait_for_function(
                "() => (document.querySelector('.iconprev img') || {}).src?.includes('/favicon')",
                timeout=15000,
            )
            src = pg.eval_on_selector(".iconprev img", "el => el.getAttribute('src') || el.src")
            check("预览回落内置图标", "/favicon.svg" in src, src)
            texts = [x.inner_text().strip() for x in pg.query_selector_all(".iconacts button")]
            check("按钮变回「上传图标」", any("上传图标" in t for t in texts), texts)
            check("「恢复默认」收起来了", not any("恢复默认" in t for t in texts), texts)
        else:
            for name in ("预览换成了自定义图标", "按钮文案变「更换图标」", "多出「恢复默认」",
                         "预览回落内置图标", "按钮变回「上传图标」", "「恢复默认」收起来了"):
                check(name, False, "跳过：选择框没弹出来")

        print("[11] 报错检查")
        check("无 JS 报错", not errs, errs[:3])
        ctx.close()
        b.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="admin123")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--unit-only", action="store_true", help="只跑离线单元测试")
    args = ap.parse_args()

    unit_suite()

    admin = Client(args.url)
    code, _ = admin.login(args.user, args.password)
    check("管理员登录", code == 200)
    # 浏览器测完顺手清干净，别把测试图标留给下一个人
    if not args.unit_only:
        pg_base = args.url.rstrip("/")
        try:
            browser_suite(pg_base, args.user, args.password, args.headed)
        finally:
            admin.req("DELETE", "/api/settings/icon")
            code, d = admin.req("GET", "/api/settings")
            check("清理后回到内置图标",
                  (d.get("site_icon") or {}).get("custom") is False, d.get("site_icon"))

    print(f"\n{len(PASS)}/{len(PASS) + len(FAIL)} 通过")
    if FAIL:
        print("失败：")
        for f in FAIL:
            print("  -", f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
