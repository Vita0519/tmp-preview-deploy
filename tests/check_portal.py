#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""门户页结构回归：吸顶容器、卡片/列表双视图、圆环位置。

用法: python tests/check_portal.py [--url http://127.0.0.1:8000]
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_test import Client  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✓' if cond else '✗'} {name}{('  → ' + str(extra)[:200]) if extra and not cond else ''}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="admin123")
    args = ap.parse_args()

    c = Client(args.url)
    code, _ = c.login(args.user, args.password)
    check("登录", code == 200)
    if code != 200:
        return 1

    code, html = c.req("GET", "/portal", raw=True)
    check("门户 200", code == 200)
    if isinstance(html, bytes):
        html = html.decode("utf-8", "replace")

    print("[1] 吸顶容器")
    check("有 .dock", 'class="dock"' in html)
    dock = html.split('class="dock"', 1)[1].split('<div class="grid"', 1)[0] if 'class="dock"' in html else ""
    check("标签栏在 dock 内", 'id="tagsbar"' in dock)
    check("筛选条在 dock 内", 'class="tools"' in dock)
    check("作者名片在 dock 内", 'class="author"' in dock or "author" not in html, "无作者信息时跳过")
    check("dock 是 sticky", re.search(r"\.dock\{[^}]*position:sticky", html) is not None)
    check("卡片容器在 dock 之外", '<div class="grid" id="grid">' not in dock)

    print("[2] 双视图")
    check("有卡片容器", 'id="grid"' in html)
    check("有列表容器", 'id="rows"' in html)
    check("列表默认隐藏", re.search(r'<div class="rows" id="rows" hidden', html) is not None)
    check("视图切换按钮存在", 'id="viewseg"' in html and 'data-view="list"' in html)
    cards = re.findall(r'class="card"', html)
    rows = re.findall(r'class="row"', html)
    check("卡片与行数一致", len(cards) == len(rows) and len(cards) >= 0, f"card={len(cards)} row={len(rows)}")

    print("[3] 圆环与倒计时")
    # 卡片：ring 必须是 card 的直接子元素（不在 .top 里），才不会跟标题挤一行
    first_card = html.split('class="card"', 1)[1].split('<div class="card"', 1)[0] if cards else ""
    top_block = first_card.split('class="top"', 1)[1].split('class="desc"', 1)[0] if 'class="top"' in first_card else ""
    check("圆环不在 .top 里", "ring" not in top_block, top_block[:120])
    check("圆环在卡片内", 'class="ring"' in first_card)
    check("倒计时在 .foot 里", re.search(r'class="foot".*?class="cd ', first_card, re.S) is not None)
    check("卡片圆环绝对定位", re.search(r"\.ring\{position:absolute", html) is not None)

    first_row = html.split('class="row"', 1)[1].split('<div class="row"', 1)[0] if rows else ""
    for cls in ("rmain", "rdesc", "rtags", "rring", "rfoot"):
        check(f"列表行含 .{cls}", f'class="{cls}"' in first_row or f'class="{cls} ' in first_row)

    print("[4] 数据属性")
    for attr in ("data-exp", "data-total", "data-created", "data-views", "data-kind", "data-tags", "data-title"):
        check(f"卡片带 {attr}", attr in first_card)

    print("[5] 复制链接按钮")
    cbtns = re.findall(r'class="cbtn"', html)
    inflow = re.findall(r'class="cbtn inflow"', html)
    check("每张卡片一个复制按钮", len(cbtns) == len(cards) and len(cards) > 0, f"cbtn={len(cbtns)} card={len(cards)}")
    check("每个列表行一个复制按钮", len(inflow) == len(rows), f"inflow={len(inflow)} row={len(rows)}")
    check("按钮带 data-path", 'data-path="/v/' in first_card)
    check("卡片内有覆盖式链接 .hit", 'class="hit"' in first_card)
    check("按钮含「已复制」气泡", '<span class="tip">已复制</span>' in first_card)
    check("按钮含打勾图标", 'class="ic-done"' in first_card and 'class="ic-copy"' in first_card)
    check(".hit 覆盖层绝对定位", re.search(r"\.hit\{position:absolute", html) is not None)
    check(".cbtn 绝对定位且层级高于 .hit", re.search(r"\.cbtn\{position:absolute;z-index:3", html) is not None)
    check("行内按钮用 relative 参与网格", re.search(r"\.cbtn\.inflow\{position:relative;z-index:3", html) is not None)
    check("JS 用剪贴板 API", "navigator.clipboard" in html and "writeText" in html)
    check("JS 有 execCommand 兜底", "execCommand('copy')" in html)
    check("点击阻止冒泡", "stopPropagation" in html)

    total = len(PASS) + len(FAIL)
    print(f"\n{len(PASS)}/{total} 通过")
    if FAIL:
        print("失败：")
        for f in FAIL:
            print("  -", f)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
