#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分组（项目层级归类）：两级树、归类、删分组时项目去哪。

以前项目是一整片平铺，没有归类。现在做成「分组 → 子分组」两层，
项目挂在叶子上；删分组默认只删壳，项目退回「未归类」，不连坐。

覆盖：
  [1] 建分组
      1. 新建一级分组
      2. 同级重名 → 409
      3. 空名 / 超 20 字 → 422
      4. 建子分组（第二级）
      5. 子分组下再挂子分组（第三级）→ 422
      5b. 带子分组的一级分组挪成子级 → 422（以前能绕过去出现第三层）
  [2] 树与计数
      6. 树里根节点带 children
      7. 父分组 total 含子分组，count 只算直属
      8. 全部项目的数 = 各分组合计 + 未归类
  [3] 归类
      9. 上传时直接指定分组
     10. PATCH 把项目挪进 / 挪出分组
     11. 批量归类（bulk action=collection）
     12. 按分组筛选（含子分组）
     13. collection=none 只出未归类
  [4] 权限
     14. 成员动不了别人的分组
     15. 成员的分组里看不到别人的项目计数
     15b. 管理员批量把别人的项目放进自己的分组 → 跳过
  [5] 删分组
     16. 删空壳：子分组一起删，项目退回未归类
     17. with_projects=1：项目连记录一起删
  [7] 侧栏折叠 & 可见性分类（浏览器）
     20. 点折叠按钮：228 → 64，只留图标
     21. 折叠状态落 localStorage，刷新后还是收起的
     22. 点「门户可见」：列表条数 = 该分类上的数字，且只有它高亮
     23. 点「全部项目」：可见性筛选被清掉

用法: python tests/check_collections.py [--url http://127.0.0.1:8000] [--headed]
"""
import argparse
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_test import FAIL, PASS, Client, check, multipart  # noqa: E402

HTML = b"<!doctype html><meta charset=utf-8><h1>collections</h1>"


def upload(c: Client, slug: str, title: str, collection=None):
    fields = {"slug": slug, "title": title, "hours": "2", "allow_download": "1"}
    if collection not in (None, ""):
        fields["collection"] = str(collection)
    body, ct = multipart(fields, [("files", "index.html", HTML)])
    return c.req("POST", "/api/projects", body, ct=ct)


def totals(c: Client) -> dict:
    code, d = c.req("GET", "/api/projects?limit=1")
    return d.get("total") if code == 200 else -1


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

    made_colls: list[int] = []
    made_slugs: list[str] = []
    made_agents: list[str] = []

    try:
        print("[1] 建分组")
        code, d = admin.req("POST", "/api/collections", {"name": f"办公{sfx}"})
        root = d.get("collection") or {}
        made_colls.append(root.get("id"))
        check("新建一级分组", code == 200 and root.get("name") == f"办公{sfx}", f"{code} {d}")
        check("一级分组 parent_id 为空", root.get("parent_id") is None, root.get("parent_id"))

        code, d = admin.req("POST", "/api/collections", {"name": f"办公{sfx}"})
        check("同级重名 → 409", code == 409, f"{code} {d}")

        code, d = admin.req("POST", "/api/collections", {"name": "   "})
        check("空名 → 422", code == 422, f"{code} {d}")
        code, d = admin.req("POST", "/api/collections", {"name": "很" * 21})
        check("超过 20 个字 → 422", code == 422, f"{code} {d}")
        code, d = admin.req("POST", "/api/collections", {"name": "很" * 20})
        check("正好 20 个字可以", code == 200, f"{code} {d}")
        if code == 200:
            made_colls.append(d["collection"]["id"])

        code, d = admin.req("POST", "/api/collections", {"name": f"报表{sfx}", "parent_id": root["id"]})
        kid = d.get("collection") or {}
        made_colls.append(kid.get("id"))
        check("建子分组", code == 200 and kid.get("parent_id") == root["id"], f"{code} {d}")

        code, d = admin.req("POST", "/api/collections", {"name": f"更深{sfx}", "parent_id": kid["id"]})
        check("第三级 → 422", code == 422, f"{code} {d}")

        print("[2] 树与计数")
        slug_a = f"col{sfx}-a"
        slug_b = f"col{sfx}-b"
        slug_c = f"col{sfx}-c"
        code, d = upload(admin, slug_a, f"根分组项目{sfx}", root["id"])
        made_slugs.append(slug_a)
        check("上传时直接指定分组", code == 200, f"{code} {d}")
        check("项目带上了分组名",
              (d.get("collection") or {}).get("name") == f"办公{sfx}", d.get("collection"))
        code, d = upload(admin, slug_b, f"子分组项目{sfx}", kid["id"])
        made_slugs.append(slug_b)
        check("项目可以挂在子分组上", code == 200, f"{code} {d}")
        code, d = upload(admin, slug_c, f"未归类项目{sfx}")
        made_slugs.append(slug_c)
        check("不指定分组 = 未归类", code == 200 and d.get("collection") is None, d.get("collection"))

        code, tree = admin.req("GET", "/api/collections")
        check("取分组树", code == 200 and isinstance(tree.get("items"), list), code)
        node = next((n for n in tree["items"] if n["id"] == root["id"]), None)
        check("根节点在树里", node is not None, [n["id"] for n in tree["items"]])
        check("根节点带 children", any(k["id"] == kid["id"] for k in node.get("children") or []),
              node.get("children"))
        check("父分组 total 含子分组（2）", node.get("total") == 2, node.get("total"))
        check("父分组 count 只算直属（1）", node.get("count") == 1, node.get("count"))
        check("未归类数 ≥ 1", tree.get("unassigned", 0) >= 1, tree.get("unassigned"))
        roots_sum = sum(n["total"] for n in tree["items"])
        check("total = 各分组合计 + 未归类",
              tree.get("total") == roots_sum + tree.get("unassigned", 0),
              f"{tree.get('total')} vs {roots_sum}+{tree.get('unassigned')}")
        check("total 与项目列表总数一致", tree.get("total") == totals(admin),
              f"{tree.get('total')} vs {totals(admin)}")

        print("[3] 归类")
        code, d = admin.req("PATCH", f"/api/projects/{slug_c}", {"collection_id": kid["id"]})
        check("PATCH 把项目挪进子分组",
              code == 200 and (d.get("collection") or {}).get("id") == kid["id"], f"{code} {d.get('collection')}")
        code, d = admin.req("PATCH", f"/api/projects/{slug_c}", {"collection_id": None})
        check("PATCH 挪回未归类", code == 200 and d.get("collection") is None, f"{code} {d.get('collection')}")
        code, d = admin.req("PATCH", f"/api/projects/{slug_c}", {"collection_id": 999999})
        check("挂到不存在的分组 → 404", code == 404, f"{code} {d}")

        code, d = admin.req("POST", "/api/projects/bulk",
                            {"action": "collection", "slugs": [slug_c], "collection_id": kid["id"]})
        check("批量归类", code == 200 and d.get("done") == 1, f"{code} {d}")
        code, d = admin.req("GET", f"/api/projects/{slug_c}")
        check("批量归类生效", (d.get("collection") or {}).get("id") == kid["id"], d.get("collection"))

        code, d = admin.req("GET", f"/api/projects?collection={root['id']}")
        got = {p["slug"] for p in d.get("items", [])}
        check("按根分组筛选含子分组", got == {slug_a, slug_b, slug_c}, got)

        code, d = admin.req("GET", f"/api/projects?collection={kid['id']}")
        got = {p["slug"] for p in d.get("items", [])}
        check("按子分组筛选只出子分组里的", got == {slug_b, slug_c}, got)

        code, d = admin.req("GET", "/api/projects?collection=none")
        got = {p["slug"] for p in d.get("items", [])}
        check("collection=none 不含已归类的", slug_a not in got and slug_b not in got, len(got))
        check("collection=none 里都是 collection 为空的",
              all(p.get("collection") is None for p in d.get("items", [])), "")

        print("[4] 权限")
        agent_name = f"cb{suffix_short()}"
        code, d = admin.req("POST", "/api/agents", {"username": agent_name, "display_name": "分组测试"})
        made_agents.append(agent_name)
        check("建一个成员账号", code == 200, f"{code} {d}")
        agent = Client(args.url)
        agent.token = (d or {}).get("api_key") or ""

        code, d = agent.req("PATCH", f"/api/collections/{root['id']}", {"name": f"抢{sfx}"})
        check("成员改不了别人的分组", code in (403, 404), f"{code} {d}")
        code, d = agent.req("DELETE", f"/api/collections/{root['id']}")
        check("成员删不了别人的分组", code in (403, 404), f"{code} {d}")

        code, d = agent.req("POST", "/api/collections", {"name": f"我的{sfx}"})
        mine = d.get("collection") or {}
        made_colls.append(mine.get("id"))
        check("成员能建自己的分组", code == 200, f"{code} {d}")
        code, tree2 = agent.req("GET", "/api/collections")
        ids = {n["id"] for n in tree2.get("items", [])}
        check("成员只看到自己的分组", root["id"] not in ids and mine.get("id") in ids, sorted(ids))
        check("成员的未归类数不含别人的项目", tree2.get("unassigned", 0) == 0, tree2.get("unassigned"))

        print("[4.5] 归属一致（回归）")
        # 管理员把成员的项目批量放进自己的分组 → 必须被跳过，不能产生「主人找不到的分组」
        slug_m = f"cm-{sfx}"
        body, ct = multipart({"slug": slug_m, "title": f"成员项目{sfx}", "hours": "2"},
                             [("files", "index.html", HTML)])
        agent.req("POST", "/api/projects", body, ct=ct, raw=True)
        code, d = admin.req("POST", "/api/projects/bulk",
                            {"slugs": [slug_m], "action": "collection", "collection_id": root["id"]})
        check("管理员批量放别人的项目进自己分组 → 跳过",
              code == 200 and d.get("skipped") == 1 and d.get("done") == 0, f"{code} {d}")
        code, d = agent.req("GET", "/api/projects?collection=none")
        check("该项目仍在成员自己的未归类里",
              slug_m in {p["slug"] for p in d.get("items", [])}, [p["slug"] for p in d.get("items", [])][:5])
        admin.req("DELETE", f"/api/projects/{slug_m}")

        # 带子分组的一级分组不能挪成别人的子级（否则出现第三层）
        code, other = admin.req("POST", "/api/collections", {"name": f"另一个{sfx}"})
        oid = (other.get("collection") or {}).get("id")
        made_colls.append(oid)
        code, d = admin.req("PATCH", f"/api/collections/{root['id']}", {"parent_id": oid})
        check("带子分组的分组挪成子级 → 422", code == 422, f"{code} {d}")
        code, tree3 = admin.req("GET", "/api/collections")
        depth_ok = all(not g.get("children") for n in tree3.get("items", []) for g in n.get("children", []))
        check("树里仍然最多两层", depth_ok)

        print("[5.5] 可见性分类")
        code, tree = admin.req("GET", "/api/collections")
        vis = tree.get("visibility") or {}
        check("树里带三档可见性计数", set(vis) == {"portal", "link", "private"}, vis)
        check("三档之和等于总数", sum(vis.values()) == tree.get("total"),
              f"{vis} vs {tree.get('total')}")
        for k, label in (("portal", "门户可见"), ("link", "持链接"), ("private", "仅自己")):
            code, d = admin.req("GET", f"/api/projects?visibility={k}&limit=1")
            check(f"{label}计数与筛选结果一致", vis.get(k) == d.get("total"),
                  f"{vis.get(k)} vs {d.get('total')}")

        print("[5] 删分组")
        code, d = admin.req("DELETE", f"/api/collections/{kid['id']}")
        check("删子分组只删壳", code == 200 and d.get("removed") == 1, f"{code} {d}")
        check("里面的项目退回未归类", d.get("moved_to_unassigned") == 2, d.get("moved_to_unassigned"))
        code, d = admin.req("GET", f"/api/projects/{slug_b}")
        check("项目本身还在", code == 200 and d.get("collection") is None, f"{code} {d.get('collection')}")

        code, d = admin.req("DELETE", f"/api/collections/{root['id']}?with_projects=1")
        check("with_projects=1 连项目一起删", code == 200 and d.get("deleted_projects") == 1, f"{code} {d}")
        code, _ = admin.req("GET", f"/api/projects/{slug_a}")
        check("项目记录真的没了", code == 404, code)
        code, _ = admin.req("GET", f"/api/projects/{slug_b}")
        check("没在分组里的项目不受影响", code == 200, code)

        print("[6] 浏览器")
        browser_suite(args.url.rstrip("/"), args.user, args.password, args.headed, sfx)
    finally:
        for cid in made_colls:
            if cid:
                admin.req("DELETE", f"/api/collections/{cid}?with_projects=1")
        for s in made_slugs:
            admin.req("DELETE", f"/api/projects/{s}")
        for name in made_agents:
            admin.req("DELETE", f"/api/agents/{name}")

    print(f"\n{len(PASS)}/{len(PASS) + len(FAIL)} 通过")
    if FAIL:
        print("失败：")
        for f in FAIL:
            print("  -", f)
        return 1
    return 0


def suffix_short() -> str:
    return uuid.uuid4().hex[:5]


def browser_suite(base: str, user: str, password: str, headed: bool, sfx: str) -> None:
    """侧栏：新建 → 出现 → 点进去筛选 → 更多菜单里删除。"""
    from playwright.sync_api import sync_playwright

    name = f"考{sfx}"
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=not headed)
        pg = b.new_context(viewport={"width": 1440, "height": 900}).new_page()
        errs = []

        pg.goto(base + "/login", wait_until="domcontentloaded")
        pg.fill('input[autocomplete="username"]', user)
        pg.fill('input[type="password"]', password)
        pg.click('button[type="submit"]')
        pg.wait_for_url(lambda u: "/login" not in u, timeout=15000)

        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: errs.append(m.text)
              if m.type == "error" and "401" not in m.text else None)

        pg.goto(base + "/", wait_until="domcontentloaded")
        pg.wait_for_selector(".railrow", timeout=15000)
        pg.wait_for_timeout(300)

        print("[6.1] 侧栏新建")
        pg.click(".railhead .railadd")
        pg.wait_for_selector(".railedit .input", timeout=5000)
        pg.fill(".railedit .input", name)
        pg.keyboard.press("Enter")
        pg.wait_for_selector(f".railrow:has-text('{name}')", timeout=8000)
        check("新建后侧栏立刻出现", pg.locator(f".railrow:has-text('{name}')").count() >= 1)

        row = pg.locator(f".railedit .input")
        check("保存后输入框收起", row.count() == 0, row.count())

        print("[6.2] 点一下筛选")
        pg.locator(f".railrow:has-text('{name}')").first.click()
        pg.wait_for_timeout(700)
        check("选中后高亮", pg.eval_on_selector(".railrow.on", "el => el.innerText").find(name) >= 0,
              pg.eval_on_selector(".railrow.on", "el => el.innerText"))
        check("空夹筛出 0 条",
              "共 0 条" in pg.inner_text("text=共 ").split("\n")[0]
              or "共 0 条" in pg.locator("text=共 ").first.inner_text(),
              pg.locator("text=共 ").first.inner_text())

        print("[6.3] 更多菜单删除")
        pg.locator(f".railrow:has-text('{name}')").first.hover()
        pg.locator(f".railrow:has-text('{name}')").first.locator(".dots").click()
        pg.wait_for_selector(".railmenu", timeout=5000)
        pg.locator(".railmenu button.danger").first.click()
        pg.wait_for_selector(".modal", timeout=5000)
        pg.locator(".modal button", has_text="删除").last.click()
        pg.wait_for_timeout(900)
        check("确认后侧栏里消失", pg.locator(f".railrow:has-text('{name}')").count() == 0)

        print("[7.1] 可见性分类")
        vis_row = pg.locator(".railrow", has_text="门户可见").first
        want = int(vis_row.inner_text().split("\n")[-1].strip() or 0)
        vis_row.click()
        pg.wait_for_timeout(800)
        got = pg.locator("text=共 ").first.inner_text()
        check("点「门户可见」筛出的条数 = 分类上的数字", f"共 {want} 条" in got, f"{got} vs {want}")
        check("高亮落在「门户可见」上",
              "门户可见" in pg.eval_on_selector(".railrow.on", "el => el.innerText"),
              pg.eval_on_selector(".railrow.on", "el => el.innerText"))

        pg.locator(".railrow", has_text="全部项目").first.click()
        pg.wait_for_timeout(800)
        check("点「全部项目」把可见性清掉",
              pg.eval_on_selector(".railrow.on", "el => el.innerText").find("全部项目") >= 0,
              pg.eval_on_selector(".railrow.on", "el => el.innerText"))

        print("[7.2] 侧栏折叠")
        w0 = pg.evaluate("() => document.querySelector('.sidebar').getBoundingClientRect().width")
        pg.click(".navtoggle")
        pg.wait_for_timeout(450)
        w1 = pg.evaluate("() => document.querySelector('.sidebar').getBoundingClientRect().width")
        check("点一下侧栏收窄", w1 < w0 and w1 <= 70, f"{w0} → {w1}")
        check("收起后文字标签不占位",
              pg.evaluate("() => { const l=document.querySelector('.nav-item .lbl'); return l? l.getBoundingClientRect().width : -1 }") == 0)
        check("内容区跟着往左挪",
              pg.evaluate("() => getComputedStyle(document.querySelector('.main')).marginLeft") == "64px",
              pg.evaluate("() => getComputedStyle(document.querySelector('.main')).marginLeft"))

        pg.reload(wait_until="domcontentloaded")
        pg.wait_for_selector(".railrow", timeout=15000)
        pg.wait_for_timeout(400)
        w2 = pg.evaluate("() => document.querySelector('.sidebar').getBoundingClientRect().width")
        check("刷新后还是收起的（记在本地）", w2 <= 70, w2)
        pg.click(".navtoggle")
        pg.wait_for_timeout(400)
        check("再点一下能展开",
              pg.evaluate("() => document.querySelector('.sidebar').getBoundingClientRect().width") > 200)

        check("全程无 JS 报错", not errs, errs[:3])
        b.close()


if __name__ == "__main__":
    sys.exit(main())
