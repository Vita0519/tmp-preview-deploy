#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端到端冒烟测试：不依赖第三方库，直接打本地服务。

用法:
  python tests/smoke_test.py --url http://127.0.0.1:8000
  python tests/smoke_test.py --url http://127.0.0.1:8000 --user admin --password xxx
"""
import argparse
import io
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from http.cookiejar import CookieJar

PASS, FAIL = [], []


def check(name: str, cond: bool, extra: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    mark = "✓" if cond else "✗"
    print(f"  {mark} {name}{('  → ' + extra) if extra and not cond else ''}")


class Client:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.jar = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(self.jar)
        )
        self.token = None

    def req(self, method, path, body=None, headers=None, raw=False, ct="application/json"):
        url = self.base + path
        data = None
        hdrs = {"User-Agent": "smoke-test"}
        if body is not None:
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            hdrs["Content-Type"] = ct
        if self.token:
            hdrs["Authorization"] = "Bearer " + self.token
        hdrs.update(headers or {})
        req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
        try:
            with self.opener.open(req, timeout=60) as r:
                payload = r.read()
                return r.status, (payload if raw else json.loads(payload or b"{}"))
        except urllib.error.HTTPError as e:
            payload = e.read()
            try:
                parsed = json.loads(payload or b"{}")
            except json.JSONDecodeError:
                parsed = {"raw": payload[:200].decode("utf-8", "replace")}
            return e.code, parsed

    def login(self, username: str, password: str):
        return self.req("POST", "/api/auth/login", {"username": username, "password": password})


def multipart(fields: dict, files: list[tuple[str, str, bytes]]):
    boundary = "----smoke" + uuid.uuid4().hex
    buf = io.BytesIO()
    for k, v in fields.items():
        buf.write(f"--{boundary}\r\n".encode())
        buf.write(f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode())
        buf.write(str(v).encode())
        buf.write(b"\r\n")
    for field, name, data in files:
        buf.write(f"--{boundary}\r\n".encode())
        buf.write(f'Content-Disposition: form-data; name="{field}"; filename="{name}"\r\n'.encode())
        buf.write(b"Content-Type: application/octet-stream\r\n\r\n")
        buf.write(data)
        buf.write(b"\r\n")
    buf.write(f"--{boundary}--\r\n".encode())
    return buf.getvalue(), f"multipart/form-data; boundary={boundary}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="admin123")
    args = ap.parse_args()

    admin = Client(args.url)
    print(f"\n▶ 目标 {args.url}")

    print("\n[基础]")
    code, d = admin.req("GET", "/api/health")
    check("健康检查", code == 200 and d.get("ok"), str(d))

    code, d = admin.login(args.user, args.password)
    check("管理员登录", code == 200 and d.get("user", {}).get("role") == "admin", str(d))

    code, _ = Client(args.url).req("GET", "/api/projects")
    check("未登录访问被拒", code == 401, str(code))

    print("\n[成员]")
    suffix = uuid.uuid4().hex[:6]
    agent_name = f"bot{suffix}"
    code, d = admin.req("POST", "/api/agents", {"username": agent_name, "display_name": "测试 Bot"})
    check("创建成员", code == 200 and d.get("api_key"), str(d))
    api_key = d.get("api_key", "")

    agent = Client(args.url)
    agent.token = api_key
    code, d = agent.req("GET", "/api/agents")
    check("成员无管理权限", code == 403, str(code))

    print("\n[上传]")
    html = b"<!doctype html><title>smoke</title><h1>ok</h1>"
    css = b"body{color:#111}"
    files = [("files", "index.html", html), ("files", "assets/app.css", css)]
    body, ctype = multipart(
        {"slug": f"smoke-{suffix}", "title": "冒烟项目", "tags": "smoke,auto", "hours": "1",
         "allow_download": "1"},
        files,
    )
    code, d = agent.req("POST", "/api/projects", body, {"Content-Type": ctype}, ct=ctype)
    check("成员上传项目", code == 200 and d.get("slug") == f"smoke-{suffix}", str(d)[:200])
    slug = d.get("slug", "")

    code, _ = agent.req("GET", f"/p/{slug}/", raw=True)
    check("子资源可访问", code == 200, str(code))
    code, _ = agent.req("GET", f"/p/{slug}/assets/app.css", raw=True)
    check("嵌套资源可访问", code == 200, str(code))

    print("\n[权限隔离]")
    code, d = agent.req("GET", "/api/projects")
    own = [x["slug"] for x in d.get("items", [])]
    check("成员只看到自己的项目", code == 200 and own == [slug], str(own))

    code, _ = agent.req("PATCH", "/api/projects/hello-demo", {"title": "hack"})
    check("成员不能改他人项目", code in (403, 404), str(code))

    code, d = admin.req("GET", "/api/projects")
    slugs = [x["slug"] for x in d.get("items", [])]
    check("管理员看到全部项目", slug in slugs, str(slugs))
    check("管理员可见 agent 分面", any(a["username"] == agent_name for a in d["facets"]["agents"]), "")
    check("统计字段齐全", {"total", "online", "views", "views_today"} <= set(d["stats"].keys()), str(d["stats"]))

    print("\n[筛选与排序]")
    code, d = admin.req("GET", f"/api/projects?q=smoke&sort=views&order=desc")
    check("关键词筛选", code == 200 and all("smoke" in x["slug"] or "smoke" in x["title"] for x in d["items"]), "")
    code, d = admin.req("GET", f"/api/projects?agent={agent_name}")
    check("按 agent 筛选", code == 200 and d["total"] == 1, str(d.get("total")))
    code, d = admin.req("GET", "/api/projects?tag=auto")
    check("按标签筛选", code == 200 and any(x["slug"] == slug for x in d["items"]), "")
    code, d = admin.req("GET", "/api/projects?sort=created_at&order=asc&limit=2")
    check("排序+分页", code == 200 and len(d["items"]) <= 2, str(len(d.get("items", []))))
    code, d = admin.req("GET", "/api/projects?status=expired")
    check("按状态筛选", code == 200, str(code))

    print("\n[改属性]")
    code, d = admin.req("PATCH", f"/api/projects/{slug}",
                        {"title": "改名了", "tags": ["smoke", "edited"], "permanent": True,
                         "visibility": "portal"})
    check("改标题/标签/永久", code == 200 and d.get("permanent") and "edited" in d.get("tags", []), str(d)[:220])
    code, d = admin.req("PATCH", f"/api/projects/{slug}", {"hours": 48})
    check("延长存活", code == 200 and not d.get("permanent"), str(d)[:160])

    print("\n[访问计数]")
    for _ in range(3):
        admin.req("GET", f"/p/{slug}/", raw=True, headers={"Accept": "text/html"})
    import time as _t
    _t.sleep(4)
    code, d = admin.req("GET", f"/api/projects?q={slug}")
    views = d["items"][0]["views"] if d.get("items") else 0
    check("访问计数已落库", views >= 3, f"views={views}")

    code, d = admin.req("GET", f"/download/{slug}", raw=True)
    check("zip 下载", code == 200 and d[:2] == b"PK", str(code))

    print("\n[批量]")
    code, d = admin.req("POST", "/api/projects/bulk", {"slugs": [slug], "action": "extend", "hours": 2})
    check("批量延长", code == 200 and d.get("done") == 1, str(d))

    print("\n[清理]")
    code, d = admin.req("DELETE", f"/api/projects/{slug}")
    check("删除项目", code == 200, str(d))
    code, _ = admin.req("GET", f"/v/{slug}", raw=True)
    check("删除后 404", code == 404, str(code))
    aid = _agent_id(admin, agent_name)
    if aid:
        code, d = admin.req("DELETE", f"/api/agents/{aid}")
        check("删除成员并清理其项目", code == 200, str(d))

    print(f"\n{'=' * 46}\n通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    if FAIL:
        print("失败用例：" + "、".join(FAIL))
        return 1
    print("全部通过 ✅")
    return 0


def _agent_id(admin: Client, username: str) -> int:
    code, d = admin.req("GET", "/api/agents")
    for a in d.get("items", []):
        if a["username"] == username:
            return a["id"]
    return 0


if __name__ == "__main__":
    sys.exit(main())
