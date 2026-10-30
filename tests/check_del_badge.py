#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""到期删除的视觉强调：门户卡片 / 列表行 / 预览页都要看得出来。

「到期删除」和「到期停访」后果完全不同（一个连目录删掉、一个只停访问），
只在设置页说明不够，得在项目出现的地方都标出来。

覆盖：
  1. 门户卡片：del 类 + 琥珀描边 + 左侧竖条 CSS + 徽章文案
  2. 门户列表行：row del + 同样的徽章
  3. 预览页顶栏：带「到期删除」提示；停访项目没有
  4. 改成停访后标记消失，改回来又出现
  5. 徽章有 title 说明后果，别只靠颜色

用法: python tests/check_del_badge.py [--url http://127.0.0.1:8000]
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_test import FAIL, PASS, Client, check, multipart  # noqa: E402

HTML = b"<!doctype html><meta charset=utf-8><h1>badge</h1>"


def card_block(html: str, title: str) -> str:
    """按 data-title 把某张卡片的整段 HTML 切出来（到下一张卡片为止）。"""
    key = f'data-title="{title}"'
    i = html.find(key)
    if i < 0:
        return ""
    start = html.rfind('<div class="card', 0, i)
    end = html.find('<div class="card', i)
    return html[start:end if end > 0 else start + 4000]


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

    def make(slug, title, action):
        body, ct = multipart(
            {
                "slug": slug,
                "title": title,
                "hours": "6",
                "expire_action": action,
                "visibility": "portal",
                "tags": "到期演示",
            },
            [("files", "index.html", HTML)],
        )
        code, d = admin.req("POST", "/api/projects", body, ct=ct, raw=True)
        # raw=True 成功时回字节，报错时回已解析的 dict，统一成 dict
        if isinstance(d, bytes):
            try:
                d = json.loads(d or b"{}")
            except json.JSONDecodeError:
                d = {"raw": d[:120].decode("utf-8", "replace")}
        return code, d

    del_slug, keep_slug = f"dels{sfx}", f"keeps{sfx}"
    c1, d1 = make(del_slug, f"到期删除 {sfx}", "delete")
    c2, d2 = make(keep_slug, f"到期停访 {sfx}", "block")
    check("建删除型项目", c1 == 200 and d1.get("expire_action") == "delete", f"{c1} {d1.get('expire_action')}")
    check("建停访型项目", c2 == 200 and d2.get("expire_action") == "block", f"{c2} {d2.get('expire_action')}")

    print("[1] 门户卡片")
    code, _, portal = admin.fetch("/portal")
    check("门户可取", code == 200, code)
    check("删除型卡片带 del 类", f'class="card del"' in portal)
    check("停访型卡片不带 del 类", f'data-act="block"' in portal)
    check("卡片带 data-act 标记", f'data-act="delete"' in portal)

    card = card_block(portal, f"到期删除 {sfx}")
    check("删除型卡片有琥珀描边", 'class="card del"' in card[:80], card[:60])
    check("徽章文案是「到期删除」", 'class="deltag"' in card and "到期删除" in card)
    check("徽章说明了后果", "不可恢复" in card)

    card2 = card_block(portal, f"到期停访 {sfx}")
    check("停访型卡片没有徽章", 'class="deltag"' not in card2, card2[:60])

    print("[2] 门户列表行")
    check("列表行也有 del 类", 'class="row del"' in portal)
    rows = portal.split('class="row')
    del_row = next((r for r in rows if f'data-title="到期删除 {sfx}"' in r[:400]), "")
    check("列表行里也带徽章", 'class="deltag"' in del_row[:2500])

    print("[3] 样式就位")
    check("卡片竖条 CSS", ".card.del::before" in portal)
    check("行竖条 CSS", ".row.del::before" in portal)
    check("徽章 CSS", ".deltag{" in portal)
    check("删除型进度条改琥珀", ".card.del .track > i" in portal)

    print("[4] 预览页顶栏")
    code, _, prev = admin.fetch(f"/v/{del_slug}")
    check("删除型预览页 200", code == 200, code)
    check("预览页带徽章", 'class="deltag"' in prev)
    check("预览页徽章文案", "到期删除" in prev)
    code, _, prev2 = admin.fetch(f"/v/{keep_slug}")
    check("停访型预览页没有徽章", 'class="deltag"' not in prev2, code)

    print("[5] 改了动作标记跟着变")
    code, d = admin.req("PATCH", f"/api/projects/{del_slug}", {"expire_action": "block"})
    check("改成停访", code == 200 and d.get("expire_action") == "block", d.get("expire_action"))
    code, _, portal = admin.fetch("/portal")
    check("卡片不再标记", "card del" not in card_block(portal, f"到期删除 {sfx}")[:80])

    code, d = admin.req("PATCH", f"/api/projects/{del_slug}", {"expire_action": "delete"})
    check("改回删除", code == 200 and d.get("expire_action") == "delete", d.get("expire_action"))
    code, _, portal = admin.fetch("/portal")
    check("卡片重新标记", 'class="card del"' in portal)

    print("[清理]")
    left = [admin.req("DELETE", f"/api/projects/{s}")[0] for s in (del_slug, keep_slug)]
    check("临时项目已清理", all(c == 200 for c in left), left)
    code, _, portal = admin.fetch("/portal")
    check("门户已无演示项目", f"到期删除 {sfx}" not in portal)

    print(f"\n{len(PASS)}/{len(PASS) + len(FAIL)} 通过")
    if FAIL:
        print("失败：")
        for f in FAIL:
            print("  -", f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
