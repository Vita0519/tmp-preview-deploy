#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""失效链接一律回门户；外链项目直接跳外部站点，不再套 iframe。

覆盖：
  1. 不存在 / 已删除 / 已过期 / 无权访问 → /v/ 302 到 /portal
  2. iframe 里取不到文件 → 返回能跳出 iframe 的失效页（而不是原地 404）
  3. 子资源请求（图片/CSS）失效 → 静默 404，不跳转
  4. 外链项目 /v/ 与 /p/ 都 302 到目标站点，门户卡片直接指向外部地址
  5. 只有一个 html（不叫 index.html）的项目仍然能打开，不被当成失效

用法: python tests/check_gone.py [--url http://127.0.0.1:8000]
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_test import FAIL, PASS, Client, check, multipart  # noqa: E402

FILES = [("files", "index.html", b"<!doctype html><meta charset=utf-8><h1>alive</h1>")]
ONLY_HTML = [("files", "report.html", b"<!doctype html><meta charset=utf-8><h1>only</h1>")]
NO_ENTRY = [("files", "readme.txt", b"no html here")]


def upload(c: Client, slug: str, title: str, files=FILES, extra=None):
    fields = {"slug": slug, "title": title, "hours": "2"}
    fields.update(extra or {})
    body, ct = multipart(fields, files)
    return c.req("POST", "/api/projects", body, ct=ct)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="admin123")
    args = ap.parse_args()
    url = args.url
    sfx = str(int(time.time()))[-4:]

    admin = Client(url)
    code, _ = admin.login(args.user, args.password)
    check("管理员登录", code == 200, str(code))
    guest = Client(url)

    print("[1] 不存在的 slug")
    code, loc = guest.probe(f"/v/nope-{sfx}")
    check("/v/ 不存在 → 302", code == 302, str(code))
    check("跳到门户", loc.startswith("/portal"), loc)
    code, loc = guest.probe(f"/download/nope-{sfx}")
    check("/download/ 不存在 → 302 到门户", code == 302 and loc.startswith("/portal"), f"{code} {loc}")

    print("[2] 项目被删掉")
    slug = f"gone-{sfx}"
    code, d = upload(admin, slug, f"会消失的站 {sfx}")
    check("项目建成", code == 200, str(code))
    code, loc = guest.probe(f"/v/{slug}")
    check("删除前 /v/ 正常 200", code == 200, str(code))
    admin.req("DELETE", f"/api/projects/{slug}")
    code, loc = guest.probe(f"/v/{slug}")
    check("删除后 /v/ → 302 到门户", code == 302 and loc.startswith("/portal"), f"{code} {loc}")

    print("[3] 项目到期")
    slug2 = f"exp-{sfx}"
    code, d = upload(admin, slug2, f"会过期的站 {sfx}")
    check("项目建成", code == 200, str(code))
    code, _ = admin.req("PATCH", f"/api/projects/{slug2}", {"expires_at": 1})
    check("改成已过期", code == 200, str(code))
    code, loc = guest.probe(f"/v/{slug2}")
    check("过期后 /v/ → 302 到门户", code == 302 and loc.startswith("/portal"), f"{code} {loc}")
    code, loc = guest.probe(f"/p/{slug2}/")
    check("过期后 /p/ 页面请求 → 404 失效页", code == 404, str(code))
    code, _loc, text = guest.fetch(f"/p/{slug2}/", "text/html")
    check("失效页会跳出 iframe", "top" in text and "/portal" in text, text[:120])
    code, _ = guest.req("GET", f"/p/{slug2}/style.css", raw=True, headers={"Accept": "text/css"})
    check("子资源失效 → 静默 404（不跳转）", code == 404, str(code))

    print("[4] 私有项目不给外人看")
    slug3 = f"priv-{sfx}"
    code, d = upload(admin, slug3, f"私有站 {sfx}", extra={"visibility": "private"})
    check("私有项目建成", code == 200, str(code))
    code, loc = guest.probe(f"/v/{slug3}")
    check("匿名打开私有 → 302 到门户（不泄露存在性）", code == 302 and loc.startswith("/portal"), f"{code} {loc}")
    code, _ = admin.probe(f"/v/{slug3}")
    check("作者自己打开私有 → 200", code == 200, str(code))

    print("[5] 外链项目直接跳外部站点")
    link_slug = f"ext-{sfx}"
    target = "https://example.com/figma-demo"
    code, d = admin.req(
        "POST", "/api/projects/link", {"link_url": target, "title": f"外链站 {sfx}", "visibility": "portal"}
    )
    check("外链项目建成", code == 200, str(code))
    code, loc = guest.probe(f"/v/{d.get('slug', '')}")
    check("/v/ 外链 → 302 直跳目标站点", code == 302 and loc == target, f"{code} {loc}")
    code, loc = guest.probe(f"/p/{d.get('slug', '')}/")
    check("/p/ 外链 → 302 直跳目标站点", code == 302 and loc == target, f"{code} {loc}")

    pub_slug = f"pub-{sfx}"
    code, _ = upload(admin, pub_slug, f"对照静态站 {sfx}", extra={"visibility": "portal"})
    check("建一个门户可见的静态项目做对照", code == 200, str(code))

    code, _loc, portal = admin.fetch("/portal", "text/html")
    link_slug = d.get("slug", "")
    check("门户卡片里外链直接指向外部地址", f'href="{target}"' in portal, "")
    check("外链卡片不再包 /v/ 外壳", f'href="/v/{link_slug}"' not in portal, "")
    check("外链卡片的复制按钮复制外部地址", f'data-path="{target}"' in portal, "")
    check("静态卡片仍然是 /v/ 预览外壳", f'href="/v/{pub_slug}"' in portal, "")

    print("[6] 只有非 index.html 的单页站不算失效")
    slug4 = f"only-{sfx}"
    code, d = upload(admin, slug4, f"单页站 {sfx}", files=ONLY_HTML)
    check("单 html 项目建成", code == 200, str(code))
    code, _ = guest.probe(f"/v/{slug4}")
    check("/v/ 仍然 200（不误判为失效）", code == 200, str(code))
    code, body = guest.req("GET", f"/p/{slug4}/", raw=True, headers={"Accept": "text/html"})
    text = body if isinstance(body, str) else body.decode("utf-8", "replace")
    check("根路径回退到唯一的 html", "only" in text, text[:60])

    print("[7] 完全没有 html 的项目视为失效")
    slug5 = f"noentry-{sfx}"
    code, d = upload(admin, slug5, f"没入口 {sfx}", files=NO_ENTRY)
    check("无 html 项目建成", code == 200, str(code))
    code, loc = guest.probe(f"/v/{slug5}")
    check("/v/ → 302 到门户", code == 302 and loc.startswith("/portal"), f"{code} {loc}")

    print("[8] 门户的失效提示")
    code, _loc, text = admin.fetch("/portal?gone=1", "text/html")
    check("门户里有提示条", "gonebar" in text and "已经失效" in text, "")
    check("提示条默认隐藏，靠 JS 显示", 'id="gonebar" hidden' in text, "")

    print("[清理]")
    code, d = admin.req("GET", "/api/projects?limit=200&status=all")
    for item in d.get("items", []):
        if sfx in item["slug"]:
            admin.req("DELETE", f"/api/projects/{item['slug']}")
    code, d = admin.req("GET", "/api/projects?limit=200&status=all")
    check("临时项目已清理", not any(sfx in x["slug"] for x in d.get("items", [])), "")

    print(f"\n{len(PASS)}/{len(PASS) + len(FAIL)} 通过")
    if FAIL:
        print("失败：")
        for f in FAIL:
            print("  -", f)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
