"""验收新建项目弹窗：两列对齐、首屏是否还要滚、高级区展开正常。"""
import os

from playwright.sync_api import sync_playwright

BASE = os.environ.get("PV_BASE", "http://127.0.0.1:8000")
USER = os.environ.get("PV_USER", "admin")
PASSWORD = os.environ.get("PV_PASS", "admin123")
OUT = os.environ.get("PV_SHOTS", "C:/tmp/shots")
os.makedirs(OUT, exist_ok=True)

MEASURE = """() => {
  const body = document.querySelector('.modal-body');
  const two = document.querySelector('.modal .frow.two');
  const ins = [...two.querySelectorAll(':scope > .frow > input')];
  const hs = [...two.querySelectorAll(':scope > .frow > .hint')];
  const adv = document.querySelector('.modal .adv');
  return {
    bodyW: body.clientWidth,
    scrollH: body.scrollHeight,
    clientH: body.clientHeight,
    overflow: body.scrollHeight - body.clientHeight,
    modalW: Math.round(document.querySelector('.modal').getBoundingClientRect().width),
    inputs: ins.map((i) => { const r = i.getBoundingClientRect(); return {w: Math.round(r.width), h: Math.round(r.height), top: Math.round(r.top)}; }),
    hints: hs.map((h) => {
      const cs = getComputedStyle(h);
      const lh = parseFloat(cs.lineHeight) || 16;
      const hh = h.getBoundingClientRect().height;
      return {lines: Math.round(hh / lh), w: Math.round(h.getBoundingClientRect().width)};
    }),
    advH: adv ? Math.round(adv.getBoundingClientRect().height) : null,
    advSum: adv ? adv.querySelector('.advsum').innerText : null,
  };
}"""


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
    pg.wait_for_timeout(500)
    return pg, errs


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")

    ctx = b.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
    pg, errs = login(ctx)

    pg.click('button:has-text("新建项目")')
    pg.wait_for_timeout(600)
    pg.screenshot(path=f"{OUT}/up-10-collapsed.png")
    d = pg.evaluate(MEASURE)
    tail = f"还要滚 {d['overflow']}px" if d["overflow"] > 2 else "一屏装下 ✓"
    print(f"弹窗 {d['modalW']}px · body 可视高 {d['clientH']} / 内容 {d['scrollH']} → {tail}")
    print("名称/Slug 输入框:", d["inputs"])
    print("两列 hint 行数:", d["hints"])
    print("高级条高:", d["advH"], " 摘要:", d["advSum"])

    # 标签上限应跟站点设置一致（后端 /api/meta 的 tags.max_per_project）
    lbl = pg.locator('.modal .frow label:has-text("标签")').inner_text().replace("\n", " ")
    hint = pg.locator('.modal .frow:has(.tagprev), .modal .frow').filter(has_text="标签").first.inner_text()
    meta_cap = pg.evaluate("() => fetch('/api/meta').then(r=>r.json()).then(d=>d.tags.max_per_project)")
    print(f"标签行: {lbl!r}  站点上限={meta_cap}  →", "一致 ✓" if f"/{meta_cap}" in lbl else "不一致 ✗")

    pg.click(".modal .advhead")
    pg.wait_for_timeout(450)
    pg.screenshot(path=f"{OUT}/up-11-expanded.png")
    d2 = pg.evaluate(MEASURE)
    print(f"\n展开后 body 内容高 {d2['scrollH']}（滚 {d2['overflow']}px）· 高级区 {d2['advH']}px")
    print("展开后摘要:", d2["advSum"])

    pg.click('.modal .seg button:has-text("外部链接")')
    pg.wait_for_timeout(400)
    pg.screenshot(path=f"{OUT}/up-12-link.png")

    ctx2 = b.new_context(viewport={"width": 430, "height": 860}, device_scale_factor=2)
    pg2, _ = login(ctx2)
    pg2.click('button:has-text("新建项目")')
    pg2.wait_for_timeout(600)
    pg2.screenshot(path=f"{OUT}/up-13-mobile.png")
    print("\n窄屏弹窗宽:", round(pg2.evaluate("() => document.querySelector('.modal').getBoundingClientRect().width")))

    print("console errors:", errs[:5])
    b.close()
