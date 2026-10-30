#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主题色：一个主色驱动控制台 / 门户 / 访客页，派生色与回落都要对。

覆盖：
  1. /api/meta 与 /api/settings 下发整套色板，且两者一致；预设里含默认墨绿
  2. PATCH theme_accent 后，门户、预览页、错误页、theme-color 全部跟着变
  3. 派生色由主色算出（hover 更深、soft 更浅、line 带主色 rgb）
  4. 非法值（非 hex / 缺 # / #abc 简写 / 空串）→ 规范化或回落到默认
  5. 跑完把主色还原成进来时的值（不覆盖管理员自己选的色）
  6. 站点图标：上传 / 校验 / /site-icon 回落 / webmanifest 跟随

用法: python tests/check_theme.py [--url http://127.0.0.1:8000]
"""
import argparse
import base64
import json
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
                  r"--brand-line:([^;]+);--brand-deep:([^;]+);--brand-light:([^;]+);"
                  r"--brand-rgb:([0-9,]+)", body)
    if not m:
        return {}
    keys = ("brand", "hover", "soft", "line", "deep", "light", "rgb")
    return dict(zip(keys, [x.strip() for x in m.groups()]))


def neutral_vars(body: str) -> dict:
    """从 :root 里取整套中性色变量（--bg / --ink / --line …）。"""
    m = re.search(r":root\{(.*?)\}", body, re.S)
    if not m:
        return {}
    out = {}
    for k, v in re.findall(r"--((?:bg|surface|ink|line)[a-z0-9-]*):([^;}]+)", m.group(1)):
        out[k] = v.strip()
    return out


def contrast_ok(hex_color: str, minimum: float = 3.0) -> bool:
    """主色跟白底的对比度是否达标（跟前端 theme.js 的 readable 同一把尺子）。"""
    if not hex_color or not re.fullmatch(r"#[0-9a-f]{6}", hex_color):
        return False

    def lum(c):
        def ch(v):
            v /= 255
            return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

        r, g, b = hex2rgb(c)
        return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)

    return (1.05) / (lum(hex_color) + 0.05) >= minimum


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

    print("[1] 当前色板")
    code, settings = admin.req("GET", "/api/settings")
    check("设置接口可取", code == 200, settings)
    t = settings.get("theme") or {}
    orig = str(t.get("accent") or DEFAULT)
    # 用户填的原值（可能因为太浅被 readable 压深），还原时要还原这个
    orig_raw = str(t.get("raw") or orig)
    check("主色是合法 hex", bool(re.fullmatch(r"#[0-9a-f]{6}", orig)), orig)
    presets = t.get("presets") or []
    check("下发 8 个预设", len(presets) == 8, len(presets))
    check("预设里含默认墨绿", any(p.get("value") == DEFAULT for p in presets),
          [p.get("value") for p in presets[:3]])
    code, meta = admin.req("GET", "/api/meta")
    check("/api/meta 与设置同色", (meta.get("theme") or {}).get("accent") == orig, meta.get("theme"))

    print("[2] 派生色")
    p = t or {}
    r, g, b = hex2rgb(orig)
    check("hover 比主色深", sum(hex2rgb(p.get("hover", "#000"))) < sum(hex2rgb(orig)), p.get("hover"))
    check("soft 比主色浅", sum(hex2rgb(p.get("soft", "#000"))) > sum(hex2rgb(orig)), p.get("soft"))
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

    print("[4] 非法输入（看 raw，实际生效值会被可读性兜底压深）")
    for raw, expect in (("#3b5bdb", "#3b5bdb"), ("3b5bdb", "#3b5bdb"), ("#3b5", "#33bb55"),
                        ("#zzz", DEFAULT), ("", DEFAULT), ("red", DEFAULT)):
        code, d = admin.req("PATCH", "/api/settings", {"theme_accent": raw})
        th = d.get("theme") or {}
        got = th.get("raw")
        check(f"{raw!r} → {expect}", code == 200 and got == expect, f"{code} {got}")
        # 不管填什么，落到 --brand 上的颜色都得在白底上看得见
        check(f"{raw!r} 生效色可读", contrast_ok(th.get("accent")), th.get("accent"))

    print("[5] 还原进来时的主色（不覆盖管理员的选择）")
    code, d = admin.req("PATCH", "/api/settings", {"theme_accent": orig_raw})
    check("还原成功", (d.get("theme") or {}).get("raw") == orig_raw, d.get("theme"))
    code, _, portal = admin.fetch("/portal")
    check("门户也回到原色", brand_vars(portal).get("brand") == orig, brand_vars(portal).get("brand"))

    print("[6] 站点图标")
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
    svg = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16"/></svg>'

    def post_icon(name: str, data: bytes):
        b, ct = multipart({}, [("file", name, data)])
        code, payload = admin.req("POST", "/api/settings/icon", b, ct=ct, raw=True)
        # 成功时 raw 回字节，报错时回已解析的 dict，这里统一成 dict
        if isinstance(payload, bytes):
            try:
                payload = json.loads(payload or b"{}")
            except json.JSONDecodeError:
                payload = {"raw": payload[:200].decode("utf-8", "replace")}
        return code, payload

    code, d = post_icon("site-icon.png", png)
    check("上传 png 成功", code == 200 and (d.get("site_icon") or {}).get("custom") is True, d)
    check("返回 /site-icon 地址", "/site-icon" in str((d.get("site_icon") or {}).get("url")), d.get("url"))

    code, hdr, raw = admin.fetch_bytes("/site-icon")
    check("/site-icon 可取到图", code == 200 and raw == png, f"{code} {len(raw)}B")
    check("/site-icon 类型对", "image/png" in str(hdr.get("content-type", "")), hdr.get("content-type"))
    check("/site-icon 允许缓存", "max-age" in str(hdr.get("cache-control", "")), hdr.get("cache-control"))

    code, meta = admin.req("GET", "/api/meta")
    check("/api/meta 带自定义图标", (meta.get("site_icon") or {}).get("custom") is True, meta.get("site_icon"))
    check("/api/meta 图标结构与设置一致",
          set(meta.get("site_icon") or {}) == set((d.get("site_icon") or {})),
          sorted((meta.get("site_icon") or {}).keys()))

    code, _, manifest = admin.fetch("/site.webmanifest")
    check("webmanifest 图标指向 /site-icon", "/site-icon" in manifest, manifest[:120])
    check("webmanifest theme_color 跟随主色", f'"theme_color":"{orig}"' in manifest, manifest[-120:])

    code, _, portal = admin.fetch("/portal")
    check("门户 <link rel=icon> 用自定义图标", "/site-icon" in portal)

    code, d = post_icon("note.txt", b"hello")
    check("非图片后缀 → 422", code == 422, d)
    code, d = post_icon("empty.png", b"")
    check("空文件 → 422", code == 422, d)
    code, d = post_icon("fake.svg", b"\x00\x01\x02not-svg")
    check("假 SVG → 422", code == 422, d)
    code, d = post_icon("big.png", png + b"\x00" * (513 * 1024))
    check("超过 512KB → 422", code == 422, d)
    code, d = post_icon("after-bad.png", png)
    check("失败后原图标没被破坏", code == 200 and (d.get("site_icon") or {}).get("custom") is True, d)

    code, d = post_icon("site-icon.svg", svg)
    check("换格式成 svg 成功", code == 200 and (d.get("site_icon") or {}).get("ext") == "svg", d.get("site_icon"))
    code, _, raw = admin.fetch("/site-icon")
    check("/site-icon 换成 svg 内容", code == 200 and raw == svg.decode(), f"{code} {raw[:20]}")

    code, d = admin.req("DELETE", "/api/settings/icon")
    check("删除后回到内置", code == 200 and (d.get("site_icon") or {}).get("custom") is False, d)
    code, _, _ = admin.fetch("/site-icon")
    check("没有自定义图标时 /site-icon 404", code == 404, code)
    code, _, portal = admin.fetch("/portal")
    check("门户回到内置图标", "/site-icon" not in portal)
    code, meta = admin.req("GET", "/api/meta")
    check("/api/meta 无自定义图标时给空壳", (meta.get("site_icon") or {}).get("custom") is False
          and not (meta.get("site_icon") or {}).get("url"), meta.get("site_icon"))

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
