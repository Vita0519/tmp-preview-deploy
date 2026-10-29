#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验「按可见性区分的默认时长」与「到期策略默认值」。

用法: python tests/check_ttl.py [--url http://127.0.0.1:8010]
"""
import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_test import Client, multipart  # noqa: E402

PASS, FAIL = [], []


def post_project(c, fields, files):
    body, ct = multipart(fields, files)
    return c.req("POST", "/api/projects", body, ct=ct)


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✓' if cond else '✗'} {name}{('  → ' + extra) if extra and not cond else ''}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8010")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="admin123")
    args = ap.parse_args()

    c = Client(args.url)
    code, _ = c.login(args.user, args.password)
    check("登录", code == 200)

    code, meta = c.req("GET", "/api/meta")
    check("meta 暴露 ttl_defaults", code == 200 and "ttl_defaults" in meta, str(meta)[:120])
    print("    meta.ttl_defaults =", meta.get("ttl_defaults"))

    code, s = c.req("GET", "/api/settings")
    base = s.get("ttl_defaults", {})
    print("    settings.ttl_defaults =", base, "expire =", s.get("default_expire_action"))

    tag = uuid.uuid4().hex[:6]
    created = {}
    for vis in ("portal", "link", "private"):
        slug = f"ttl-{vis}-{tag}"
        code, d = post_project(
            c,
            {"slug": slug, "title": f"TTL {vis}", "visibility": vis},
            [("files", "index.html", b"<!doctype html><h1>ttl</h1>")],
        )
        check(f"上传 {vis}", code == 200, str(d)[:160])
        created[vis] = d
        hours = (d.get("expires_at") or 0) - (d.get("created_at") or 0)
        hours = round(hours / 3600_000, 2)
        expect = base.get(vis, 0)
        if expect:
            check(f"{vis} 默认 ≈ {expect}h", abs(hours - expect) < 0.05, f"实际 {hours}h")
        else:
            check(f"{vis} 默认永久", d.get("permanent") is True, f"expires_at={d.get('expires_at')}")
        check(f"{vis} 到期动作默认 block", d.get("expire_action") == "block", str(d.get("expire_action")))

    # 改设置为 2 / 3 / 0，再建一个看是否生效
    code, _ = c.req("PATCH", "/api/settings", {"ttl_defaults": {"portal": 2, "link": 3, "private": 0}})
    check("保存 ttl_defaults", code == 200, str(_)[:120])
    code, s2 = c.req("GET", "/api/settings")
    check("回读 ttl_defaults", s2.get("ttl_defaults") == {"portal": 2.0, "link": 3.0, "private": 0.0}, str(s2.get("ttl_defaults")))

    slug = f"ttl-portal2-{tag}"
    code, d = post_project(
        c,
        {"slug": slug, "title": "TTL portal 2h", "visibility": "portal"},
        [("files", "index.html", b"<h1>x</h1>")],
    )
    hrs = round(((d.get("expires_at") or 0) - (d.get("created_at") or 0)) / 3600_000, 2)
    check("新默认 2h 生效", abs(hrs - 2) < 0.05, f"实际 {hrs}h")

    # 显式 hours 仍然优先
    slug = f"ttl-explicit-{tag}"
    code, d = post_project(
        c,
        {"slug": slug, "title": "explicit", "visibility": "portal", "hours": "30"},
        [("files", "index.html", b"<h1>y</h1>")],
    )
    hrs = round(((d.get("expires_at") or 0) - (d.get("created_at") or 0)) / 3600_000, 2)
    check("显式 hours 覆盖默认", abs(hrs - 30) < 0.05, f"实际 {hrs}h")

    # 到期策略：设为 delete 后新建的项目继承
    c.req("PATCH", "/api/settings", {"default_expire_action": "delete"})
    slug = f"ttl-act-{tag}"
    code, d = post_project(
        c,
        {"slug": slug, "title": "act", "visibility": "link"},
        [("files", "index.html", b"<h1>z</h1>")],
    )
    check("继承 delete 策略", d.get("expire_action") == "delete", str(d.get("expire_action")))

    # 复位
    c.req("PATCH", "/api/settings", {"ttl_defaults": base, "default_expire_action": "block"})
    for vis, d in created.items():
        c.req("DELETE", f"/api/projects/{d['slug']}")
    for s in (f"ttl-portal2-{tag}", f"ttl-explicit-{tag}", f"ttl-act-{tag}"):
        c.req("DELETE", f"/api/projects/{s}")

    print(f"\n通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
