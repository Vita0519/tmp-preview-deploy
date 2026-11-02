#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全站备份与恢复。

备份 = 一个 zip（数据库在线快照 + 项目文件 + zip 包 + 站点图标 + manifest），
恢复 = 校验 → 整体换血 → 旧数据留在 data/.backup-before-restore-<时间>/。

测试策略：先打一份包，再用这份包恢复回去。**内容是同一份快照**，所以
数据不会丢；但走完了真实的「搬家 → 换上新数据 → 清缓存」全流程。

覆盖：
  [1] 打包
      1. GET /api/backup → application/zip + 文件名
      2. zip 里有 db.sqlite3 / manifest.json / projects/
      3. manifest 里带各表条数，且跟现网对得上
  [2] 预览
      4. inspect 报出文件数 / 项目数 / 账号数
      5. 不是 zip → 422
      6. zip 里没有 db.sqlite3 → 422
  [3] 恢复
      7. 恢复返回 ok + 旧数据目录
      8. 恢复后服务仍健康、数据条数没变
      9. 旧数据真的留在安全区
     10. 安全区只留最近 3 份
  [4] 权限
     11. 成员不能下载备份
     12. 成员不能恢复
     13. 未登录 401
  [5] 浏览器
     14. 设置页有「备份恢复」面板
     15. 点打包下载能拿到 zip
     16. 选中 zip 后能预览里面有什么

用法: python tests/check_backup.py [--url http://127.0.0.1:8000] [--headed]
"""
import argparse
import io
import json
import sys
import time
import uuid
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_test import FAIL, PASS, Client, check, multipart  # noqa: E402


def inspect_bytes(c: Client, blob: bytes, name: str = "backup.zip"):
    body, ct = multipart({}, [("file", name, blob)])
    return c.req("POST", "/api/backup/inspect", body, ct=ct)


def restore_bytes(c: Client, blob: bytes, name: str = "backup.zip"):
    body, ct = multipart({}, [("file", name, blob)])
    return c.req("POST", "/api/backup/restore", body, ct=ct)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="admin123")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--keep-zip", default="", help="把打好的包另存到这个路径，方便手工看")
    args = ap.parse_args()

    admin = Client(args.url)
    code, _ = admin.login(args.user, args.password)
    check("管理员登录", code == 200)

    made_agents: list[str] = []
    blob = b""

    try:
        print("[1] 打包")
        code, hdrs, blob = admin.fetch_bytes("/api/backup")
        check("下载备份 200", code == 200, code)
        check("是 zip", "zip" in (hdrs.get("content-type") or ""), hdrs.get("content-type"))
        cd = hdrs.get("content-disposition") or ""
        check("是附件且带文件名", "attachment" in cd and ".zip" in cd, cd)
        check("包不是空的", len(blob) > 1024, f"{len(blob)} bytes")
        if args.keep_zip:
            Path(args.keep_zip).write_bytes(blob)

        zf = zipfile.ZipFile(io.BytesIO(blob))
        names = zf.namelist()
        check("包里有 db.sqlite3", "db.sqlite3" in names, names[:6])
        check("包里有 manifest.json", "manifest.json" in names, names[:6])
        check("包里有 projects/ 目录", any(n.startswith("projects/") for n in names), names[:6])
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        counts = manifest.get("counts") or {}
        check("manifest 带条数", {"projects", "users"} <= set(counts), counts)

        code, d = admin.req("GET", "/api/projects?limit=1")
        check("manifest 的项目数等于现网", counts.get("projects") == d.get("total", -1),
              f"{counts.get('projects')} vs {d.get('total')}")
        code, d = admin.req("GET", "/api/collections")
        check("manifest 的收藏夹数对得上",
              counts.get("collections", -1) >= len(d.get("items", [])), counts.get("collections"))

        print("[2] 预览")
        code, d = inspect_bytes(admin, blob)
        check("预览成功", code == 200 and d.get("db") is True, f"{code} {str(d)[:120]}")
        check("报出文件数", (d.get("files") or 0) > 0, d.get("files"))
        check("带 manifest 条数", (d.get("manifest") or {}).get("counts", {}).get("projects") == counts["projects"],
              d.get("manifest"))

        code, d = inspect_bytes(admin, b"not a zip at all", "x.zip")
        check("不是 zip → 422", code == 422, f"{code} {d}")

        empty = io.BytesIO()
        with zipfile.ZipFile(empty, "w") as z:
            z.writestr("readme.txt", "hello")
        code, d = inspect_bytes(admin, empty.getvalue())
        check("没有 db.sqlite3 → 422", code == 422, f"{code} {d}")

        print("[3] 恢复")
        before_projects = counts["projects"]
        code, d = restore_bytes(admin, blob)
        check("恢复返回 200", code == 200, f"{code} {str(d)[:160]}")
        check("返回 ok", (d or {}).get("ok") is True, d)
        check("返回旧的落点目录", ".backup-before-restore-" in ((d or {}).get("backup_dir") or ""),
              d.get("backup_dir"))
        check("恢复后的项目数一致", (d.get("counts") or {}).get("projects") == before_projects,
              d.get("counts"))

        safety = Path(d.get("backup_dir") or "")
        check("旧数据目录真的存在", safety.is_dir(), safety)
        check("旧库里也有一份 db", (safety / "db.sqlite3").exists(), list(safety.glob("*"))[:4])

        code, d = admin.req("GET", "/api/health")
        check("恢复后服务仍健康", code == 200 and d.get("ok"), f"{code} {d}")
        code, d = admin.req("GET", "/api/projects?limit=1")
        check("恢复后项目数没变", d.get("total") == before_projects, f"{d.get('total')} vs {before_projects}")
        code, d = admin.req("GET", "/api/collections")
        check("恢复后收藏夹还在", code == 200 and isinstance(d.get("items"), list), code)

        # 再恢复一次，顺手验证安全区保留策略
        code, d2 = restore_bytes(admin, blob)
        check("可以连续恢复", code == 200, f"{code} {str(d2)[:120]}")
        data_dir = safety.parent
        safeties = sorted(data_dir.glob(".backup-before-restore-*"))
        check("安全区最多留 3 份", len(safeties) <= 3, [p.name for p in safeties])

        print("[4] 权限")
        agent_name = f"bk{uuid.uuid4().hex[:5]}"
        code, d = admin.req("POST", "/api/agents", {"username": agent_name, "display_name": "备份测试"})
        made_agents.append(agent_name)
        check("建一个成员账号", code == 200, f"{code} {d}")
        agent = Client(args.url)
        agent.token = (d or {}).get("api_key") or ""
        code, _ = agent.req("GET", "/api/backup", raw=True)
        check("成员不能下载备份", code == 403, code)
        code, _ = restore_bytes(agent, blob)
        check("成员不能恢复", code == 403, code)

        anon = Client(args.url)
        code, _ = anon.req("GET", "/api/backup", raw=True)
        check("未登录 401", code == 401, code)

        print("[5] 浏览器")
        browser_suite(args.url.rstrip("/"), args.user, args.password, args.headed)
    finally:
        for name in made_agents:
            admin.req("DELETE", f"/api/agents/{name}")

    print(f"\n{len(PASS)}/{len(PASS) + len(FAIL)} 通过")
    if FAIL:
        print("失败：")
        for f in FAIL:
            print("  -", f)
        return 1
    return 0


def browser_suite(base: str, user: str, password: str, headed: bool) -> None:
    from playwright.sync_api import sync_playwright

    tmp_zip = Path(__import__("tempfile").gettempdir()) / "check_backup_dl.zip"
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=not headed)
        ctx = b.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
        pg = ctx.new_page()
        errs = []

        pg.goto(base + "/login", wait_until="domcontentloaded")
        pg.fill('input[autocomplete="username"]', user)
        pg.fill('input[type="password"]', password)
        pg.click('button[type="submit"]')
        pg.wait_for_url(lambda u: "/login" not in u, timeout=15000)

        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: errs.append(m.text)
              if m.type == "error" and "401" not in m.text else None)

        pg.goto(base + "/settings", wait_until="domcontentloaded")
        pg.wait_for_selector("#backup", timeout=15000)

        print("[5.1] 面板在")
        check("设置页有备份恢复面板", pg.locator("#backup").count() == 1)
        check("面板说明了备份范围",
              "项目文件" in pg.inner_text("#backup"), pg.inner_text("#backup")[:60])
        check("侧栏导航里有入口", pg.locator("text=备份恢复").count() >= 1)

        print("[5.2] 打包下载")
        with pg.expect_download(timeout=120000) as dl:
            pg.locator("#backup a", has_text="打包下载").click()
        d = dl.value
        d.save_as(tmp_zip)
        check("真的下到一个 zip", d.suggested_filename.endswith(".zip"), d.suggested_filename)
        check("下载的文件不是空的", tmp_zip.exists() and tmp_zip.stat().st_size > 1024,
              tmp_zip.stat().st_size if tmp_zip.exists() else "missing")

        print("[5.3] 选包预览")
        with pg.expect_file_chooser() as fc:
            pg.locator("#backup button", has_text="选择备份 zip").click()
        fc.value.set_files(str(tmp_zip))
        pg.wait_for_timeout(400)
        check("选中后显示文件名", "check_backup_dl.zip" in pg.inner_text("#backup"),
              pg.inner_text("#backup")[-120:])
        pg.locator("#backup button", has_text="先看看里面有什么").click()
        try:
            pg.wait_for_function(
                "() => document.getElementById('backup').innerText.includes('备份于')", timeout=60000
            )
        except Exception as exc:  # noqa: BLE001 - 超时就让下面的断言报出来
            print("     预览没出来：", exc.__class__.__name__)
        panel = pg.inner_text("#backup")
        check("预览报出项目/账号/文件数",
              "项目" in panel and "账号" in panel and "文件" in panel, panel[-160:])
        check("提示这是不可撤销操作", "不可撤销" in panel, panel[-80:])

        check("全程无 JS 报错", not errs, errs[:3])
        b.close()


if __name__ == "__main__":
    sys.exit(main())
