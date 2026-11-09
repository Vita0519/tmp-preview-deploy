"""创建成员后的「复制登录命令 / 复制 Key」要真的写进剪贴板并弹 toast。"""
import os
import time

from playwright.sync_api import sync_playwright

BASE = os.environ.get("PV_BASE", "http://127.0.0.1:8000")
USER = os.environ.get("PV_USER", "admin")
PASSWORD = os.environ.get("PV_PASS", "admin123")

ok = fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  [ok] {name}")
    else:
        fail += 1
        print(f"  [!!] {name}  {extra}")


uname = f"copycheck{int(time.time()) % 100000}"
pw = "pw-for-copy-check"


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    ctx = b.new_context(viewport={"width": 1500, "height": 950})
    ctx.grant_permissions(["clipboard-read", "clipboard-write"], origin=BASE)
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append("pageerror: " + str(e)))
    pg.on("console", lambda m: errs.append("console: " + m.text) if m.type == "error" else None)

    pg.goto(BASE + "/", wait_until="networkidle")
    pg.fill('input[autocomplete="username"]', USER)
    pg.fill('input[type="password"]', PASSWORD)
    pg.click('button[type="submit"]')
    pg.wait_for_url(lambda u: "/login" not in u, timeout=15000)

    pg.goto(BASE + "/agents", wait_until="networkidle")
    pg.wait_for_timeout(800)

    # 加一个临时成员，拿到「凭据（只显示一次）」弹窗
    pg.click('button:has-text("添加成员")')
    pg.wait_for_timeout(400)
    pg.fill('.modal input[placeholder*="小写字母"]', uname)
    pg.fill('.modal input[placeholder="用于列表展示"]', "复制校验")
    pg.fill('.modal input[placeholder="留空自动生成"]', pw)
    pg.click('.modal .modal-foot .btn.primary')
    pg.wait_for_timeout(1200)

    dialog = pg.locator('.modal:has-text("凭据（只显示一次）")')
    check("创建后弹出凭据弹窗", dialog.count() == 1, dialog.count())
    body = dialog.inner_text()
    check("弹窗里带着账号和密码", uname in body and pw in body, body[:80])

    # ---- 复制登录命令 ----
    pg.evaluate("() => navigator.clipboard.writeText('__sentinel__')")
    dialog.locator('button:has-text("复制登录命令")').click()
    pg.wait_for_timeout(700)
    clip = pg.evaluate("() => navigator.clipboard.readText()")
    print(f"剪贴板 = {clip}")
    check("登录命令写进了剪贴板（不是哨兵值）", clip != "__sentinel__", clip)
    check("命令以 agentctl login --url 开头", clip.startswith("agentctl login --url "), clip)
    check("命令里带着站点地址", BASE in clip, clip)
    check("命令里带着账号", f"--username {uname}" in clip, clip)
    check("命令里密码带单引号（防特殊字符被 shell 解释）", f"--password '{pw}'" in clip, clip)
    check("点了之后有「已复制」提示", pg.locator('.toast:has-text("已复制")').count() >= 1)

    # ---- 复制 Key ----
    pg.wait_for_timeout(600)
    pg.evaluate("() => navigator.clipboard.writeText('__sentinel__')")
    dialog.locator('button:has-text("复制 Key")').click()
    pg.wait_for_timeout(700)
    key = pg.evaluate("() => navigator.clipboard.readText()")
    check("API Key 写进了剪贴板", key != "__sentinel__" and len(key) > 10, key[:12] + "…")

    # ---- 关掉弹窗，清理成员 ----
    pg.click('.modal .modal-foot .btn.primary')
    pg.wait_for_timeout(600)
    ok_del = pg.evaluate(
        """async (u) => {
      const d = await fetch('/api/agents?limit=0&q=' + encodeURIComponent(u)).then((r) => r.json());
      const hit = (d.items || []).find((a) => a.username === u);
      if (!hit) return 'not-found';
      const r = await fetch('/api/agents/' + hit.id, { method: 'DELETE' });
      return 'deleted:' + r.status;
    }""",
        uname,
    )
    print(f"清理 {uname} → {ok_del}")

    # 进登录页前会探一次 /api/auth/me，401 是预期内的资源加载噪声
    real_errs = [
        e for e in errs
        if "__sentinel__" not in e and not ("Failed to load resource" in e and "401" in e)
    ]
    check("全程没有 JS 报错", not real_errs, real_errs[:2])

    print(f"\n{ok} 通过 / {fail} 失败")
    b.close()
