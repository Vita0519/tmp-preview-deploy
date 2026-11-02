#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""浏览器书签导入 / 导出。

Chrome、Edge、Firefox、Safari 导出的都是同一种 Netscape 书签 HTML，
所以一个解析器全吃。文件夹变成收藏夹（只取前两级，更深的折进第二级），
书签变成外链项目；同一个网址重复导入自动跳过。

覆盖：
  [1] 预览（dry_run）
      1. 解析出条数 / 可导入数 / 无效数
      2. 文件夹路径被算出来（含二级）
      3. dry_run 不落库
  [2] 导入
      4. 按书签文件夹建收藏夹
      5. 深层文件夹折进第二级
      6. 书签变外链项目 + 默认仅自己可见
      7. 重复导入按网址判重
      8. 指定 parent_id 时都进那个夹
      9. 不是书签文件 → 422、空请求 → 400
  [3] 导出
     10. attachment + X-Bookmark-Count
     11. 正文是 Netscape 格式，浏览器能认
     12. 按收藏夹导出只含该夹
     13. 导出的文件能再导入（说明格式没坏）
  [4] 权限
     14. 未登录不能导入 / 导出
  [5] 浏览器
     15. 弹窗里预览数字对得上
     16. 导入后侧栏出现新收藏夹
     17. 导出链接带当前收藏夹

用法: python tests/check_bookmarks.py [--url http://127.0.0.1:8000] [--headed]
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_test import FAIL, PASS, Client, check, multipart  # noqa: E402

# 一份「Chrome 风格」的书签：两条在书签栏，办公下面再套一层，最后一个 javascript: 是坏的
FIXTURE = """<!DOCTYPE NETSCAPE-Bookmark-file-1>
<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">
<TITLE>Bookmarks</TITLE>
<H1>Bookmarks</H1>
<DL><p>
    <DT><H3 ADD_DATE="1700000000" PERSONAL_TOOLBAR_FOLDER="true">书签栏</H3>
    <DL><p>
        <DT><A HREF="{base}/alpha" ADD_DATE="1700000001">Alpha 文档</A>
        <DT><H3 ADD_DATE="1700000002">办公</H3>
        <DL><p>
            <DT><A HREF="{base}/beta" ADD_DATE="1700000003">Beta 报表</A>
            <DT><H3 ADD_DATE="1700000004">更深的层</H3>
            <DL><p>
                <DT><A HREF="{base}/gamma" ADD_DATE="1700000005">Gamma 深层</A>
            </DL><p>
        </DL><p>
    </DL><p>
    <DT><H3 ADD_DATE="1700000006">其他书签</H3>
    <DL><p>
        <DT><A HREF="{base}/delta" ADD_DATE="1700000007">Delta</A>
        <DT><A HREF="javascript:void(0)" ADD_DATE="1700000008">坏书签</A>
    </DL><p>
</DL><p>
"""


def do_import(c: Client, html: str, **fields):
    f = {"visibility": "private"}
    f.update({k: str(v) for k, v in fields.items() if v is not None})
    if "dry_run" in fields and fields["dry_run"]:
        f["dry_run"] = "1"
    body, ct = multipart(f, [("file", "bookmarks.html", html.encode("utf-8"))])
    return c.req("POST", "/api/import/bookmarks", body, ct=ct)


def project_total(c: Client) -> int:
    code, d = c.req("GET", "/api/projects?limit=1")
    return d.get("total", -1) if code == 200 else -1


def folder_names(c: Client) -> list[tuple[str, str]]:
    code, tree = c.req("GET", "/api/collections")
    out = []
    for n in tree.get("items", []):
        out.append((n["name"], ""))
        for k in n.get("children") or []:
            out.append((n["name"], k["name"]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="admin123")
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()

    sfx = str(int(time.time()))[-5:]
    base_url = f"https://bm{sfx}.example.com"
    html = FIXTURE.format(base=base_url)
    admin = Client(args.url)
    code, _ = admin.login(args.user, args.password)
    check("管理员登录", code == 200)

    made_colls: list[int] = []

    try:
        print("[1] 预览")
        before = project_total(admin)
        code, d = do_import(admin, html, dry_run=True)
        check("预览成功", code == 200 and d.get("dry_run") is True, f"{code} {str(d)[:160]}")
        check("解析出 5 条", d.get("parsed") == 5, d.get("parsed"))
        check("可导入 4 条", d.get("will_create") == 4, d.get("will_create"))
        check("坏书签被跳过 1 条", d.get("skipped_invalid") == 1, d.get("skipped_invalid"))
        folders = [tuple(f) for f in d.get("folders") or []]
        check("算出 3 个文件夹", d.get("folders_total") == 3, folders)
        check("文件夹路径是两层", ("书签栏", "办公") in folders, folders)
        check("顶层文件夹路径第二段为空", ("书签栏", "") in folders, folders)
        check("预览不落库", project_total(admin) == before, f"{before} → {project_total(admin)}")

        print("[2] 导入")
        code, d = do_import(admin, html)
        check("导入成功", code == 200 and d.get("created") == 4, f"{code} {str(d)[:160]}")
        check("建了 3 个收藏夹", d.get("folders_created") == 3, d.get("folders_created"))
        check("默认可见性是仅自己", d.get("visibility") == "private", d.get("visibility"))
        check("项目数 +4", project_total(admin) == before + 4, f"{before} → {project_total(admin)}")

        names = folder_names(admin)
        check("收藏夹出现在树里", ("书签栏", "") in names and ("其他书签", "") in names, names)
        check("二级收藏夹挂在书签栏下", ("书签栏", "办公") in names, names)
        check("第三层没有单独建夹（折进第二级）", not any(n[1] == "更深的层" for n in names),
              [n for n in names if n[1]])

        code, tree = admin.req("GET", "/api/collections")
        for n in tree.get("items", []):
            made_colls.append(n["id"])
            for k in n.get("children") or []:
                made_colls.append(k["id"])
        root_node = next(n for n in tree["items"] if n["name"] == "书签栏")

        code, d = admin.req("GET", f"/api/projects?collection={root_node['id']}&limit=50")
        got = [p for p in d.get("items", []) if (p.get("link_url") or "").startswith(base_url)]
        check("书签栏里 3 条（含已折进来的深层那条）", len(got) == 3, len(got))
        check("书名变外链项目", all(p.get("kind") == "link" for p in got) and bool(got), got[:2])
        check("深层书签落在办公夹里",
              any((p.get("collection") or {}).get("name") == "办公" for p in got),
              [p.get("collection") for p in got])
        check("导入的书签只自己可见", all(p.get("visibility") == "private" for p in got),
              [p.get("visibility") for p in got])

        code, d = do_import(admin, html)
        check("再导一次不重复建", d.get("created") == 0 and d.get("skipped_duplicate") == 4,
              f"created={d.get('created')} dup={d.get('skipped_duplicate')}")
        check("重复导入后项目数不变", project_total(admin) == before + 4, project_total(admin))

        # 指定 parent_id：全部塞进这个夹（换一批网址，免得被判重）
        html2 = FIXTURE.format(base=f"https://b2{sfx}.example.com")
        target = root_node["id"]
        code, d = do_import(admin, html2, parent_id=target)
        check("指定 parent_id 也能导", code == 200 and d.get("created") == 4, f"{code} {str(d)[:160]}")
        code, d = admin.req("GET", f"/api/projects?collection={root_node['id']}&limit=100")
        got2 = [p for p in d.get("items", []) if f"b2{sfx}" in (p.get("link_url") or "")]
        check("都进了指定的收藏夹（含子夹，不越层）", len(got2) == 4, len(got2))

        code, d = do_import(admin, "<html><body>hello</body></html>")
        check("不是书签文件 → 422", code == 422, f"{code} {d}")
        body, ct = multipart({}, [])
        code, d = admin.req("POST", "/api/import/bookmarks", body, ct=ct)
        check("空请求 → 400", code == 400, f"{code} {d}")

        print("[3] 导出")
        code, hdrs, raw = admin.fetch_bytes("/api/export/bookmarks")
        check("导出 200", code == 200, code)
        check("是附件下载", "attachment" in (hdrs.get("content-disposition") or ""),
              hdrs.get("content-disposition"))
        check("带条数头", (hdrs.get("x-bookmark-count") or "").isdigit(), hdrs.get("x-bookmark-count"))
        total_all = int(hdrs.get("x-bookmark-count") or 0)
        text = raw.decode("utf-8", "replace")
        check("是 Netscape 书签格式", text.lstrip().startswith("<!DOCTYPE NETSCAPE-Bookmark-file-1>"),
              text[:60])
        check("带 <DL>/<H3>/<A>", "<DL>" in text and "<H3" in text and "<A HREF" in text, "")
        check("收藏夹名进了导出", "书签栏" in text and "办公" in text, "")
        check("自己的书签都在里面", f"{base_url}/alpha" in text, "")

        code, hdrs, raw = admin.fetch_bytes(f"/api/export/bookmarks?collection={root_node['id']}")
        text2 = raw.decode("utf-8", "replace")
        n2 = int(hdrs.get("x-bookmark-count") or 0)
        check("按收藏夹导出条数更少", 0 < n2 < total_all, f"{n2} / {total_all}")
        check("按收藏夹导出不含别的夹的书签", f"{base_url}/delta" not in text2, "delta 属于其他书签")
        check("文件名带收藏夹 id",
              f"bookmarks-{root_node['id']}.html" in (hdrs.get("content-disposition") or ""),
              hdrs.get("content-disposition"))

        code, d = do_import(admin, text)
        check("导出的文件能再导入（格式没坏）",
              code == 200 and d.get("skipped_duplicate", 0) >= 4,
              f"{code} created={d.get('created')} dup={d.get('skipped_duplicate')}")

        print("[4] 权限")
        anon = Client(args.url)
        code, _ = anon.req("GET", "/api/export/bookmarks")
        check("未登录不能导出", code == 401, code)
        body, ct = multipart({}, [("file", "b.html", html.encode())])
        code, _ = anon.req("POST", "/api/import/bookmarks", body, ct=ct)
        check("未登录不能导入", code == 401, code)

        print("[5] 浏览器")
        browser_suite(args.url.rstrip("/"), args.user, args.password, args.headed, sfx)
    finally:
        for cid in made_colls:
            admin.req("DELETE", f"/api/collections/{cid}?with_projects=1")
        code, d = admin.req("GET", "/api/projects?limit=200")
        for p in d.get("items", []):
            if "example.com" in (p.get("link_url") or ""):
                admin.req("DELETE", f"/api/projects/{p['slug']}")

    print(f"\n{len(PASS)}/{len(PASS) + len(FAIL)} 通过")
    if FAIL:
        print("失败：")
        for f in FAIL:
            print("  -", f)
        return 1
    return 0


def browser_suite(base: str, user: str, password: str, headed: bool, sfx: str) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=not headed)
        pg = b.new_context(viewport={"width": 1440, "height": 900}).new_page()
        errs = []

        pg.goto(base + "/login", wait_until="domcontentloaded")
        pg.fill('input[autocomplete="username"]', user)
        pg.fill('input[type="password"]', password)
        pg.click('button[type="submit"]')
        pg.wait_for_url(lambda u: "/login" not in u, timeout=15000)

        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: errs.append(m.text)
              if m.type == "error" and "401" not in m.text else None)

        pg.goto(base + "/", wait_until="domcontentloaded")
        pg.wait_for_selector(".railrow", timeout=15000)
        pg.wait_for_timeout(300)

        print("[5.1] 弹窗预览")
        pg.locator("button", has_text="导入书签").first.click()
        pg.wait_for_selector(".dropzone", timeout=5000)
        tmp = Path(tempfile_path())
        tmp.write_text(FIXTURE.format(base="https://ui" + sfx + ".example.com"), encoding="utf-8")
        with pg.expect_file_chooser() as fc:
            pg.locator(".dropzone").click()
        fc.value.set_files(str(tmp))
        pg.wait_for_timeout(200)
        pg.locator("button", has_text="先预览").click()
        pg.wait_for_selector(".modal .panel", timeout=10000)
        panel = pg.inner_text(".modal .panel")
        check("预览显示可导入 4 条", "4" in panel.split("\n")[0], panel.split("\n")[0])
        check("预览列出收藏夹", "书签栏" in panel, panel[:120])

        print("[5.2] 真的导进去")
        pg.locator(".modal-foot .btn.primary").click()
        pg.wait_for_timeout(2200)
        check("弹窗关掉", pg.locator(".modal").count() == 0)
        rail = pg.inner_text(".rail")
        check("侧栏出现「书签栏」", "书签栏" in rail, rail.replace("\n", "|")[:120])

        print("[5.3] Esc 关弹窗")
        pg.locator("button", has_text="导入书签").first.click()
        pg.wait_for_selector(".modal", timeout=5000)
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(300)
        check("Esc 能关掉导入弹窗", pg.locator(".modal").count() == 0)

        print("[5.4] 导出链接")
        pg.locator(".railrow", has_text="书签栏").first.click()
        pg.wait_for_timeout(600)
        href = pg.evaluate(
            """() => { const a=[...document.querySelectorAll('a')].find(x=>/导出/.test(x.innerText));
                 return a ? a.getAttribute('href') : null }"""
        )
        check("导出链接带当前收藏夹", bool(href) and "collection=" in href, href)

        check("全程无 JS 报错", not errs, errs[:3])
        b.close()


def tempfile_path() -> str:
    import tempfile
    from pathlib import Path as _P

    return str(_P(tempfile.gettempdir()) / "check_bookmarks_fixture.html")


if __name__ == "__main__":
    sys.exit(main())
