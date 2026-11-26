#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""操作日志的「查看相关对象」必须指到项目真实地址。

背景：日志页原来拼的是 `/<slug>/`，少了 `/v/` 前缀，点进去落到前端路由 404，
看着像「项目不存在」；项目改过 slug 之后，老日志更是彻底指错。

覆盖：
  1. 改属性产生的 patch 事件，slug 是当时的快照、live_slug 是当前值
  2. 改 slug 之后，改名前的日志 live_slug 也跟着变（前端据此跳新地址）
  3. 项目删掉之后，live_slug 变成 null（前端换成「项目已删除」，不再给死链）
  4. 用新 slug 做关键字搜索，能搜到 slug 还是旧值的那些老日志
  5. /v/<live_slug> 真的能打开（不是 404）

用法: python tests/check_events_link.py [--url http://127.0.0.1:8000]
"""
import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_test import FAIL, PASS, Client, check, multipart  # noqa: E402

FILES = [("files", "index.html", b"<!doctype html><meta charset=utf-8><h1>ev</h1>")]


def upload(c: Client, slug: str, title: str):
    body, ct = multipart({"slug": slug, "title": title, "hours": "2"}, FILES)
    return c.req("POST", "/api/projects", body, ct=ct)


def events(c: Client, **params):
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    code, d = c.req("GET", f"/api/events?page=1&page_size=50&{qs}")
    return code, d.get("items", []) if code == 200 else []


def find(items, action, slug_snapshot=None, title=None):
    for it in items:
        if it["action"] != action:
            continue
        if slug_snapshot is not None and it["slug"] != slug_snapshot:
            continue
        if title is not None and it["title"] != title:
            continue
        return it
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="admin123")
    args = ap.parse_args()

    sfx = "ev" + uuid.uuid4().hex[:6]
    old_slug, new_slug = f"{sfx}-before", f"{sfx}-after"
    c = Client(args.url)
    code, _ = c.login(args.user, args.password)
    if code != 200:
        print(f"登录失败，{code}")
        return 1

    print("[1] 传项目 → 改名称")
    code, d = upload(c, old_slug, "日志链接验证")
    check("项目建成", code == 200, str(code))
    code, _ = c.req("PATCH", f"/api/projects/{old_slug}", {"title": "日志链接验证 v2"})
    check("改名称成功", code == 200, str(code))
    _code, items = events(c, action="patch")
    e1 = find(items, "patch", slug_snapshot=old_slug)
    check("拿到改名称那条事件", e1 is not None, "")
    if e1:
        check("快照 slug 是当时的值", e1["slug"] == old_slug, str(e1["slug"]))
        check("live_slug 指向当前项目", e1["live_slug"] == old_slug, str(e1["live_slug"]))
        check("带着 project_id", bool(e1["project_id"]), str(e1["project_id"]))
        code, _loc = c.probe(f"/v/{e1['live_slug']}")
        check("/v/<live_slug> 能打开", code == 200, str(code))

    print("[2] 改 slug → 老事件的 live_slug 跟着新地址")
    code, _ = c.req("PATCH", f"/api/projects/{old_slug}", {"slug": new_slug})
    check("改 slug 成功", code == 200, str(code))
    _code, items = events(c, action="patch")
    e1 = find(items, "patch", slug_snapshot=old_slug)
    e2 = find(items, "patch", slug_snapshot=new_slug)
    check("改名那条也记了", e2 is not None, "")
    if e1:
        check("老事件快照不变", e1["slug"] == old_slug, str(e1["slug"]))
        check("老事件 live_slug 已跟到新 slug", e1["live_slug"] == new_slug, str(e1["live_slug"]))
    code, _loc = c.probe(f"/v/{new_slug}")
    check("/v/<新 slug> 能打开", code == 200, str(code))

    print("[3] 用新 slug 搜索，能搜到老日志")
    _code, items = events(c, q=new_slug)
    hit_old = any(it["slug"] == old_slug for it in items)
    check("新 slug 能搜出快照还是旧 slug 的事件", hit_old, f"{len(items)} 条")

    print("[4] 删项目 → 不再给出死链")
    code, _ = c.req("DELETE", f"/api/projects/{new_slug}")
    check("删除成功", code == 200, str(code))
    _code, items = events(c, action="patch")
    e1 = find(items, "patch", slug_snapshot=old_slug)
    check("老事件还在（日志是快照）", e1 is not None, "")
    if e1:
        check("live_slug 变成 null", e1["live_slug"] is None, str(e1["live_slug"]))
        check("project_id 仍保留", bool(e1["project_id"]), str(e1["project_id"]))

    print("[清理]")
    for s in (old_slug, new_slug):
        c.req("DELETE", f"/api/projects/{s}")

    print(f"\n{len(PASS)}/{len(PASS) + len(FAIL)} 通过")
    if FAIL:
        print("失败：")
        for f in FAIL:
            print("  -", f)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
