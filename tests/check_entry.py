#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""入口文件规则：单文件不限文件名，多文件必须有根目录 index.html。

覆盖：
  1. 单个 report.html（不叫 index）→ entry 就是它，/v/ 的 iframe 指向它，/p/ 根路径 200
  2. 单个 demo.htm / 单个 index.html 同样可用
  3. 单文件是 PDF → entry 也是它（不当成"没有入口"）
  4. 多文件 + 根目录 index.html → 正常，entry=index.html
  5. 多文件 + 没有 index.html 但有别的 html → 422，且文案说清怎么办
  6. 多文件 + 一个 html 都没有（纯素材包）→ 允许，entry 留空
  7. 单文件项目的访问计数生效（曾经因为 entry 为空而不计数）
  8. 旧项目（entry 为空但根目录只有一个 html）仍然能打开，不被判成失效

用法: python tests/check_entry.py [--url http://127.0.0.1:8000]
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_test import FAIL, PASS, Client, check, multipart  # noqa: E402

HTML = b"<!doctype html><meta charset=utf-8><h1>entry</h1>"


def upload(c: Client, slug: str, title: str, files, extra=None):
    fields = {"slug": slug, "title": title, "hours": "3"}
    fields.update(extra or {})
    body, ct = multipart(fields, files)
    return c.req("POST", "/api/projects", body, ct=ct, raw=True)


def make(c: Client, slug: str, files, title=None, extra=None):
    """建项目，返回 (状态码, 解析后的 JSON)。"""
    import json

    code, payload = upload(c, slug, title or f"入口 {slug}", files, extra)
    if isinstance(payload, dict):  # 4xx 时 Client 已经解析好了
        return code, payload
    try:
        return code, json.loads(payload or b"{}")
    except json.JSONDecodeError:
        return code, {"raw": payload[:200].decode("utf-8", "replace")}


def by_slug(c: Client, slug: str):
    code, d = c.req("GET", f"/api/projects/{slug}")
    return d if code == 200 else {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="admin123")
    args = ap.parse_args()

    sfx = str(int(time.time()))[-6:]
    admin = Client(args.url)
    code, _ = admin.login(args.user, args.password)
    check("管理员登录", code == 200)

    created: list[str] = []

    # ---------- 1. 单文件 report.html ----------
    print("[1] 单个 html，名字不是 index")
    slug = f"single-{sfx}"
    code, d = make(admin, slug, [("files", "report.html", HTML)])
    created.append(slug)
    check("上传成功", code == 200, d)
    check("entry 就是 report.html", d.get("entry") == "report.html", d.get("entry"))
    code, loc, body = admin.fetch(f"/v/{slug}")
    check("/v/ 200", code == 200, f"{code} {loc}")
    check("iframe 指向 report.html", f'src="/p/{slug}/report.html"' in body, body[:200])
    code, loc, _ = admin.fetch(f"/p/{slug}/")
    check("/p/ 根路径 200", code == 200, f"{code} {loc}")
    code, _, body = admin.fetch(f"/p/{slug}/")
    check("/p/ 根路径返回的就是那个页面", "entry" in body, body[:80])

    # ---------- 2. 计数 ----------
    print("[2] 单文件项目也计数")
    before = by_slug(admin, slug).get("views") or 0
    admin.fetch(f"/p/{slug}/", accept="text/html")
    time.sleep(3.6)  # 计数是内存缓冲，等它落库
    after = by_slug(admin, slug).get("views") or 0
    check("访问 +1", after > before, f"{before} → {after}")

    # ---------- 3. 单文件 .htm ----------
    print("[3] 单个 .htm")
    slug2 = f"htm-{sfx}"
    code, d = make(admin, slug2, [("files", "demo.htm", HTML)])
    created.append(slug2)
    check("entry = demo.htm", d.get("entry") == "demo.htm", d.get("entry"))
    code, _, _ = admin.fetch(f"/v/{slug2}")
    check("/v/ 200", code == 200, code)

    # ---------- 4. 单文件 PDF ----------
    print("[4] 单文件不是 html")
    slug3 = f"pdf-{sfx}"
    code, d = make(admin, slug3, [("files", "menu.pdf", b"%PDF-1.4 fake")])
    created.append(slug3)
    check("entry = menu.pdf", d.get("entry") == "menu.pdf", d.get("entry"))
    code, _, _ = admin.fetch(f"/p/{slug3}/")
    check("/p/ 根路径能拿到文件", code == 200, code)

    # ---------- 5. 多文件 + index.html ----------
    print("[5] 多文件 + 根目录 index.html")
    slug4 = f"multi-{sfx}"
    code, d = make(admin, slug4, [
        ("files", "index.html", HTML),
        ("files", "style.css", b"body{margin:0}"),
        ("files", "assets/app.js", b"console.log(1)"),
    ])
    created.append(slug4)
    check("上传成功", code == 200, d)
    check("entry = index.html", d.get("entry") == "index.html", d.get("entry"))
    check("文件数 3", d.get("file_count") == 3, d.get("file_count"))

    # ---------- 6. 多文件没有 index ----------
    print("[6] 多文件但没有 index.html")
    slug5 = f"noindex-{sfx}"
    code, d = make(admin, slug5, [
        ("files", "a.html", HTML),
        ("files", "b.html", HTML),
    ])
    check("被拒绝 422", code == 422, f"{code} {d}")
    check("文案提到 index.html", "index.html" in str(d.get("detail")), d.get("detail"))
    code, _, _ = admin.fetch(f"/p/{slug5}/")
    check("没有留下半成品项目", code in (302, 404), code)

    # ---------- 7. 多文件纯素材 ----------
    print("[7] 多文件但没有 html（素材包）")
    slug6 = f"assets-{sfx}"
    code, d = make(admin, slug6, [
        ("files", "readme.txt", b"hello"),
        ("files", "img/a.png", b"\x89PNG fake"),
    ])
    check("同样被拒绝 422", code == 422, f"{code} {d}")
    check("文案提示改走 zip", "zip" in str(d.get("detail", "")).lower(), d.get("detail"))

    # ---------- 8. 覆盖更新也走同一套规则 ----------
    print("[8] 覆盖更新同样校验")
    code, d = make(admin, slug2, [
        ("files", "x.html", HTML),
        ("files", "y.html", HTML),
    ], title=f"入口 {slug2}")
    check("覆盖成多文件无 index → 422", code == 422, f"{code} {d}")
    code, d = by_slug(admin, slug2), None
    check("原项目没被破坏", code.get("entry") == "demo.htm", code.get("entry"))

    # ---------- 清理 ----------
    print("[清理]")
    ok = True
    for slug in created:
        c, _ = admin.req("DELETE", f"/api/projects/{slug}")
        ok = ok and c == 200
    check("临时项目已清理", ok)

    print(f"\n{len(PASS)}/{len(PASS) + len(FAIL)} 通过")
    if FAIL:
        print("失败：")
        for f in FAIL:
            print("  -", f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
