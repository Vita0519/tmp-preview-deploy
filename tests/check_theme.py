#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主题色：一个主色驱动控制台 / 门户 / 访客页，派生色与回落都要对。

覆盖：
  1. 默认主色是墨绿，/api/meta 与 /api/settings 都下发整套色板
  2. PATCH theme_accent 后，门户、预览页、错误页、theme-color 全部跟着变
  3. 派生色由主色算出（hover 更深、soft 更浅、line 带主色 rgb）
  4. 非法值（非 hex / 缺 # / #abc 简写 / 空串）→ 规范化或回落到默认
  5. 恢复默认后全站回到墨绿

用法: python tests/check_theme.py [--url http://127.0.0.1:8000]
"""
import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_test import FAIL, PASS, Client, check, multipart  # noqa: E402

HTML = b"<!doctype html><meta charset=utf-8><h1>theme</h1>"
DEFAULT = "#0f766e"


def hex2rgb(h):
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def brand_vars(body: str) -> dict:
    m = re.search(r":root\{--brand:([^;]+);--brand-hover:([^;]+);--brand-soft:([^;]+);"
                  r"--brand-line:([^;]+);--brand-deep:([^;]+);--brand-light:([^;]+);--brand-rgb:([^}]+)\}", body)
    if not m:
        return {}
    keys = ("brand", "hover", "soft", "line", "deep", "light", "rgb")
    return dict(zip(keys, [x.strip() for x in m.groups()]))


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

    # 造一个项目，后面用它的预览页验证
    slug = f"thm-{sfx}"
    body, ct = multipart({"slug": slug, "title": f"主题测试 {slug}", "hours": "2"},
                         [("files", "index.html", HTML)])
    admin.req("POST", "/api/projects", body, ct=ct, raw=True)

    print("[1] 默认色素")
    _ = admin.patch if False else None
    code, settings = admin.req("GET", "/api/settings")
    check("设置接口可取", code == 200, settings)
    t = settings.get("theme") or {}
    check("默认主色墨绿", t.get("accent") == DEFAULT, t.get("accent"))
    check("下发 8 个预设", len(t.get("presets") or []) == 8, len(t.get("presets") or []))
    code, meta = admin.req("GET", "/api/meta")
    check("/api/meta 也带主题", (meta.get("theme") or {}).get("accent") == DEFAULT, meta.get("theme"))

    print("[2] 派生色")
    p = t or {}
    check("hover 比主色深", sum(hex2rgb(p.get("hover", "#000"))) < sum(hex2rgb(DEFAULT)), p.get("hover"))
    check("soft 比主色浅", sum(hex2rgb(p.get("soft", "#000"))) > sum(hex2rgb(DEFAULT)), p.get("soft"))
    r, g, b = hex2rgb(DEFAULT)
    check("line 用主色 rgb", f"rgba({r},{g},{b}," in str(p.get("line")), p.get("line"))
    check("rgb 字段正确", p.get("rgb") == f"{r},{g},{b}", p.get("rgb"))

    print("[3] 换成靛蓝，全站跟随")
    code, d = admin.req("PATCH", "/api/settings", {"theme_accent": "#3b5bdb"})
    check("PATCH 成功", code == 200, d)
    check("返回新主色", (d.get("theme") or {}).get("accent") == "#3b5bdb", d.get("theme"))

    code, _, portal = admin.fetch("/portal")
    v = brand_vars(portal)
    check("门户 --brand 变了", v.get("brand") == "#3b5bdb", v.get("brand"))
    check("门户 theme-color 变了", 'content="#3b5bdb"' in portal)
    check("门户圆环用主色", "conic-gradient(var(--brand)" in portal or "var(--brand)" in portal)

    code, _, prev = admin.fetch(f"/v/{slug}")
    check("预览页 --brand 变了", brand_vars(prev).get("brand") == "#3b5bdb", brand_vars(prev).get("brand"))
    check("预览页品牌标记渐变跟随", "#3b5bdb" in prev or "var(--brand)" in prev)

    # 没开放下载时会渲染 403 错误页，正好验证错误页也吃同一套变量
    code, _, err = admin.fetch(f"/download/{slug}")
    check("错误页也带上变量", code == 403 and "--brand:" in err, f"{code} {'--brand:' in err}")

    print("[4] 非法输入")
    for raw, expect in (("#3b5bdb", "#3b5bdb"), ("3b5bdb", "#3b5bdb"), ("#3b5", "#33bb55"),
                        ("#zzz", DEFAULT), ("", DEFAULT), ("red", DEFAULT)):
        code, d = admin.req("PATCH", "/api/settings", {"theme_accent": raw})
        got = (d.get("theme") or {}).get("accent")
        check(f"{raw!r} → {expect}", code == 200 and got == expect, f"{code} {got}")

    print("[5] 恢复默认")
    code, d = admin.req("PATCH", "/api/settings", {"theme_accent": DEFAULT})
    check("回到墨绿", (d.get("theme") or {}).get("accent") == DEFAULT, d.get("theme"))
    code, _, portal = admin.fetch("/portal")
    check("门户也回到墨绿", brand_vars(portal).get("brand") == DEFAULT, brand_vars(portal).get("brand"))

    print("[清理]")
    c, _ = admin.req("DELETE", f"/api/projects/{slug}")
    check("临时项目已清理", c == 200)

    print(f"\n{len(PASS)}/{len(PASS) + len(FAIL)} 通过")
    if FAIL:
        print("失败：")
        for f in FAIL:
            print("  -", f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
