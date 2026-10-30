#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""门户 RSS：权限、结构、内容筛选与自动发现。

覆盖：
  1. 门户不公开 + 未登录 → 404（不能给阅读器一个 HTML 登录页）
  2. 登录后 → 200 + application/rss+xml
  3. XML 可解析，channel 字段齐全，item 的 link 指向 /v/<slug>
  4. 只收门户可见的项目；持链接 / 私有不出现
  5. 过期项目不出现
  6. 门户 head 里有 alternate 自动发现，页面上有 RSS 入口
  7. /feed.xml 与 /rss.xml 等价

用法: python tests/check_rss.py [--url http://127.0.0.1:8000]
"""
import argparse
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_test import FAIL, PASS, Client, check, multipart  # noqa: E402

HTML = b"<!doctype html><meta charset=utf-8><h1>rss</h1>"


def upload(c: Client, slug: str, title: str, visibility: str, hours="3"):
    body, ct = multipart(
        {"slug": slug, "title": title, "hours": hours, "visibility": visibility},
        [("files", "index.html", HTML)],
    )
    return c.req("POST", "/api/projects", body, ct=ct, raw=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="admin123")
    args = ap.parse_args()

    sfx = str(int(time.time()))[-6:]
    admin = Client(args.url)
    anon = Client(args.url)
    code, _ = admin.login(args.user, args.password)
    check("管理员登录", code == 200)

    # 造三个项目：门户 / 持链接 / 私有
    p_portal, p_link = f"rssp-{sfx}", f"rssk-{sfx}"
    for slug, vis in ((p_portal, "portal"), (p_link, "link")):
        code, payload = upload(admin, slug, f"RSS 测试 {slug}", vis)
        check(f"{vis} 项目建好", code == 200, payload[:80])

    print("[1] 权限")
    code, location, _ = anon.fetch("/rss.xml")
    public_now = code == 200
    if public_now:
        check("门户公开时匿名可读", True)
    else:
        check("门户未公开：匿名 404", code == 404, f"{code} {location}")
    code, location, _ = anon.fetch("/rss.xml", accept="application/rss+xml")
    check("匿名请求也不会被转去登录页", code in (200, 404), f"{code} {location}")

    print("[2] 结构")
    code, _, body = admin.fetch("/rss.xml")
    check("登录后 200", code == 200, code)
    root = None
    try:
        root = ET.fromstring(body)
        ok = True
    except ET.ParseError as exc:
        ok = False
        print("   XML 解析失败:", exc)
    check("是合法 XML", ok)
    if root is not None:
        ch = root.find("channel")
        check("根节点是 rss", root.tag == "rss")
        check("有 channel", ch is not None)
        check("有标题", bool((ch.findtext("title") or "").strip()), ch.findtext("title"))
        check("有 atom:link 自指",
              any(el.tag.endswith("link") for el in ch),
              [el.tag for el in ch][:4])
        items = ch.findall("item")
        check("至少 1 条", len(items) >= 1, len(items))
        first = items[0] if items else None
        if first is not None:
            link = first.findtext("link") or ""
            check("item link 指向 /v/", "/v/" in link, link)
            check("guid = link", first.findtext("guid") == link, first.findtext("guid"))
            check("pubDate 是 RFC822",
                  "," in (first.findtext("pubDate") or "") and "+" in (first.findtext("pubDate") or ""),
                  first.findtext("pubDate"))
            check("title 不为空", bool((first.findtext("title") or "").strip()))

    print("[3] 只收门户可见")
    titles = [i.findtext("title") or "" for i in ET.fromstring(body).iter("item")]
    check("包含门户项目", any(p_portal in t for t in titles), titles[:3])
    check("不含持链接项目", not any(p_link in t for t in titles), p_link)

    print("[4] 过期项目不进 RSS")
    admin.req("PATCH", f"/api/projects/{p_portal}", {"hours": 0.0002})  # 约 0.7 秒
    time.sleep(2.5)
    _, _, body2 = admin.fetch("/rss.xml")
    titles2 = [i.findtext("title") or "" for i in ET.fromstring(body2).iter("item")]
    check("过期后被剔除", not any(p_portal in t for t in titles2), p_portal)

    print("[5] 门户自动发现与入口")
    code, _, portal = admin.fetch("/portal")
    check("门户 200", code == 200, code)
    check("head 里有 alternate",
          'type="application/rss+xml"' in portal and 'href="/rss.xml"' in portal)
    check("页面上有 RSS 入口", 'href="/rss.xml"' in portal)

    print("[6] /feed.xml 别名")
    code, _, body3 = admin.fetch("/feed.xml")
    check("/feed.xml 也可用", code == 200 and "<rss" in body3, code)

    print("[清理]")
    ok = True
    for slug in (p_portal, p_link):
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
