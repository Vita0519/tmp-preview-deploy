#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同一成员名下的项目名不允许重复：新建 / 外链 / 改名三条路径都要拦住。

用法: python tests/check_title.py [--url http://127.0.0.1:8000]
"""
import argparse
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_test import FAIL, PASS, Client, check, multipart  # noqa: E402

FILES = [("files", "index.html", b"<!doctype html><meta charset=utf-8><h1>t</h1>")]


def upload(c: Client, slug: str, title: str):
    body, ct = multipart({"slug": slug, "title": title, "hours": "2"}, FILES)
    return c.req("POST", "/api/projects", body, ct=ct)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="admin123")
    args = ap.parse_args()
    url = args.url
    suffix = str(int(time.time()))[-4:]

    admin = Client(url)
    code, d = admin.login(args.user, args.password)
    check("管理员登录", code == 200, str(code))

    # 两个临时成员：验证「重名只在自己名下算冲突」
    mate_a = f"tna{suffix}"
    mate_b = f"tnb{suffix}"
    ids = {}
    for name in (mate_a, mate_b):
        code, d = admin.req("POST", "/api/agents", {"username": name, "display_name": name, "role": "publisher"})
        check(f"创建成员 {name}", code == 200, str(d)[:120])
        ids[name] = d.get("id")
        code, k = admin.req("GET", f"/api/agents/{d['id']}/key")
        ids[name + "_key"] = k.get("api_key")

    a = Client(url)
    a.token = ids[mate_a + "_key"]
    b = Client(url)
    b.token = ids[mate_b + "_key"]

    title = f"同名测试 {suffix}"
    slug1 = f"tna-{suffix}-1"
    slug2 = f"tna-{suffix}-2"

    print("[1] 新建时的重名")
    code, d = upload(a, slug1, title)
    check("第一个同名项目建成", code == 200, str(code))
    code, d = upload(a, slug2, title)
    check("同一个人再建同名 → 409", code == 409, str(code))
    check("409 里点名了冲突的项目", slug1 in str(d) or "已" in str(d), str(d)[:140])

    print("[2] 大小写与空格不算新名字")
    code, d = upload(a, f"tna-{suffix}-3", f"  {title.upper()}  ")
    check("大写 + 前后空格也判重", code == 409, str(code))

    print("[3] 覆盖更新自己那个 slug 不算冲突")
    code, d = upload(a, slug1, title)
    check("同 slug 同标题覆盖更新 → 200", code == 200, str(code))
    check("更新后仍是同一个项目", d.get("slug") == slug1, str(d.get("slug")))

    print("[4] 改名撞上已有名字")
    code, d = upload(a, f"tna-{suffix}-4", f"另一个名字 {suffix}")
    check("先建一个不同名的项目", code == 200, str(code))
    code, d = a.req("PATCH", f"/api/projects/tna-{suffix}-4", {"title": title})
    check("改名撞车 → 409", code == 409, str(code))
    code, d = a.req("PATCH", f"/api/projects/tna-{suffix}-4", {"title": f"  另一个名字 {suffix}  "})
    check("改成自己原来的名字（只改空格）不算冲突", code == 200, str(code))
    code, d = a.req("PATCH", f"/api/projects/tna-{suffix}-4", {"title": f"独一无二 {suffix}"})
    check("改成没被占用的名字 → 200", code == 200, str(code))

    print("[5] 外链项目也受约束")
    code, d = a.req("POST", "/api/projects/link", {"link_url": "https://example.com/a", "title": title, "hours": 2})
    check("外链用已占用的名字 → 409", code == 409, str(code))
    code, d = a.req("POST", "/api/projects/link", {"link_url": "https://example.com/b", "title": f"外链 {suffix}", "hours": 2})
    check("外链用新名字 → 200", code == 200, str(code))

    print("[6] 别人用这个名字不受影响")
    code, d = upload(b, f"tnb-{suffix}-1", title)
    check("另一个成员建同名项目 → 200", code == 200, str(code))
    code, d = upload(b, f"tnb-{suffix}-2", title)
    check("他自己再建同名 → 409", code == 409, str(code))

    print("[7] 管理员替成员建项目时，按成员的命名空间判重")
    body, ct = multipart(
        {"slug": f"adm-{suffix}-1", "title": f"代建 {suffix}", "hours": "2", "owner": mate_a}, FILES
    )
    code, d = admin.req("POST", "/api/projects", body, ct=ct)
    check("管理员替成员建项目 → 200", code == 200, str(code))
    body, ct = multipart(
        {"slug": f"adm-{suffix}-2", "title": f"代建 {suffix}", "hours": "2", "owner": mate_a}, FILES
    )
    code, d = admin.req("POST", "/api/projects", body, ct=ct)
    check("替同一个成员建重名项目 → 409", code == 409, str(code))

    print("[8] 空标题不受影响（回落成 slug）")
    code, d = upload(a, f"tna-{suffix}-5", "")
    check("不给标题也能建（标题取 slug）", code == 200, str(code))
    check("标题就是 slug", d.get("title") == f"tna-{suffix}-5", str(d.get("title")))

    print("[清理]")
    code, d = admin.req("GET", "/api/projects?limit=200")
    for item in d.get("items", []):
        if item["slug"].startswith(("tna-", "tnb-", "adm-")) and suffix in item["slug"]:
            admin.req("DELETE", f"/api/projects/{item['slug']}")
    for name in (mate_a, mate_b):
        admin.req("DELETE", f"/api/agents/{ids[name]}")
    code, d = admin.req("GET", "/api/agents")
    check("临时成员已清理", not any(x["username"] in (mate_a, mate_b) for x in d.get("items", [])))

    print(f"\n{len(PASS)}/{len(PASS) + len(FAIL)} 通过")
    if FAIL:
        print("失败：")
        for f in FAIL:
            print("  -", f)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
