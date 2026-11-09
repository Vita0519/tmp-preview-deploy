"""一期：收藏夹归属可见。

后端：/api/collections 要给出 owner / owners / count_own / count_foreign
前端：管理员侧栏按成员分组、成员筛选、夹里混别人项目时补 +N

造数据后自查自删，不污染站点。
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

PEER = "zz_owner_probe"
PEER_PW = "probe123456"
PEER_DISPLAY = "归属探针"
COL_A = "探针主夹"
COL_B = "探针子夹"
LINK = "https://example.com/probe"

ok = fail = 0


class Resp:
    def __init__(self, code, body):
        self.status_code = code
        self._body = body

    def json(self):
        return json.loads(self._body or b"{}")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}: {self._body[:180]!r}")


class Sess:
    """环境里没有 requests，用 urllib 顶一下；顺便关掉系统代理，否则打不到 127.0.0.1"""

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


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  [ok] {name}")
    else:
        fail += 1
        print(f"  [!!] {name}  {extra}")


def sess(username, password):
    s = Sess()
    r = s.post("/api/auth/login", {"username": username, "password": password})
    r.raise_for_status()
    return s


def cleanup(admin):
    """先删项目再删收藏夹最后删成员；成员删不掉也不拦着测试结果"""
    try:
        for p in admin.get("/api/projects?limit=0").json()["items"]:
            if p["title"].startswith("探针"):
                admin.delete(f"/api/projects/{p['slug']}")
    except Exception as e:
        print("  [clean] 清项目失败:", e)
    try:
        tree = admin.get("/api/collections").json()
        for n in tree["items"]:
            if n["name"] == COL_A:
                admin.delete(f"/api/collections/{n['id']}")
    except Exception as e:
        print("  [clean] 清收藏夹失败:", e)
    try:
        for u in admin.get("/api/agents?limit=0").json()["items"]:
            if u["username"] == PEER:
                admin.delete(f"/api/agents/{u['id']}")
    except Exception as e:
        print("  [clean] 清成员失败:", e)


# ---------------- 造数据 ----------------
admin = sess(USER, PASSWORD)
cleanup(admin)

r = admin.post(
    "/api/agents",
    {"username": PEER, "password": PEER_PW, "display_name": PEER_DISPLAY, "role": "publisher"},
)
r.raise_for_status()
peer = sess(PEER, PEER_PW)

root = peer.post("/api/collections", {"name": COL_A}).json()["collection"]
kid = peer.post("/api/collections", {"name": COL_B, "parent_id": root["id"]}).json()["collection"]
peer.post(
    "/api/projects/link",
    {"link_url": LINK, "title": "探针项目一", "collection_id": kid["id"], "visibility": "portal"},
).raise_for_status()
peer.post(
    "/api/projects/link",
    {"link_url": LINK + "/2", "title": "探针项目二", "collection_id": root["id"]},
).raise_for_status()

# ---------------- 后端 ----------------
print("\n== 后端 /api/collections ==")
tree = admin.get("/api/collections").json()
owners = tree.get("owners") or []
print("  owners:", [(o["username"], o["display_name"], o["count"], o["total"]) for o in owners])
check("owners 汇总存在且含两个人", len(owners) >= 2, owners)
check("我的组排在最前", owners and owners[0]["username"] == USER, owners[:1])
mine = next((o for o in owners if o["username"] == USER), None)
theirs = next((o for o in owners if o["username"] == PEER), None)
check("探针成员有一组", bool(theirs), owners)
check("探针组统计到 1 个根夹", theirs and theirs["count"] == 1, theirs)

probe = next((n for n in tree["items"] if n["name"] == COL_A), None)
check("节点带 owner 字段", probe and probe.get("owner") == PEER, probe and probe.get("owner"))
check("节点带 owner_display", probe and probe.get("owner_display") == PEER_DISPLAY, probe and probe.get("owner_display"))
check("节点带 owner_id", probe and probe.get("owner_id") == theirs["id"], probe and probe.get("owner_id"))
print(
    "  探针主夹 count=%s total=%s own=%s foreign=%s tf=%s kids=%s"
    % (probe and probe.get("count"), probe and probe.get("total"), probe and probe.get("count_own"),
       probe and probe.get("count_foreign"), probe and probe.get("total_foreign"),
       len(probe["children"]) if probe else 0)
)
# count = 直挂在这一层的项目数，total = 连同子夹一起算
check("主夹直挂 1 个", probe and probe.get("count") == 1, probe and probe.get("count"))
check("主夹连同子夹共 2 个", probe and probe.get("total") == 2, probe and probe.get("total"))
# 计数是「相对看的人」：管理员看别人的夹，全是 foreign
check("管理员视角下别人的项目都算 foreign", probe and probe.get("count_foreign") == 1, probe and probe.get("count_foreign"))
check("total_foreign 含子夹滚上来", probe and probe.get("total_foreign") == 2, probe and probe.get("total_foreign"))
kidrow = next((k for k in (probe or {}).get("children") or [] if k["name"] == COL_B), None)
check("子夹继承 owner", kidrow and kidrow.get("owner") == PEER, kidrow and kidrow.get("owner"))
check("子夹带自己的计数", kidrow and kidrow.get("count") == 1, kidrow and kidrow.get("count"))

# 普通成员视角：不应看到别人的夹，owners 为空
ptree = peer.get("/api/collections").json()
check("普通成员看不到 owners 汇总", not (ptree.get("owners") or []), ptree.get("owners"))
check(
    "普通成员只看到自己的夹",
    all(n.get("owner") == PEER for n in ptree["items"]),
    [(n["name"], n.get("owner")) for n in ptree["items"]],
)
pnode = next((n for n in ptree["items"] if n["name"] == COL_A), None)
# 跟管理员视角同一套口径：count_own 是直挂，total 才含子夹
check("自己的夹直挂项目算 own", pnode and pnode.get("count_own") == 1, pnode and pnode.get("count_own"))
check("自己的夹含子夹共 2 个", pnode and pnode.get("total") == 2, pnode and pnode.get("total"))
check("自己的夹没有 foreign", pnode and pnode.get("total_foreign") == 0, pnode and pnode.get("total_foreign"))

# ---------------- 前端 ----------------
print("\n== 前端侧栏 ==")


def rail(pg):
    return pg.evaluate(
        """() => {
      const q = (s) => [...document.querySelectorAll(s)];
      return {
        groups: q('.rail .railgroup').map((g) => g.innerText.replace(/\\s+/g, ' ').trim()),
        nodes: q('.rail .railnode > .railrow').map((r) => r.innerText.replace(/\\s+/g, ' ').trim()),
        hasPick: !!document.querySelector('.rail .railpick'),
        pickOpts: [...document.querySelectorAll('.rail .railpick option')].map((o) => o.textContent.trim()),
        xf: q('.rail .railrow .n .xf').map((e) => e.innerText.trim()),
      };
    }"""
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
    print("  分组:", s0["groups"])
    print("  节点:", s0["nodes"])
    check("侧栏出现成员分组", len(s0["groups"]) >= 2, s0["groups"])
    check("我的组叫「我的收藏夹」", any("我的收藏夹" in g for g in s0["groups"]), s0["groups"])
    check("别人的组带成员显示名", any(PEER_DISPLAY in g for g in s0["groups"]), s0["groups"])
    check("分组带夹数量", all(any(ch.isdigit() for ch in g) for g in s0["groups"]), s0["groups"])
    check("出现成员筛选下拉", s0["hasPick"], s0)
    check("下拉含「全部成员」", any("全部成员" in o for o in s0["pickOpts"]), s0["pickOpts"])
    check(
        "下拉含探针成员",
        any(PEER_DISPLAY in o for o in s0["pickOpts"]),
        s0["pickOpts"],
    )
    # 分组归属正确：探针主夹只能出现在探针组底下
    group_nodes = pg.evaluate(
        """() => [...document.querySelectorAll('.rail .railgw')].map((g) => ({
            head: (g.querySelector('.railgroup')?.innerText || '').replace(/\\s+/g, ' ').trim(),
            nodes: [...g.querySelectorAll('.railnode > .railrow .nm')].map((e) => e.innerText.trim()),
          }))"""
    )
    print("  分组明细:", group_nodes)
    mine_g = next((g for g in group_nodes if "我的收藏夹" in g["head"]), None)
    theirs_g = next((g for g in group_nodes if PEER_DISPLAY in g["head"]), None)
    check("探针夹落在探针组里", theirs_g and COL_A in theirs_g["nodes"], theirs_g)
    check("我的组里没有探针夹", mine_g and COL_A not in mine_g["nodes"], mine_g)
    check("每个节点只渲染一次", len(s0["nodes"]) == len(set(s0["nodes"])), s0["nodes"])
    probe_row = next((n for n in s0["nodes"] if COL_A in n), "")
    print("  探针行:", probe_row)
    check("探针行显示含子夹的总数 + 混入别人的 +N", "2" in probe_row and "+2" in probe_row, probe_row)
    check("侧栏出现 +N 徽标", "+2" in s0["xf"], s0["xf"])
    pg.screenshot(path=f"{OUT}/owner-rail.png")

    # 筛选到探针成员
    pg.select_option(".rail .railpick", str(theirs["id"]))
    pg.wait_for_timeout(600)
    s1 = rail(pg)
    print("  筛选后分组:", s1["groups"], "节点:", s1["nodes"])
    check("筛完只剩一组", len(s1["groups"]) == 1, s1["groups"])
    check("筛完只剩探针的夹", COL_A in " ".join(s1["nodes"]), s1["nodes"])
    check("筛完看不到我的夹", "书签栏" not in " ".join(s1["nodes"]), s1["nodes"])
    pg.screenshot(path=f"{OUT}/owner-rail-filtered.png")

    # 收回「全部成员」
    pg.select_option(".rail .railpick", "")
    pg.wait_for_timeout(600)
    s2 = rail(pg)
    check("复位后分组恢复", len(s2["groups"]) == len(s0["groups"]), s2["groups"])

    # 分组折叠
    head = pg.locator(".rail .railgroup", has_text="我的收藏夹").first
    head.click()
    pg.wait_for_timeout(400)
    folded = pg.evaluate(
        """() => {
          const g = [...document.querySelectorAll('.rail .railgw')].find(
            (x) => (x.querySelector('.railgroup')?.innerText || '').includes('我的收藏夹'));
          return {
            open: g.querySelector('.railgroup').classList.contains('open'),
            kids: g.querySelectorAll('.railnode').length,
          };
        }"""
    )
    check("折叠后该组节点隐藏", folded["kids"] == 0, folded)
    check("折叠后箭头状态跟着变", folded["open"] is False, folded)
    head.click()
    pg.wait_for_timeout(300)

    b.close()

cleanup(admin)
print(f"\n{ok} 通过 / {fail} 失败")
