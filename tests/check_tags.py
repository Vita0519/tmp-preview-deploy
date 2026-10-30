#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""标签规则：数量 / 长度 / 字符 / 归一化 / 去重 / 池子回收。

规则是硬约束，超了要 422 且话说清楚，不静默截断。

覆盖：
  1. 规则通过 /api/meta 与 /api/settings 下发，两处数值一致
  2. 归一化：全角转半角、英文小写、逗号顿号分号空格都当分隔符、重名合并
  3. 校验：超过 6 个 / 超过 12 字 / 非法字符 / 尖括号 —— 全部 422
  4. 改属性同样受规则约束；批量打标签满了会截断并回报 trimmed
  5. 标签没人用了会被回收，/api/settings/tags/prune 也能手动清
  6. 存量数据：所有项目标签都符合规则、没有大写遗留

用法: python tests/check_tags.py [--url http://127.0.0.1:8000]
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_test import FAIL, PASS, Client, check, multipart  # noqa: E402

HTML = b"<!doctype html><meta charset=utf-8><h1>tags</h1>"
MAX = 6
MAX_LEN = 12


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

    def make(tags, slug=None, title=None):
        slug = slug or f"tag{sfx}-{abs(hash(str(tags))) % 9999}"
        body, ct = multipart(
            {"slug": slug, "title": title or slug, "hours": "3", "tags": tags, "visibility": "link"},
            [("files", "index.html", HTML)],
        )
        code, d = admin.req("POST", "/api/projects", body, ct=ct, raw=True)
        return code, d, slug

    def detail(slug):
        code, d = admin.req("GET", f"/api/projects/{slug}")
        return d or {}

    def patch(slug, payload):
        return admin.req("PATCH", f"/api/projects/{slug}", payload)

    made: list[str] = []

    print("[1] 规则下发")
    code, meta = admin.req("GET", "/api/meta")
    mt = meta.get("tags") or {}
    check("/api/meta 带标签规则", code == 200 and mt.get("max_per_project") == MAX, mt)
    check("单个长度上限 12", mt.get("max_len") == MAX_LEN, mt.get("max_len"))
    code, st = admin.req("GET", "/api/settings")
    stg = st.get("tags") or {}
    check("/api/settings 与 meta 一致",
          (stg.get("max_per_project"), stg.get("max_len")) == (mt.get("max_per_project"), mt.get("max_len")),
          stg)
    check("带池子占用", isinstance(stg.get("used"), int) and stg.get("pool_max", 0) > 0, stg.get("used"))

    print("[2] 归一化与去重")
    code, d, s1 = make("Vue, VUE 、vue")
    made.append(s1)
    check("三种写法合并成一个", code == 200 and detail(s1).get("tags") == ["vue"], detail(s1).get("tags"))
    code, d, s2 = make(" 前端 ，验收 ")
    made.append(s2)
    check("全角逗号+首尾空格", detail(s2).get("tags") == ["前端", "验收"], detail(s2).get("tags"))
    code, d, s3 = make("alpha beta;gamma、delta")
    made.append(s3)
    check("空格/分号/顿号都是分隔符",
          sorted(detail(s3).get("tags") or []) == ["alpha", "beta", "delta", "gamma"],
          detail(s3).get("tags"))
    code, d, s4 = make("ＶＵＥ，ＡＢＣ")
    made.append(s4)
    check("全角字母转半角小写", detail(s4).get("tags") == ["abc", "vue"], detail(s4).get("tags"))
    code, d, s5 = make(",,a,,b,")
    made.append(s5)
    check("空段直接忽略", detail(s5).get("tags") == ["a", "b"], detail(s5).get("tags"))

    print("[3] 硬约束")
    code, d, _ = make("a,b,c,d,e,f,g")
    check(f"超过 {MAX} 个 → 422", code == 422 and "最多 6 个" in str(d), f"{code} {d}")
    code, d, _ = make("x" * (MAX_LEN + 1))
    check("超过 12 字 → 422", code == 422 and "太长" in str(d), f"{code} {d}")
    code, d, _ = make("数据/分析")
    check("斜杠 → 422", code == 422 and "不允许的字符" in str(d), f"{code} {d}")
    code, d, _ = make("<b>x</b>")
    check("尖括号 → 422", code == 422, f"{code} {d}")
    code, d, s6 = make("c++, node.js, v2.0")
    made.append(s6)
    check("+ # . - 这类符号可用",
          sorted(detail(s6).get("tags") or []) == ["c++", "node.js", "v2.0"], detail(s6).get("tags"))

    print("[4] 改属性与批量")
    code, d = patch(s1, {"tags": ["一", "二", "三", "四", "五", "六"]})
    check("改属性可以填满 6 个", code == 200 and len(d.get("tags") or []) == MAX, d.get("tags"))
    code, d = patch(s1, {"tags": ["一", "二", "三", "四", "五", "六", "七"]})
    check("改属性超限同样 422", code == 422, f"{code} {d}")
    code, d = patch(s1, {"tags": ["一", "二", "三", "四", "五", "六", "七"][:5]})
    check("改属性后剩 5 个", code == 200 and len(d.get("tags") or []) == 5, d.get("tags"))

    code, d = admin.req("POST", "/api/projects/bulk", {"slugs": [s1], "action": "tag_add", "tags": "甲,乙,丙"})
    tags_after = detail(s1).get("tags") or []
    check("批量补标签最多补到 6 个", len(tags_after) == MAX, tags_after)
    check("回报被截断的项目数", d.get("trimmed") == 1, d)

    code, d = admin.req("POST", "/api/projects/bulk", {"slugs": [s2], "action": "tag_add", "tags": "X/Y"})
    check("批量里的非法标签也 422", code == 422, f"{code} {d}")

    print("[5] 标签回收")
    before = (admin.req("GET", "/api/settings")[1].get("tags") or {}).get("used")
    code, d = patch(s6, {"tags": ["唯一标签"]})
    after = (admin.req("GET", "/api/settings")[1].get("tags") or {}).get("used")
    check("换标签后旧的没人用就回收", code == 200 and after < before + 1, f"{before} -> {after}")
    orphans = (admin.req("GET", "/api/settings")[1].get("tags") or {}).get("orphans")
    check("没有悬空标签", orphans == 0, orphans)
    code, d = admin.req("POST", "/api/settings/tags/prune", {})
    check("手动清理接口可用", code == 200 and d.get("tags", {}).get("orphans") == 0, d)

    print("[6] 存量数据合规")
    code, d = admin.req("GET", "/api/projects?limit=200&status=all")
    items = d.get("items") or []
    check("能取到项目列表", code == 200 and isinstance(items, list), code)
    bad_count = [p["slug"] for p in items if len(p.get("tags") or []) > MAX]
    bad_case = [t for p in items for t in (p.get("tags") or []) if t != t.lower()]
    check(f"没有超过 {MAX} 个标签的项目", not bad_count, bad_count[:3])
    check("没有大写遗留", not bad_case, bad_case[:5])

    print("[清理]")
    left = [admin.req("DELETE", f"/api/projects/{s}")[0] for s in made]
    check("临时项目已清理", all(c in (200, 404) for c in left), left)

    print(f"\n{len(PASS)}/{len(PASS) + len(FAIL)} 通过")
    if FAIL:
        print("失败：")
        for f in FAIL:
            print("  -", f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
