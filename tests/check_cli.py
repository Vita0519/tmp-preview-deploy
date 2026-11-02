#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通过真实 CLI 子进程跑一遍增删改查：证明其它 agent 拿到 Key 就能干活。

用法: python tests/check_cli.py [--url http://127.0.0.1:8000]
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_test import Client, check, FAIL, PASS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "cli" / "agentctl.py"
PY = sys.executable


def run(url, token, *argv, expect=0):
    """跑一次 CLI，返回 (exit_code, parsed_json, raw_stdout)。"""
    cmd = [PY, str(CLI), "--url", url, "--token", token, "--json", *argv]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=180)
    out = (p.stdout or "").strip()
    try:
        data = json.loads(out.splitlines()[-1]) if out else {}
    except (json.JSONDecodeError, IndexError):
        data = {}
    if expect is not None:
        check(f"CLI {' '.join(argv[:2])} 退出码 {expect}",
              p.returncode == expect, f"rc={p.returncode} err={p.stderr[:200]}")
    return p.returncode, data, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="admin123")
    args = ap.parse_args()
    url = args.url.rstrip("/")

    admin = Client(url)
    code, _ = admin.login(args.user, args.password)
    check("管理员登录", code == 200, str(code))
    if code != 200:
        return 1

    suffix = str(int(time.time()))[-6:]
    uname, upass = f"cli{suffix}", "cli123456"

    print("[0] 造一个 publisher 成员，只用它的 Key")
    code, d = admin.req("POST", "/api/agents", {
        "username": uname, "password": upass, "role": "publisher", "key_label": "cli-agent",
    })
    check("创建成员", code == 200, d)
    if code != 200:
        return 1
    uid, token = d["id"], d["api_key"]

    print("[1] 身份与健康")
    rc, d, _ = run(url, token, "whoami")
    check("whoami 角色正确", d.get("data", {}).get("role") == "publisher", d)
    check("whoami 能发布", d.get("data", {}).get("can_publish") is True)
    check("whoami 不能管理", d.get("data", {}).get("can_admin") is False)
    check("whoami 不泄露完整 Key", len(d.get("data", {}).get("key_tail", "")) == 6)

    rc, d, _ = run(url, token, "health")
    check("health 认证通过", d.get("data", {}).get("auth") == "ok", d)
    check("health 拿到版本号", bool(d.get("data", {}).get("version")))

    print("[2] 部署：自动返回并校验地址 + 项目自带图标")
    tmp = Path(tempfile.mkdtemp(prefix="clicase-"))
    (tmp / "index.html").write_text(
        "<!doctype html><meta charset=utf-8><title>cli</title><h1>hi</h1>", "utf-8")
    (tmp / "favicon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8"><rect width="8" height="8" fill="#f00"/></svg>',
        "utf-8")
    (tmp / "assets").mkdir()
    (tmp / "assets" / "a.css").write_text("body{margin:0}", "utf-8")

    slug = f"cli-case-{suffix}"
    rc, d, _ = run(url, token, "deploy", str(tmp), "--slug", slug, "--title", "CLI 验收",
                   "--tags", "cli,test", "--ttl", "2")
    data = d.get("data", {})
    check("deploy 返回 slug", data.get("slug") == slug, data)
    check("deploy 自动给出预览地址", str(data.get("url", "")).endswith(f"/v/{slug}"), data.get("url"))
    check("deploy 自动探活通过", data.get("verified") is True, data.get("http_status"))
    check("deploy 报告文件数", data.get("files") == 3, data.get("files"))

    code, html = Client(url).req("GET", f"/v/{slug}", raw=True)
    text = html.decode("utf-8", "replace") if isinstance(html, bytes) else str(html)
    check("预览页 200", code == 200, str(code))
    check("预览页用项目自带图标", f'/p/{slug}/favicon.svg' in text, text[:300].replace("\n", " "))

    print("[3] 读：show / ls / stats")
    rc, d, _ = run(url, token, "show", slug)
    check("show 拿到地址", d.get("data", {}).get("url", "").endswith(f"/v/{slug}"))
    check("show 列出文件", d.get("data", {}).get("files") == 3, d.get("data", {}).get("file_list"))

    rc, d, _ = run(url, token, "ls", "--q", slug)
    check("ls 能检索到自己刚部署的", slug in (d.get("data", {}).get("slugs") or []), d)

    rc, d, _ = run(url, token, "stats", "--days", "7")
    check("stats 返回序列", isinstance(d.get("data", {}).get("items"), list), d)

    print("[4] 改：可见性 / 续期 / 标签")
    rc, d, _ = run(url, token, "set", slug, "--visibility", "portal")
    check("set 改可见性生效", d.get("data", {}).get("visibility") == "portal", d)
    code, html = admin.req("GET", "/portal", raw=True)
    text = html.decode("utf-8", "replace") if isinstance(html, bytes) else str(html)
    check("改完真的出现在门户列表", f'data-path="/v/{slug}"' in text)

    rc, d, _ = run(url, token, "extend", slug, "6")
    check("extend 把到期时间往后推了", (d.get("data", {}).get("expires_at") or 0) > int(time.time() * 1000) + 5 * 3600_000, d.get("data"))

    rc, d, _ = run(url, token, "set", slug, "--tags", "cli,验收")
    check("set 改标签生效", sorted(d.get("data", {}).get("tags") or []) == ["cli", "验收"], d)

    print("[5] 外链项目")
    rc, d, _ = run(url, token, "link", "https://example.com/x", "--title", "外链验收",
                   "--slug", f"link-{suffix}", "--ttl", "1")
    check("link 返回预览地址", str(d.get("data", {}).get("url", "")).endswith(f"/v/link-{suffix}"), d)

    print("[6] 批量")
    rc, d, _ = run(url, token, "bulk", "--action", "visibility", "--visibility", "private",
                   "--slugs", f"{slug},link-{suffix}")
    check("bulk 处理 2 个", d.get("data", {}).get("done") == 2, d)
    check("bulk 报告无跳过", d.get("data", {}).get("skipped") == 0, d)

    print("[7] 删除")
    rc, d, _ = run(url, token, "rm", slug, "--yes")
    check("rm 删除成功", d.get("data", {}).get("deleted") is True, d)
    check("rm 后链接失效", d.get("data", {}).get("gone") is True, d.get("data"))
    run(url, token, "rm", f"link-{suffix}", "--yes")

    print("[8] 自检命令")
    rc, d, _ = run(url, token, "selfcheck")
    steps = d.get("data", {}).get("steps") or []
    failed = [s["step"] for s in steps if not s["ok"]]
    check("selfcheck 全绿", d.get("data", {}).get("all_ok") is True, failed or d)
    check("selfcheck 覆盖增删改查", len(steps) >= 8, len(steps))

    print("[9] 越权与错误处理")
    viewer = Client(url)
    code, vd = admin.req("POST", "/api/agents", {
        "username": f"see{suffix}", "password": "see123456", "role": "viewer"})
    check("创建 viewer", code == 200, vd)
    code, vk = admin.req("GET", f"/api/agents/{vd['id']}/key")
    rc, d, _ = run(url, vk["api_key"], "deploy", str(tmp), "--slug", f"nope-{suffix}", expect=1)
    check("viewer 部署被拒", "403" in str(d.get("error", "")), d)
    rc, d, _ = run(url, vk["api_key"], "selfcheck")
    check("viewer selfcheck 判为无写权限", d.get("data", {}).get("note", "").startswith("viewer"), d)

    rc, d, _ = run(url, "pv_totally_wrong_key", "whoami", expect=1)
    check("坏 Key 报错清晰", "HTTP 401" in str(d.get("error", "")), d)

    print("[10] 成员管理（管理员）")
    admin_key = admin.req("GET", f"/api/agents/{1}/key")[1].get("api_key")
    if admin_key:
        rc, d, _ = run(url, admin_key, "members", "list")
        check("members list 可用", d.get("data", {}).get("total", 0) >= 2, d)
        rc, d, _ = run(url, admin_key, "members", "set", uname, "--label", "codex-cli")
        check("members set 改绑定名", d.get("ok") is True, d)
        rc, d, _ = run(url, token, "members", "list", expect=1)
        check("publisher 调 members 被拒", "403" in str(d.get("error", "")), d)

    print("[10.5] 收藏夹（建 / 归类 / 筛选 / 退回未归类）")
    cname = f"验收{suffix}"
    rc, d, _ = run(url, token, "collections", "add", "--name", cname)
    root_id = d.get("data", {}).get("id")
    check("collections add 建成一级夹", isinstance(root_id, int), d)

    rc, d, _ = run(url, token, "collections", "add", "--name", "子夹", "--parent", cname)
    kid_id = d.get("data", {}).get("id")
    check("collections add --parent 吃名字",
          isinstance(kid_id, int) and d.get("data", {}).get("parent_id") == root_id, d)

    rc, d, _ = run(url, token, "collections", "add", "--name", "深夹", "--parent", "子夹", expect=1)
    check("挂在子夹下面被拒（只两级）", "两级" in str(d.get("error", "")), d)

    rc, d, _ = run(url, token, "collections", "add", "--name", cname, expect=1)
    check("同级同名收藏夹被拒", "409" in str(d.get("error", "")), d)

    cslug = f"col-{suffix}"
    rc, d, _ = run(url, token, "deploy", str(tmp), "--slug", cslug, "--title", "归类验收",
                   "--collection", cname, "--ttl", "1")
    check("deploy --collection 用名字归类", d.get("data", {}).get("slug") == cslug, d)

    rc, d, _ = run(url, token, "collections")
    items = d.get("data", {}).get("items") or []
    node = next((i for i in items if i["id"] == root_id), None)
    check("collections 列出新建的一级夹", node is not None, [i["name"] for i in items])
    check("父夹合计含子夹项目", (node or {}).get("total", 0) >= 1, node)
    vis = d.get("data", {}).get("visibility") or {}
    check("collections 报三档可见性", set(vis) == {"portal", "link", "private"}, vis)
    check("三档可见性之和 = 项目总数",
          sum(vis.values()) == d.get("data", {}).get("total"),
          (vis, d.get("data", {}).get("total")))

    rc, d, _ = run(url, token, "ls", "--collection", cname)
    check("ls --collection 按名字筛出项目", cslug in (d.get("data", {}).get("slugs") or []), d)

    rc, d, _ = run(url, token, "ls", "--collection", "没这个夹", expect=1)
    check("ls --collection 名字不存在报错清晰", "找不到收藏夹" in str(d.get("error", "")), d)

    rc, d, _ = run(url, token, "set", cslug, "--collection", "子夹")
    check("set --collection 挪到子夹", d.get("ok") is True, d)
    rc, d, _ = run(url, token, "ls", "--collection", "子夹")
    check("子夹里能筛到搬过去的项目", cslug in (d.get("data", {}).get("slugs") or []), d)

    rc, d, _ = run(url, token, "set", cslug, "--no-collection")
    check("set --no-collection 退回未归类", d.get("ok") is True, d)
    rc, d, _ = run(url, token, "ls", "--collection", "none")
    check("未归类里能找到退回来的项目", cslug in (d.get("data", {}).get("slugs") or []), d)

    run(url, token, "set", cslug, "--collection", cname)
    rc, d, _ = run(url, token, "collections", "rm", cname)
    check("删夹默认不删项目", d.get("data", {}).get("deleted_projects") == 0, d)
    check("删夹报告项目退回未归类", (d.get("data", {}).get("moved_to_unassigned") or 0) >= 1, d)
    rc, d, _ = run(url, token, "show", cslug)
    check("删夹后项目还在", d.get("data", {}).get("slug") == cslug, d)
    rc, d, _ = run(url, token, "collections")
    left = [i["name"] for i in (d.get("data", {}).get("items") or [])]
    check("删夹时子夹一起没了", cname not in left and "子夹" not in left, left)
    run(url, token, "rm", cslug, "--yes")

    print("[11] 清理")
    admin.req("DELETE", f"/api/agents/{uid}")
    admin.req("DELETE", f"/api/agents/{vd['id']}")
    code, d = admin.req("GET", "/api/agents")
    check("临时成员已清理",
          not any(a["username"] in (uname, f"see{suffix}") for a in d.get("items", [])))

    print(f"\n{len(PASS)}/{len(PASS) + len(FAIL)} 通过")
    if FAIL:
        print("失败：")
        for f in FAIL:
            print("  -", f)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
