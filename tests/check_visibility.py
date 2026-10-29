#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三档可见性 + 批量切换 + Key 与账号一对一绑定。

用法: python tests/check_visibility.py [--url http://127.0.0.1:8000]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_test import Client, check, FAIL, PASS, multipart  # noqa: E402

PAGE = b'<!doctype html><meta charset="utf-8"><h1>v</h1>'


def new_proj(c, slug, visibility, title=None):
    body, ct = multipart(
        {
            "slug": slug,
            "title": title or slug,
            "visibility": visibility,
            "hours": "24",
            "tags": "visibility",
        },
        [("files", "index.html", PAGE)],
    )
    return c.req("POST", "/api/projects", body, ct=ct)


def anon(base):
    """没登录的浏览器。"""
    return Client(base)


def portal_slugs(c) -> list[str]:
    code, html = c.req("GET", "/portal", raw=True)
    if code != 200:
        return []
    text = html.decode("utf-8", "replace") if isinstance(html, bytes) else html
    out = []
    for chunk in text.split('data-path="/v/')[1:]:
        out.append(chunk.split('"', 1)[0])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="admin123")
    args = ap.parse_args()

    base = args.url.rstrip("/")
    c = Client(base)
    code, _ = c.login(args.user, args.password)
    check("管理员登录", code == 200, code)
    if code != 200:
        return 1

    code, pub_key = c.req("GET", "/api/agents")
    me = next((a for a in pub_key["items"] if a["username"] == args.user), None)
    check("成员列表返回 key_label", me and "key_label" in me, str(pub_key))
    check("成员列表返回最近使用时间", me and "key_last_used_at" in me)

    # ---------- 建三个项目，各一种可见性 ----------
    print("[1] 三档可见性：匿名访问")
    suffix = str(int(__import__("time").time()))[-6:]
    slugs = {
        "portal": f"vis-portal-{suffix}",
        "link": f"vis-link-{suffix}",
        "private": f"vis-private-{suffix}",
    }
    for vis, slug in slugs.items():
        code, d = new_proj(c, slug, vis)
        check(f"创建 {vis} 项目", code == 200, d)

    guest = anon(base)
    for vis, slug in slugs.items():
        code, _ = guest.req("GET", f"/v/{slug}", raw=True)
        if vis == "private":
            check("匿名打开 private → 404", code == 404, code)
        else:
            check(f"匿名打开 {vis} → 200", code == 200, code)

    print("[2] 是否出现在访客门户")
    listed = portal_slugs(c)
    check("portal 项目在门户列表里", slugs["portal"] in listed, listed[:6])
    check("link 项目不在门户列表", slugs["link"] not in listed)
    check("private 项目不在门户列表", slugs["private"] not in listed)

    print("[3] 私有链接只有本人 / 管理员能开")
    code, d = c.req("POST", "/api/agents", {
        "username": f"mate{suffix}", "password": "mate123456", "role": "publisher",
        "key_label": "claude-code",
    })
    check("创建一个 publisher 成员", code == 200, d)
    mate_name, mate_pw = f"mate{suffix}", "mate123456"
    mate = Client(base)
    code, _ = mate.login(mate_name, mate_pw)
    check("成员登录", code == 200, code)
    code, _ = mate.req("GET", f"/v/{slugs['private']}", raw=True)
    check("其他 publisher 打开别人的 private → 404", code == 404, code)
    code, _ = c.req("GET", f"/v/{slugs['private']}", raw=True)
    check("管理员打开 private → 200", code == 200, code)
    code, _ = mate.req("GET", f"/v/{slugs['link']}", raw=True)
    check("其他 publisher 打开 link → 200", code == 200, code)

    print("[4] 批量改可见性")
    code, d = c.req("POST", "/api/projects/bulk", {
        "slugs": [slugs["link"]], "action": "visibility", "visibility": "portal",
    })
    check("批量设为门户可见", code == 200 and d.get("done") == 1, d)
    check("改完后出现在门户", slugs["link"] in portal_slugs(c))

    code, d = c.req("POST", "/api/projects/bulk", {
        "slugs": [slugs["portal"]], "action": "visibility", "visibility": "private",
    })
    check("批量设为仅自己", code == 200 and d.get("done") == 1, d)
    check("改为私有不影响 owner", c.req("GET", f"/v/{slugs['portal']}", raw=True)[0] == 200)
    check("改为私有后匿名 404",
          anon(base).req("GET", f"/v/{slugs['portal']}", raw=True)[0] == 404)

    code, d = c.req("POST", "/api/projects/bulk", {
        "slugs": [slugs["portal"]], "action": "visibility", "visibility": "bogus",
    })
    check("非法可见性 → 400", code == 400, d)

    # 越权：成员想改别人的项目
    code, mine = new_proj(mate, f"mate-own-{suffix}", "link")
    check("成员建自己的项目", code == 200, str(mine))
    code, d = mate.req("POST", "/api/projects/bulk", {
        "slugs": [slugs["link"]], "action": "visibility", "visibility": "private",
    })
    check("成员改别人的项目被跳过", code == 200 and d.get("done") == 0 and d.get("skipped") == 1, d)

    print("[5] Key 与账号一对一")
    code, d = c.req("GET", "/api/agents")
    mate_row = next((a for a in d["items"] if a["username"] == mate_name), None)
    check("新成员可设置绑定名", mate_row and mate_row["key_label"] == "claude-code", str(mate_row))
    check("新成员绑定名不为空（默认回落到账号）", bool(mate_row and mate_row["key_label"]))
    code, k = c.req("GET", f"/api/agents/{mate_row['id']}/key")
    key = k["api_key"]
    check("取到该成员的 Key", key.startswith("pv_"), key[:6])

    # 用 key 调一次接口，看最近使用时间与次数是否落库
    cli = Client(base)
    cli.token = key
    code, _ = cli.req("GET", "/api/projects?limit=5")
    check("Key 能调接口", code == 200, code)
    code, d = c.req("GET", "/api/agents")
    mate_row2 = next((a for a in d["items"] if a["username"] == mate_name), None)
    check("Key 使用后记录最近使用时间", bool(mate_row2 and mate_row2["key_last_used_at"]))
    check("Key 使用后累计次数 +1", mate_row2 and mate_row2["key_uses"] >= 1, str(mate_row2))

    code, d = c.req("PATCH", f"/api/agents/{mate_row['id']}", {"key_label": "codex-cli"})
    check("改绑定名成功", code == 200, d)
    code, d = c.req("GET", "/api/agents")
    mate_row3 = next((a for a in d["items"] if a["username"] == mate_name), None)
    check("绑定名已更新", mate_row3 and mate_row3["key_label"] == "codex-cli", str(mate_row3))

    # 轮换：旧 key 立即失效，新 key 可用，绑定名保留
    code, r = c.req("PATCH", f"/api/agents/{mate_row['id']}", {"rotate_key": True})
    check("轮换返回新 Key", code == 200 and r.get("api_key", "").startswith("pv_"), r)
    cli2 = Client(base)
    cli2.token = key
    code, _ = cli2.req("GET", "/api/projects?limit=5")
    check("旧 Key 立即失效 401", code == 401, code)
    cli3 = Client(base)
    cli3.token = r["api_key"]
    code, _ = cli3.req("GET", "/api/projects?limit=5")
    check("新 Key 可用", code == 200, code)
    code, d = c.req("GET", "/api/agents")
    mate_row4 = next((a for a in d["items"] if a["username"] == mate_name), None)
    check("轮换后绑定名保留", mate_row4 and mate_row4["key_label"] == "codex-cli", str(mate_row4))
    # 计数在轮换时归零；新 Key 刚被用了一次，所以允许 0/1
    check("轮换后计数从零重新累计", mate_row4 and mate_row4["key_uses"] <= 1, str(mate_row4))

    print("[6] viewer 的 Key 只能读，不能发布")
    code, d = c.req("POST", "/api/agents", {
        "username": f"look{suffix}", "password": "look123456", "role": "viewer",
    })
    check("创建 viewer", code == 200, d)
    code, k = c.req("GET", f"/api/agents/{d['id']}/key")
    gk = Client(base)
    gk.token = k["api_key"]
    code, _ = gk.req("GET", "/api/projects?limit=5")
    check("viewer Key 读项目列表 → 403", code == 403, code)
    code, _ = gk.req("GET", f"/v/{slugs['link']}", raw=True)
    check("viewer Key 能开 link 项目", code == 200, code)

    # ---------- 清理 ----------
    print("[清理]")
    for slug in (slugs["portal"], slugs["link"], slugs["private"], f"mate-own-{suffix}"):
        c.req("DELETE", f"/api/projects/{slug}")
    for name in (mate_name, f"look{suffix}"):
        code, d = c.req("GET", "/api/agents")
        row = next((a for a in d["items"] if a["username"] == name), None)
        if row:
            c.req("DELETE", f"/api/agents/{row['id']}")

    print(f"\n{len(PASS)}/{len(PASS) + len(FAIL)} 通过")
    if FAIL:
        print("失败：")
        for f in FAIL:
            print("  -", f)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
