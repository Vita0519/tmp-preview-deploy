#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三档角色回归测试：viewer / publisher / admin 的权限边界与角色变更。

用法:
  python tests/check_roles.py [--url http://127.0.0.1:8000]

会创建形如 rv_xxxx / rp_xxxx 的临时账号，跑完自行清理。
"""
import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_test import Client, multipart  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✓' if cond else '✗'} {name}{('  → ' + str(extra)[:160]) if extra and not cond else ''}")


def upload(c, slug):
    body, ct = multipart(
        {"slug": slug, "title": slug, "visibility": "link"},
        [("files", "index.html", b"<!doctype html><h1>role</h1>")],
    )
    return c.req("POST", "/api/projects", body, ct=ct)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="admin123")
    args = ap.parse_args()

    tag = uuid.uuid4().hex[:6]
    admin = Client(args.url)
    code, _ = admin.login(args.user, args.password)
    check("管理员登录", code == 200)
    if code != 200:
        return 1

    made = []

    def make(role, label):
        name = f"r{role[0]}{tag}"
        code, d = admin.req(
            "POST", "/api/agents",
            {"username": name, "display_name": label, "password": "pw123456", "role": role},
        )
        check(f"创建 {role} 账号", code == 200, d)
        made.append(d.get("id"))
        c = Client(args.url)
        code, _ = c.login(name, "pw123456")
        check(f"{role} 能登录", code == 200)
        c.username = name
        c.api_key = d.get("api_key")
        return c, d

    print("[1] 创建三种角色")
    viewer, vd = make("viewer", "只读访客")
    pub, pd = make("publisher", "发布者")
    code, d = admin.req("GET", "/api/agents")
    roles = {a["username"]: a["role"] for a in d.get("items", [])}
    check("列表回显 viewer", roles.get(viewer.username) == "viewer", roles)
    check("列表回显 publisher", roles.get(pub.username) == "publisher", roles)

    print("[2] viewer 只能看门户")
    code, d = viewer.req("GET", "/api/projects")
    check("viewer 列表项目 403", code == 403, (code, d))
    code, d = upload(viewer, f"v-{tag}")
    check("viewer 上传 403", code == 403, (code, d))
    code, d = viewer.req("GET", "/api/agents")
    check("viewer 看成员 403", code == 403, (code, d))
    code, d = viewer.req("GET", "/api/settings")
    check("viewer 看设置 403", code == 403, (code, d))

    vk = Client(args.url)
    vk.token = vd.get("api_key")
    code, d = vk.req("GET", "/api/projects")
    check("viewer 的 Key 上传通道同样 403", code == 403, (code, d))

    print("[3] publisher 能发自己的项目，但管不了别人")
    code, d = upload(pub, f"p-{tag}")
    check("publisher 上传 200", code == 200, d)
    slug = d.get("slug")
    code, d = pub.req("GET", "/api/projects")
    check("publisher 列表只有自己的", code == 200 and d.get("total") == 1, d.get("total"))
    code, d = pub.req("GET", "/api/agents")
    check("publisher 看成员 403", code == 403, (code, d))
    code, d = pub.req("GET", "/api/settings")
    check("publisher 看设置 403", code == 403, (code, d))
    code, d = pub.req("PATCH", f"/api/projects/{slug}", {"title": "改一下"})
    check("publisher 能改自己的项目", code == 200, (code, d))

    print("[4] 管理员改角色，立即生效")
    pid = None
    code, d = admin.req("GET", "/api/agents")
    for a in d.get("items", []):
        if a["username"] == pub.username:
            pid = a["id"]
    code, d = admin.req("PATCH", f"/api/agents/{pid}", {"role": "viewer"})
    check("管理员把 publisher 降为 viewer", code == 200 and d.get("ok"), d)
    code, d = pub.req("GET", "/api/projects")
    check("旧会话立刻失去项目权限", code == 403, (code, d))
    code, d = admin.req("PATCH", f"/api/agents/{pid}", {"role": "publisher"})
    check("再升回 publisher", code == 200, d)
    code, d = pub.req("GET", "/api/projects")
    check("恢复后又能看项目", code == 200, (code, d))

    code, d = admin.req("PATCH", f"/api/agents/{pid}", {"role": "root"})
    check("非法角色 400", code == 400, (code, d))

    me_id = None
    code, d = admin.req("GET", "/api/agents")
    for a in d.get("items", []):
        if a["username"] == args.user:
            me_id = a["id"]
    code, d = admin.req("PATCH", f"/api/agents/{me_id}", {"role": "viewer"})
    check("不能改自己的角色 400", code == 400, (code, d))

    print("[5] 管理员权限")
    code, d = admin.req("GET", "/api/agents")
    check("管理员看成员 200", code == 200, "")
    code, d = admin.req("GET", "/api/settings")
    check("管理员看设置 200", code == 200, "")

    print("[6] 清理")
    for uid in [made[0], pid, made[1]]:
        if uid:
            admin.req("DELETE", f"/api/agents/{uid}")
    code, d = admin.req("GET", "/api/agents")
    left = [a["username"] for a in d.get("items", []) if a["username"].endswith(tag)]
    check("临时账号已清理", not left, left)

    total = len(PASS) + len(FAIL)
    print(f"\n{len(PASS)}/{total} 通过")
    if FAIL:
        print("失败：")
        for f in FAIL:
            print("  -", f)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
