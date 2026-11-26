"""门户卡片/列表的「复制链接」按钮：点击不跳转、出现打勾与「已复制」气泡、剪贴板内容正确。"""
import os
import sys

from playwright.sync_api import sync_playwright

BASE = os.environ.get("PV_BASE", "http://127.0.0.1:8000")
USER = os.environ.get("PV_USER", "admin")
PASSWORD = os.environ.get("PV_PASS", "admin123")
OUT = os.environ.get("PV_SHOTS", "C:/tmp/shots")
os.makedirs(OUT, exist_ok=True)


def login(ctx):
    p = ctx.new_page()
    p.goto(BASE + "/", wait_until="networkidle")
    p.fill('input[autocomplete="username"]', USER)
    p.fill('input[type="password"]', PASSWORD)
    p.click('button[type="submit"]')
    p.wait_for_url(lambda u: "/login" not in u, timeout=15000)
    return p

ok = 0
bad = []


def chk(name, cond, extra=""):
    global ok
    if cond:
        ok += 1
        print(f"  [ok] {name}")
    else:
        bad.append(name + (f" -> {extra}" if extra else ""))
        print(f"  [!!] {name} {extra}")


def read_clipboard(pg):
    return pg.evaluate("navigator.clipboard.readText()")


def full(p):
    """data-path 可能是站内路径，也可能直接是外链项目的完整地址。"""
    return p if p.startswith("http") else BASE.rstrip("/") + p


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    ctx = b.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
    ctx.grant_permissions(["clipboard-read", "clipboard-write"])
    pg = login(ctx)
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    # dev server 下 favicon.ico 偶尔 404，与功能无关，忽略
    pg.on("console", lambda m: errs.append(m.text)
          if m.type == "error" and "favicon" not in m.text and "404" not in m.text else None)

    pg.goto(BASE + "/", wait_until="networkidle")
    pg.wait_for_timeout(400)

    cards = pg.locator("#grid .card").count()
    rows = pg.locator("#rows .row").count()
    btns = pg.locator("#grid .cbtn").count()
    rbtns = pg.locator("#rows .cbtn").count()
    print(f"卡片 {cards} / 列表行 {rows} / 卡片按钮 {btns} / 行内按钮 {rbtns}")
    chk("每张卡片都有复制按钮", cards > 0 and btns == cards, f"{btns}/{cards}")
    chk("每个列表行都有复制按钮", rows > 0 and rbtns == rows, f"{rbtns}/{rows}")
    chk("卡片按钮带 data-path", pg.locator("#grid .cbtn[data-path]").count() == cards)
    # 外链项目也走本地短链（先计数再 302），所以 data-path 应当全是站内 /v/
    paths = pg.eval_on_selector_all("#grid .cbtn", "els => els.map(e => e.dataset.path)")
    chk("复制按钮都是站内短链", all(p.startswith("/v/") for p in paths), paths[:3])
    chk("按钮默认无 done 类", pg.locator(".cbtn.done").count() == 0)
    chk("气泡文案为「已复制」", pg.locator("#grid .cbtn").first.locator(".tip").inner_text() == "已复制")

    # ---- 卡片模式 ----
    print("卡片模式：")
    btn = pg.locator("#grid .card").first.locator(".cbtn")
    path = btn.get_attribute("data-path")
    url0 = pg.url
    box = btn.bounding_box()
    ring = pg.locator("#grid .card").first.locator(".ring").bounding_box()
    overlap = not (
        box["x"] + box["width"] <= ring["x"]
        or ring["x"] + ring["width"] <= box["x"]
        or box["y"] + box["height"] <= ring["y"]
        or ring["y"] + ring["height"] <= box["y"]
    )
    chk("按钮不与访问圆环重叠", not overlap, f"btn={box} ring={ring}")
    # 按钮在最上层（不在覆盖式链接之下）
    top_tag = pg.evaluate(
        """([x,y]) => { const el=document.elementFromPoint(x,y); return el&&el.tagName; }""",
        [box["x"] + box["width"] / 2, box["y"] + box["height"] / 2],
    )
    chk("按钮可被点中（不被 .hit 遮住）", top_tag in ("BUTTON", "svg", "path"), str(top_tag))

    btn.click()
    pg.wait_for_timeout(260)
    chk("点击后不跳转", pg.url == url0, pg.url)
    chk("点击后出现 done 类", "done" in (btn.get_attribute("class") or ""))
    chk("气泡可见", btn.locator(".tip").evaluate("e => getComputedStyle(e).opacity") == "1")
    tip_text = btn.locator(".tip").inner_text()
    chk("气泡显示「已复制」", tip_text == "已复制", tip_text)
    chk("卡片按钮切换为打勾图标",
       btn.locator(".ic-done").is_visible() and not btn.locator(".ic-copy").is_visible())
    clip = read_clipboard(pg)
    chk("剪贴板 = 完整直链", clip == full(path), clip)
    pg.screenshot(path=f"{OUT}/30-copy-card.png", clip={"x": 0, "y": 0, "width": 1280, "height": 620})
    pg.wait_for_timeout(1700)
    chk("1.6s 后自动恢复", "done" not in (btn.get_attribute("class") or ""))
    chk("恢复后气泡隐藏", btn.locator(".tip").evaluate("e => getComputedStyle(e).opacity") == "0")

    # ---- 列表模式 ----
    print("列表模式：")
    pg.click("#viewseg button[data-view='list']")
    pg.wait_for_timeout(320)
    chk("#rows 可见 / #grid 隐藏",
       pg.locator("#rows").is_visible() and not pg.locator("#grid").is_visible())
    lbtn = pg.locator("#rows .row").first.locator(".cbtn")
    lpath = lbtn.get_attribute("data-path")
    lb = lbtn.bounding_box()
    ltop = pg.evaluate(
        """([x,y]) => { const el=document.elementFromPoint(x,y); return el&&el.tagName; }""",
        [lb["x"] + lb["width"] / 2, lb["y"] + lb["height"] / 2],
    )
    chk("行内按钮可被点中", ltop in ("BUTTON", "svg", "path"), str(ltop))
    lbtn.click()
    pg.wait_for_timeout(260)
    chk("行内点击后不跳转", pg.url == url0, pg.url)
    chk("行内按钮出现 done 类", "done" in (lbtn.get_attribute("class") or ""))
    chk("行内气泡可见",
       lbtn.locator(".tip").evaluate("e => getComputedStyle(e).opacity") == "1")
    chk("行内剪贴板正确", read_clipboard(pg) == full(lpath))
    row_box = pg.locator("#rows .row").first.bounding_box()
    pg.screenshot(path=f"{OUT}/31-copy-list.png", clip={
        "x": 0, "y": 0, "width": 1280, "height": min(900, row_box["y"] + row_box["height"] + 90)})
    # 气泡不越出行框右边界
    tb = lbtn.locator(".tip").bounding_box()
    chk("行内气泡不溢出容器", tb["x"] >= 0 and tb["x"] + tb["width"] <= 1280, str(tb))

    # ---- 移动端 ----
    print("移动端：")
    ctx2 = b.new_context(
        viewport={"width": 390, "height": 844}, device_scale_factor=2,
        is_mobile=True, has_touch=True,
    )
    ctx2.grant_permissions(["clipboard-read", "clipboard-write"])
    m = login(ctx2)
    m.goto(BASE + "/", wait_until="networkidle")
    m.wait_for_timeout(400)
    m.evaluate("localStorage.setItem('pv_view','grid')")
    m.reload(wait_until="networkidle")
    m.wait_for_timeout(400)
    mb = m.locator("#grid .card").first.locator(".cbtn").bounding_box()
    mcard = m.locator("#grid .card").first.bounding_box()
    chk("移动端按钮在卡内", mb["x"] > mcard["x"] and mb["x"] + mb["width"] < mcard["x"] + mcard["width"] + 1)
    chk("无横向溢出", m.evaluate("document.documentElement.scrollWidth <= 390"),
       str(m.evaluate("document.documentElement.scrollWidth")))
    m.locator("#grid .card").first.locator(".cbtn").tap()
    m.wait_for_timeout(260)
    chk("移动端点按也出「已复制」",
       "done" in (m.locator("#grid .card").first.locator(".cbtn").get_attribute("class") or ""))
    m.screenshot(path=f"{OUT}/32-copy-mobile.png")

    chk("无 JS 报错", not errs, "; ".join(errs[:3]))
    b.close()

print(f"\n{ok} 项通过，{len(bad)} 项失败")
if bad:
    for x in bad:
        print("  -", x)
    sys.exit(1)
