#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多 agent 同时操作：并发部署 / 同 slug 抢占 / 混合读写，看是否出错或写坏。

用法: python tests/check_concurrency.py [--url http://127.0.0.1:8000] [--agents 6] [--each 3]
"""
import argparse
import io
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_test import Client, FAIL, PASS, check, multipart  # noqa: E402

FILES = [
    ("files", "index.html", b'<!doctype html><meta charset=utf-8><h1>c</h1>'),
    ("files", "assets/app.js", b"console.log(1)"),
    ("files", "assets/app.css", b"body{margin:0}"),
]


def deploy(url, token, slug, visibility="link", files=None):
    body, ct = multipart(
        {"slug": slug, "title": slug, "visibility": visibility, "hours": "2", "tags": "conc"},
        files or FILES,
    )
    c = Client(url)
    c.token = token
    t0 = time.time()
    code, d = c.req("POST", "/api/projects", body, ct=ct)
    return code, d, time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="admin123")
    ap.add_argument("--agents", type=int, default=6)
    ap.add_argument("--each", type=int, default=3)
    args = ap.parse_args()
    url = args.url.rstrip("/")

    admin = Client(url)
    code, _ = admin.login(args.user, args.password)
    check("管理员登录", code == 200, str(code))
    if code != 200:
        return 1

    suffix = str(int(time.time()))[-6:]
    agents = []
    print(f"[准备] {args.agents} 个 agent × 每人 {args.each} 个并发上传")
    for i in range(args.agents):
        name = f"conc{suffix}{i}"
        code, d = admin.req("POST", "/api/agents",
                            {"username": name, "password": "conc123456", "role": "publisher"})
        if code != 200:
            check(f"创建 agent {i}", False, d)
            return 1
        agents.append({"username": name, "id": d["id"], "token": d["api_key"]})
    check(f"创建 {args.agents} 个 agent 全部成功", len(agents) == args.agents)

    # ---------- 1. 纯并发部署：每人若干，同一瞬间打进来 ----------
    print("[1] 并发部署（互不相同的 slug）")
    jobs = []
    expect_slugs = {}
    for a in agents:
        expect_slugs[a["username"]] = []
        for k in range(args.each):
            slug = f"c{suffix}-{a['username'][-3:]}-{k}"
            expect_slugs[a["username"]].append(slug)
            jobs.append((a, slug))

    results, lat = [], []
    with ThreadPoolExecutor(max_workers=len(jobs)) as ex:
        fut = {ex.submit(deploy, url, a["token"], slug): (a, slug) for a, slug in jobs}
        for f in as_completed(fut):
            a, slug = fut[f]
            try:
                code, d, dt = f.result()
            except Exception as exc:  # noqa: BLE001
                code, d, dt = 0, {"detail": str(exc)}, 0
            results.append((a["username"], slug, code, d))
            lat.append(dt)

    bad = [(u, s, c) for u, s, c, _ in results if c != 200]
    check(f"{len(results)} 个并发部署全部 200", not bad, bad[:4])
    lat.sort()
    if lat:
        print(f"    延迟 中位 {lat[len(lat)//2]:.2f}s / 最慢 {lat[-1]:.2f}s")
    check("没有服务端 5xx", not any(c >= 500 for _, _, c, _ in results),
          [c for _, _, c, _ in results if c >= 500][:5])

    # 每人只看得到自己的
    print("[2] 归属隔离与完整性")
    for a in agents[:3]:
        c = Client(url)
        c.token = a["token"]
        code, d = c.req("GET", "/api/projects?status=all&limit=200&q=" + f"c{suffix}")
        got = {p["slug"] for p in (d.get("items") or [])}
        mine = set(expect_slugs[a["username"]])
        check(f"{a['username']} 能看到自己全部 {len(mine)} 个", mine <= got, sorted(mine - got))
        others = set().union(*[set(v) for k, v in expect_slugs.items() if k != a["username"]])
        check(f"{a['username']} 看不到别人的", not (got & others), sorted(got & others)[:3])

    # 抽查一个项目文件数是否正确（并发写没有串）
    one = agents[0]
    slug0 = expect_slugs[one["username"]][0]
    c = Client(url)
    c.token = one["token"]
    code, d = c.req("GET", f"/api/projects/{slug0}")
    check("并发部署后文件数正确（3 个）", d.get("file_count") == 3, d.get("file_count"))
    code, html = Client(url).req("GET", f"/v/{slug0}", raw=True)
    check("并发部署的项目能正常打开", code == 200, str(code))

    # ---------- 3. 同一个 slug 被同时覆盖写 ----------
    print("[3] 同一 slug 被 6 路同时覆盖写")
    dup = f"cdup-{suffix}"
    with ThreadPoolExecutor(max_workers=6) as ex:
        fut = [ex.submit(deploy, url, one["token"], dup) for _ in range(6)]
        r = [f.result() for f in as_completed(fut)]
    check("同 slug 并发覆盖不报错", all(c == 200 for c, _, _ in r), [c for c, _, _ in r])
    c = Client(url)
    c.token = one["token"]
    code, d = c.req("GET", f"/api/projects/{dup}")
    check("覆盖后文件数仍是 3（没有写串）", d.get("file_count") == 3, d.get("file_count"))
    check("覆盖后项目仍可访问", Client(url).req("GET", f"/v/{dup}", raw=True)[0] == 200)

    # ---------- 4. 边写边读：部署 / 改 / 删 / 读混在一起 ----------
    print("[4] 混合读写（部署 + 改可见性 + 列表 + 门户 + 删除）")
    mixed_errors = []

    def op(kind, a, slug):
        c = Client(url)
        c.token = a["token"]
        if kind == "deploy":
            return deploy(url, a["token"], slug)[0]
        if kind == "set":
            return c.req("PATCH", f"/api/projects/{slug}", {"visibility": "portal"})[0]
        if kind == "list":
            return c.req("GET", "/api/projects?limit=50")[0]
        if kind == "portal":
            return c.req("GET", "/portal", raw=True)[0]
        if kind == "rm":
            return c.req("DELETE", f"/api/projects/{slug}")[0]
        return -1

    with ThreadPoolExecutor(max_workers=12) as ex:
        fut = []
        for i, a in enumerate(agents):
            fut.append(ex.submit(op, "deploy", a, f"cmix-{suffix}-{i}"))
            fut.append(ex.submit(op, "list", a, ""))
            fut.append(ex.submit(op, "portal", a, ""))
        for f in as_completed(fut):
            try:
                code = f.result()
            except Exception as exc:  # noqa: BLE001
                code = 0
                mixed_errors.append(str(exc))
            if code not in (200, 302):
                mixed_errors.append(code)
    check("混合读写没有异常返回", not mixed_errors, mixed_errors[:5])

    # 改/删同时发生（不同项目，不能互相影响）
    print("[5] 同时改可见性 + 同时删除（不同项目）")
    targets = [f"cmix-{suffix}-{i}" for i in range(min(4, len(agents)))]
    with ThreadPoolExecutor(max_workers=8) as ex:
        fut = []
        for i, slug in enumerate(targets):
            fut.append(ex.submit(op, "set", agents[i % len(agents)], slug))
        for i, slug in enumerate(targets[:2]):
            fut.append(ex.submit(op, "rm", agents[i % len(agents)], slug))
        codes = []
        for f in as_completed(fut):
            try:
                codes.append(f.result())
            except Exception as exc:  # noqa: BLE001
                codes.append(str(exc))
    check("改可见性与删除并发执行无 5xx", not any(isinstance(c, int) and c >= 500 for c in codes),
          [c for c in codes if isinstance(c, int) and c >= 500])

    # ---------- 6. 服务仍然健康 ----------
    print("[6] 压完之后的健康检查")
    code, _ = Client(url).req("GET", "/api/health")
    check("健康检查 200", code == 200, str(code))
    c = Client(url)
    c.token = admin.req("GET", f"/api/agents/{agents[0]['id']}/key")[1]["api_key"]
    code, d = c.req("GET", "/api/projects?limit=5")
    check("压测后仍能正常读写", code == 200, str(code))

    print("[清理]")
    with ThreadPoolExecutor(max_workers=8) as ex:
        fut = []
        for a in agents:
            for slug in expect_slugs[a["username"]]:
                fut.append(ex.submit(op, "rm", a, slug))
        for f in as_completed(fut):
            try:
                f.result()
            except Exception:  # noqa: BLE001
                pass
    admin.req("DELETE", f"/api/projects/{dup}")
    for a in agents:
        admin.req("DELETE", f"/api/agents/{a['id']}")
    code, d = admin.req("GET", "/api/agents")
    check("临时 agent 已清理",
          not any(x["username"].startswith(f"conc{suffix}") for x in d.get("items", [])))

    print(f"\n{len(PASS)}/{len(PASS) + len(FAIL)} 通过")
    if FAIL:
        print("失败：")
        for f in FAIL:
            print("  -", f)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
