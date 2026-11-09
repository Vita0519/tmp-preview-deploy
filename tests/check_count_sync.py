"""删除 / 新建项目后，侧栏收藏夹与分类的数量要当场跟着变，不能等刷新。

用户报的现象：45 个项目删了三个，页面不刷新的话侧栏那些数字还是 45。
"""
import json
import os
import urllib.error
import urllib.request
from http.cookiejar import CookieJar

from playwright.sync_api import sync_playwright

BASE = os.environ.get("PV_BASE", "http://127.0.0.1:8000")
USER = os.environ.get("PV_USER", "admin")
PASSWORD = os.environ.get("PV_PASS", "admin123")
OUT = os.environ.get("PV_SHOTS", "C:/tmp/shots")
os.makedirs(OUT, exist_ok=True)

COL = "校验计数"
LINK = "https://example.com/count-check"

ok = fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  [ok] {name}")
    else:
        fail += 1
        print(f"  [!!] {name}  {extra}")


class Resp:
    def __init__(self, code, body):
        self.status_code = code
        self._body = body

    def json(self):
        return json.loads(self._body or b"{}")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}: {self._body[:160]!r}")


class Sess:
    def __init__(self):
        self.op = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(CookieJar()),
        )

    def _do(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            BASE + path, data=data, method=method, headers={"Content-Type": "application/json"}
        )
        try:
            with self.op.open(req, timeout=20) as r:
                return Resp(r.status, r.read())
        except urllib.error.HTTPError as e:
            return Resp(e.code, e.read())

    def get(self, path):
        return self._do("GET", path)

    def post(self, path, body=None):
        return self._do("POST", path, body or {})

    def delete(self, path):
        return self._do("DELETE", path)


def cleanup(admin):
    try:
        for p in admin.get("/api/projects?limit=0").json()["items"]:
            if p["title"].startswith("计数"):
                admin.delete(f"/api/projects/{p['slug']}")
    except Exception as e:
        print("  [clean] 项目:", e)
    try:
        for n in admin.get("/api/collections").json()["items"]:
            if n["name"] == COL:
                admin.delete(f"/api/collections/{n['id']}")
    except Exception as e:
        print("  [clean] 收藏夹:", e)


admin = Sess()
admin.post("/api/auth/login", {"username": USER, "password": PASSWORD}).raise_for_status()
cleanup(admin)

col = admin.post("/api/collections", {"name": COL}).json()["collection"]
for i in range(3):
    admin.post(
        "/api/projects/link",
        {"link_url": f"{LINK}/{i}", "title": f"计数项目{i}", "collection_id": col["id"], "visibility": "portal"},
    ).raise_for_status()


def rail(pg):
    """侧栏数字：某个收藏夹行、以及「全部项目」那一行"""
    return pg.evaluate(
        """(name) => {
      const rows = [...document.querySelectorAll('.rail .railrow')];
      const pick = (el) => {
        const n = el.querySelector('.n');
        return n ? Number((n.innerText.match(/\\d+/) || [0])[0]) : null;
      };
      const node = rows.find((r) => (r.innerText || '').includes(name));
      const all = rows.find((r) => (r.innerText || '').includes('全部项目'));
      return { node: node ? pick(node) : null, all: all ? pick(all) : null,
               nodeText: node ? node.innerText.replace(/\\s+/g, ' ').trim() : '' };
    }""",
        COL,
    )


def rows(pg):
    return pg.evaluate(
        """() => [...document.querySelectorAll('tbody tr')]
             .filter((tr) => !tr.querySelector('.skel')).length"""
    )


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    ctx = b.new_context(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
    pg = ctx.new_page()
    pg.goto(BASE + "/", wait_until="networkidle")
    pg.fill('input[autocomplete="username"]', USER)
    pg.fill('input[type="password"]', PASSWORD)
    pg.click('button[type="submit"]')
    pg.wait_for_url(lambda u: "/login" not in u, timeout=15000)
    pg.wait_for_timeout(1200)

    s0 = rail(pg)
    print("初始侧栏:", s0)
    check("新建的夹在侧栏里显示 3 个", s0["node"] == 3, s0)

    # 进这个夹，勾三条，批量删除
    pg.locator(".rail .railrow", has_text=COL).first.click()
    pg.wait_for_timeout(900)
    n0 = rows(pg)
    check("夹里列出 3 条", n0 == 3, n0)

    pg.locator('thead input[type="checkbox"]').first.check()
    pg.wait_for_timeout(300)
    pg.locator(".bulkbar .btn.danger", has_text="删除").click()
    pg.wait_for_selector(".modal", timeout=5000)
    pg.locator(".modal button", has_text="删除").last.click()
    pg.wait_for_timeout(1500)

    s1 = rail(pg)
    print("批量删除后侧栏:", s1)
    check("批量删除后，夹的计数当场归零（不等刷新）", s1["node"] == 0, s1)
    check("「全部项目」的数字也跟着减", s1["all"] == s0["all"] - 3, f"{s1['all']} vs {s0['all']}")
    check("列表也空了", rows(pg) == 0, rows(pg))
    pg.screenshot(path=f"{OUT}/count-sync-after-bulk-delete.png")

    # 再建一条：走上传弹窗的「登记外链」太快，直接用接口建，然后验证抽屉里删掉也会同步
    admin.post(
        "/api/projects/link",
        {"link_url": f"{LINK}/single", "title": "计数单删", "collection_id": col["id"]},
    ).raise_for_status()
    pg.reload(wait_until="networkidle")
    pg.wait_for_timeout(1200)
    s2 = rail(pg)
    check("外部新增后刷新页面能看到 1 个", s2["node"] == 1, s2)

    # 抽屉里删除单条
    pg.locator(".rail .railrow", has_text=COL).first.click()
    pg.wait_for_timeout(900)
    pg.locator("tbody tr").first.click()
    pg.wait_for_selector(".drawer", timeout=6000)
    pg.wait_for_timeout(500)
    pg.locator(".drawer button", has_text="删除项目").first.click()
    pg.wait_for_selector(".modal", timeout=5000)
    pg.locator(".modal button", has_text="删除").last.click()
    pg.wait_for_timeout(1600)
    s3 = rail(pg)
    print("抽屉删除后侧栏:", s3)
    check("抽屉删单条后计数当场归零", s3["node"] == 0, s3)
    pg.screenshot(path=f"{OUT}/count-sync-after-drawer-delete.png")

    b.close()

cleanup(admin)
print(f"\n{ok} 通过 / {fail} 失败")
