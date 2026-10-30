#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""配色系列：6 套「主色 + 中性色画布」下发、切换、回落。

覆盖：
  1. /api/settings 下发系列清单，字段齐全、每套中性色 13 个变量
  2. 每套主色与白底的对比度 ≥ 3:1（以后加系列不许塞个看不见的色）
  3. PATCH theme_series 后 meta / settings / 门户 / 预览页全部跟着换
  4. 门户 :root 里的 --bg / --ink 就是该系列的值（不是硬编码）
  5. 非法 key 回落 classic；同请求带主色时以主色为准（自定义）
  6. 跑完还原进来时的系列与主色

用法: python tests/check_series.py [--url http://127.0.0.1:8000]
"""
import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_test import FAIL, PASS, Client, check, multipart  # noqa: E402

HTML = b"<!doctype html><meta charset=utf-8><h1>series</h1>"
NEUTRAL_KEYS = {"bg", "bg-2", "bg-deep", "surface-2", "surface-3",
                "ink", "ink-2", "ink-3", "ink-4", "line", "line-2", "ink-rgb", "bg-rgb"}


def lum(c: str) -> float:
    def ch(v: int) -> float:
        x = v / 255
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4

    h = c.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast_on_white(c: str) -> float:
    return 1.05 / (lum(c) + 0.05)


def root_vars(body: str) -> dict:
    m = re.search(r":root\{(.*?)\}", body, re.S)
    if not m:
        return {}
    return {k: v.strip() for k, v in re.findall(r"--([a-z0-9-]+):([^;}]+)", m.group(1))}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="admin123")
    args = ap.parse_args()

    sfx = str(int(time.time()))[-6:]
    c = Client(args.url)
    code, _ = c.login(args.user, args.password)
    check("管理员登录", code == 200)
    if code != 200:
        return 1

    # 造个项目，用来验证预览页也吃同一套变量
    slug = f"ser{sfx}"
    body, ct = multipart({"slug": slug, "title": f"配色测试 {sfx}", "hours": "2"},
                         [("files", "index.html", HTML)])
    c.req("POST", "/api/projects", body, ct=ct, raw=True)

    th0 = (c.req("GET", "/api/settings")[1] or {}).get("theme") or {}
    orig_series = th0.get("series") or "classic"
    orig_raw = th0.get("raw") or th0.get("accent") or "#0f766e"

    try:
        run(c, slug, orig_series, orig_raw)
    finally:
        print("[清理]")
        c.req("PATCH", "/api/settings", {"theme_series": orig_series, "theme_accent": orig_raw})
        back = (c.req("GET", "/api/settings")[1] or {}).get("theme") or {}
        check("系列已还原", back.get("series") == orig_series, back.get("series"))
        check("主色已还原", back.get("raw") == orig_raw, back.get("raw"))
        c.req("DELETE", f"/api/projects/{slug}")

    print()
    print(f"{len(PASS)}/{len(PASS) + len(FAIL)} 通过")
    if FAIL:
        print("失败：")
        for f in FAIL:
            print("  -", f)
        return 1
    return 0


def run(c: Client, slug: str, orig_series: str, orig_raw: str):
    print("[1] 系列清单")
    th = (c.req("GET", "/api/settings")[1] or {}).get("theme") or {}
    series = th.get("series_list") or []
    check("下发 6 套系列", len(series) == 6, len(series))
    keys = [s.get("key") for s in series]
    check("key 唯一", len(set(keys)) == len(keys), keys)
    check("含经典墨绿", "classic" in keys, keys)
    check("含科技感 / 马卡龙", {"tech", "macaron"} <= set(keys), keys)
    for res in series:
        ok = all(res.get(k) for k in ("key", "name", "desc", "use", "accent", "neutral"))
        check(f"{res.get('name')} 字段齐全", ok, res)
        n = res.get("neutral") or {}
        check(f"{res.get('name')} 中性色 13 项", set(n) == NEUTRAL_KEYS, sorted(set(n) ^ NEUTRAL_KEYS))
        check(f"{res.get('name')} 主色合法", bool(re.fullmatch(r"#[0-9a-f]{6}", res.get("accent") or "")), res.get("accent"))

    print("[2] 每套主色在白底上都看得见（≥3:1）")
    for res in series:
        r = contrast_on_white(res["accent"])
        check(f"{res['name']} 对比度 {r:.2f}", r >= 3.0, r)

    print("[3] 切换系列，全站跟着换")
    for res in series:
        code, d = c.req("PATCH", "/api/settings", {"theme_series": res["key"]})
        th = (d or {}).get("theme") or {}
        check(f"切到{res['name']}", code == 200 and th.get("series") == res["key"], th.get("series"))
        check(f"{res['name']} 主色跟随", th.get("accent") == res["accent"], th.get("accent"))
        check(f"{res['name']} 画布跟随",
              (th.get("neutral") or {}).get("bg") == res["neutral"]["bg"],
              (th.get("neutral") or {}).get("bg"))

        meta = (c.req("GET", "/api/meta")[1] or {}).get("theme") or {}
        check(f"{res['name']} meta 同步", meta.get("series") == res["key"] and meta.get("accent") == res["accent"],
              [meta.get("series"), meta.get("accent")])

        _, _, portal = c.fetch("/portal")
        v = root_vars(portal)
        check(f"{res['name']} 门户 --bg 正确", v.get("bg") == res["neutral"]["bg"], v.get("bg"))
        check(f"{res['name']} 门户 --ink 正确", v.get("ink") == res["neutral"]["ink"], v.get("ink"))
        check(f"{res['name']} 门户 --brand 正确", v.get("brand") == res["accent"], v.get("brand"))
        check(f"{res['name']} 门户 --ink-rgb 可用",
              v.get("ink-rgb") == ",".join(str(int(res["neutral"]["ink"][i:i + 2], 16)) for i in (1, 3, 5)),
              v.get("ink-rgb"))

        _, _, prev = c.fetch(f"/v/{slug}")
        pv = root_vars(prev)
        check(f"{res['name']} 预览页同款画布", pv.get("bg") == res["neutral"]["bg"], pv.get("bg"))

    print("[4] 硬编码的暖灰不该再出现在页面里当底色")
    _, _, portal = c.fetch("/portal")
    # 只查最容易被漏掉的几处：body 背景与吸顶区
    check("body 背景走变量", "background:var(--bg" in portal.replace(" ", ""), portal[:0])
    check("吸顶区底走变量", "rgba(var(--bg-rgb)" in portal.replace(" ", ""), portal[:0])

    print("[5] 非法 key / 自定义主色")
    code, d = c.req("PATCH", "/api/settings", {"theme_series": "no-such-theme"})
    th = (d or {}).get("theme") or {}
    check("非法 key 回落 classic", code == 200 and th.get("series") == "classic", th.get("series"))

    code, d = c.req("PATCH", "/api/settings", {"theme_series": "tech", "theme_accent": "#8a2be2"})
    th = (d or {}).get("theme") or {}
    check("同时给系列和主色 → 系列生效", th.get("series") == "tech", th.get("series"))
    check("同时给系列和主色 → 主色以请求为准", th.get("raw") == "#8a2be2", th.get("raw"))
    check("自定义主色标记为 custom", th.get("custom") is True, th.get("custom"))
    check("自定义主色不动画布", (th.get("neutral") or {}).get("bg") == "#f3f5fa", (th.get("neutral") or {}).get("bg"))

    code, d = c.req("PATCH", "/api/settings", {"theme_series": "tech"})
    th = (d or {}).get("theme") or {}
    check("再选同一系列 → 主色归位", th.get("accent") == "#2563eb" and th.get("custom") is False,
          [th.get("accent"), th.get("custom")])


if __name__ == "__main__":
    sys.exit(main())
