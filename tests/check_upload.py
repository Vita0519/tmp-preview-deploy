"""新建项目弹窗的端到端校验：折叠态/展开态提交时，参数都要真的带上。

只走「外部链接」模式（不落文件），建完立刻删掉，不留垃圾。
"""
import os

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
        print(f"  [!!] {name} {extra}")


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    captured = []
    pg.on("request", lambda r: captured.append(r) if "/api/projects" in r.url and r.method == "POST" else None)
    pg.goto(BASE + "/", wait_until="networkidle")
    pg.fill('input[autocomplete="username"]', USER)
    pg.fill('input[type="password"]', PASSWORD)
    pg.click('button[type="submit"]')
    pg.wait_for_url(lambda u: "/login" not in u, timeout=15000)
    pg.wait_for_timeout(500)

    token = pg.evaluate("() => localStorage.getItem('pv_api_key') || ''")

    # ---- 1. 折叠态：不改任何高级项，直接建外链 ----
    pg.click('button:has-text("新建项目")')
    pg.wait_for_timeout(400)
    pg.click('.modal .seg button:has-text("外部链接")')
    pg.fill('.modal input[placeholder="https://example.com/demo"]', "https://example.com/pv-check-1")
    pg.fill('.modal input[placeholder="用于列表展示，可中文"]', "折叠态校验")
    pg.click('.modal-foot .btn.primary')
    pg.wait_for_timeout(1200)
    body1 = (captured[-1].post_data_json or {}) if captured else {}
    check("折叠态能提交", bool(body1), body1)
    check("折叠态 hours=null（跟随默认）", body1.get("hours") is None, body1.get("hours"))
    check("折叠态 forever=false", body1.get("forever") is False, body1.get("forever"))

    # 记下刚建的 slug，稍后删
    slug1 = body1.get("slug") or ""

    # ---- 2. 展开态：勾永久保存 + 切到期删除 ----
    # 建完会自动打开详情抽屉，重载页面拿干净状态再测第二轮
    pg.goto(BASE + "/", wait_until="networkidle")
    pg.wait_for_timeout(600)
    pg.click('button:has-text("新建项目")')
    pg.wait_for_timeout(400)
    pg.click('.modal .seg button:has-text("外部链接")')
    pg.fill('.modal input[placeholder="https://example.com/demo"]', "https://example.com/pv-check-2")
    pg.fill('.modal input[placeholder="用于列表展示，可中文"]', "展开态校验")
    pg.click(".modal .advhead")
    pg.wait_for_timeout(300)
    check("展开后能看到存活时长", pg.locator('.modal .frow label:has-text("存活时长")').count() == 1)
    pg.click('.modal .check:has-text("永久保存") input')
    pg.click('.modal .advbody .seg button:has-text("删除文件")')
    pg.wait_for_timeout(200)
    summary = pg.locator(".modal .advsum").inner_text()
    check("摘要跟着变（永久 / 删除文件）", "永久" in summary and "删除" in summary, summary)
    pg.click('.modal-foot .btn.primary')
    pg.wait_for_timeout(1200)
    body2 = (captured[-1].post_data_json or {}) if captured else {}
    check("展开态 forever=true", body2.get("forever") is True, body2.get("forever"))
    slug2 = body2.get("slug") or ""

    # ---- 3. 清理：按标题前缀找回本轮建的（slug 是后端生成的，脚本里拿不到）----
    cleaned = pg.evaluate(
        """async () => {
      const d = await fetch('/api/projects?limit=300').then((r) => r.json());
      const bad = (d.items || []).filter((p) => (p.title || '').includes('校验'));
      const out = [];
      for (const p of bad) {
        const r = await fetch('/api/projects/' + encodeURIComponent(p.slug), { method: 'DELETE' });
        out.push(p.slug + ' → ' + r.status);
      }
      return out;
    }"""
    )
    print("  清理:", cleaned or "无残留")

    print(f"\n{ok} 通过 / {fail} 失败")
    b.close()
