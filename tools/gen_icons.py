#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成站点图标的位图产物：favicon.ico / apple-touch-icon.png / icon-192 / icon-512。

矢量源只有一份：`frontend/public/favicon.svg`。位图用 Chrome 渲染（纯 Python 没有矢量光栅化器，
自己写一套不如直接用浏览器，看到的和标签页里完全一致），生成结果直接提交进仓库，
**运行时不依赖 Playwright**。

用法：
    python tools/gen_icons.py            # 生成/覆盖
    python tools/gen_icons.py --check    # 只检查源文件是否比产物新
"""
from __future__ import annotations

import argparse
import pathlib
import struct
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "frontend" / "public"
SRC = PUBLIC / "favicon.svg"

# iOS 主屏图标与 maskable 图标不能有透明角（会被垫黑底），所以铺一层实色底
FLAT_BG = "#0d6a62"

ICO_SIZES = (16, 32, 48)
PNG_TARGETS = {
    "apple-touch-icon.png": (180, True),
    "icon-192.png": (192, False),
    "icon-512.png": (512, True),  # 兼作 maskable，铺底更安全
}


def _png(svg_markup: str, size: int, opaque: bool) -> bytes:
    """用 Chrome 把 SVG 渲染成指定边长的 PNG。"""
    from playwright.sync_api import sync_playwright

    bg = f"background:{FLAT_BG}" if opaque else "background:transparent"
    # SVG 自带 width/height="32"，必须用 CSS 顶掉，否则截出来永远是 32×32
    html = (
        "<!doctype html><meta charset=utf-8>"
        f"<style>html,body{{margin:0;padding:0;{bg}}}"
        f"svg{{display:block;width:{size}px;height:{size}px}}</style>"
        f"{svg_markup}"
    )
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": size, "height": size}, device_scale_factor=1)
        page.set_content(html)
        el = page.query_selector("svg")
        data = el.screenshot(omit_background=not opaque)
        browser.close()
    return data


def _ico(entries: list[tuple[int, bytes]]) -> bytes:
    """把若干张 PNG 打成 .ico（Vista 起支持内嵌 PNG，Windows 全部主流浏览器认）。"""
    head = struct.pack("<HHH", 0, 1, len(entries))
    offset = 6 + 16 * len(entries)
    dirs, blobs = b"", b""
    for size, png in entries:
        dirs += struct.pack(
            "<BBBBHHII",
            size if size < 256 else 0,  # 宽
            size if size < 256 else 0,  # 高
            0,                          # 调色板数
            0,                          # 保留
            1,                          # 色彩平面
            32,                         # 位深
            len(png),                   # 数据长度
            offset,
        )
        blobs += png
        offset += len(png)
    return head + dirs + blobs


def build() -> int:
    if not SRC.is_file():
        print(f"缺少矢量源：{SRC}")
        return 1
    markup = SRC.read_text(encoding="utf-8")
    if "viewBox=\"0 0 32 32\"" not in markup:
        print("矢量源不是 32×32 viewBox，先确认再生成")
        return 1

    written = []
    ico_entries = []
    for size in ICO_SIZES:
        data = _png(markup, size, opaque=False)
        ico_entries.append((size, data))
        (PUBLIC / f"favicon-{size}.png").write_bytes(data)
        written.append((f"favicon-{size}.png", len(data)))

    ico = _ico(ico_entries)
    (PUBLIC / "favicon.ico").write_bytes(ico)
    written.append(("favicon.ico", len(ico)))

    for name, (size, opaque) in PNG_TARGETS.items():
        data = _png(markup, size, opaque=opaque)
        (PUBLIC / name).write_bytes(data)
        written.append((name, len(data)))

    # 顺便把一份 SVG 复制成 /icon.svg（部分平台只认这个路径）
    (PUBLIC / "icon.svg").write_bytes(SRC.read_bytes())
    written.append(("icon.svg", SRC.stat().st_size))

    for name, size in written:
        print(f"  {name:<22} {size / 1024:7.1f} KB")
    print(f"共 {len(written)} 个文件 → {PUBLIC}")
    return 0


def check() -> int:
    stale = [p.name for p in PUBLIC.glob("*.png") if p.stat().st_mtime < SRC.stat().st_mtime]
    if (PUBLIC / "favicon.ico").exists() and (PUBLIC / "favicon.ico").stat().st_mtime < SRC.stat().st_mtime:
        stale.append("favicon.ico")
    if stale:
        print("产物比矢量源旧，需要重新生成：" + "、".join(sorted(stale)))
        return 1
    print("图标产物是最新的")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="生成站点图标位图产物")
    ap.add_argument("--check", action="store_true", help="只检查是否过期，不生成")
    args = ap.parse_args()
    return check() if args.check else build()


if __name__ == "__main__":
    sys.exit(main())
