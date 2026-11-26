#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主题插件引擎：内置黑/白两套、安装/启用/卸载、商店校验与守卫、门户跟随。

覆盖：
  1. /api/meta 与 /api/settings 下发 theme.vars（完整语义令牌）与 plugins 清单；
     内置只有 noir（玄夜·黑）与 ivory（象牙·白）
  2. PATCH theme_plugin 切换黑↔白：门户 / 预览页 / 错误页的 --bg、--scheme 跟着变
  3. 主色微调照旧：theme_accent 派生 --brand 族，两头对比度兜底
  4. 示例插件安装（source=example，不依赖外网）→ 出现在清单 → 卸载后消失；
     内置不可卸载；不存在/非法 id 被拒
  5. 商店预览：垃圾输入给能看懂的错误（不连真实仓库，避免限额抖动）
  6. 跑完恢复进来的主题与主色

用法: python tests/check_themes.py [--url http://127.0.0.1:8000]
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_test import FAIL, PASS, Client, check, multipart  # noqa: E402

HTML = b"<!doctype html><meta charset=utf-8><h1>themes</h1>"
NOIR_BG = "#0b0d10"
IVORY_BG = "#f6f7f5"


def root_vars(body: str) -> dict:
    m = re.search(r":root\{(.*?)\}", body, re.S)
    if not m:
        return {}
    return dict(re.findall(r"--([a-z0-9-]+):([^;}]+)", m.group(1)))


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

    # 进来时的主题状态，最后还原
    code, d0 = admin.req("GET", "/api/settings")
    th0 = d0.get("theme") or {}
    orig_plugin = th0.get("plugin") or "noir"
    orig_accent = str(th0.get("raw") or th0.get("accent") or "#2563eb")

    print("[1] 载荷与内置清单")
    check("meta 可取", code == 200)
    # 先清掉上一次运行 / 截图脚本残留的已装插件，让清单回到「只有内置」的基准
    for p in th0.get("plugins", []):
        if not p.get("builtin"):
            admin.req("DELETE", "/api/settings/themes/" + p["id"])
    code, meta = admin.req("GET", "/api/meta")
    th = meta.get("theme") or {}
    check("meta 带当前插件", th.get("plugin") == orig_plugin, th.get("plugin"))
    check("meta 带完整语义令牌", isinstance(th.get("vars"), dict) and "--bg" in th["vars"], list(th.get("vars", {}))[:5])
    check("meta 的 vars 不含 brand 派生族", not any(k.startswith("--brand") for k in th.get("vars", {})))
    ids = [p["id"] for p in th.get("plugins", [])]
    check("内置黑/白两套", {"noir", "ivory"} == set(ids), ids)
    noir = next(p for p in th["plugins"] if p["id"] == "noir")
    ivory = next(p for p in th["plugins"] if p["id"] == "ivory")
    check("noir 是深色内置", noir["mode"] == "dark" and noir["builtin"] is True, noir)
    check("ivory 是浅色内置", ivory["mode"] == "light" and ivory["builtin"] is True, ivory)
    check("卡片预览色齐全", all(noir["preview"].get(k) for k in ("bg", "surface", "ink", "accent")), noir["preview"])

    code, d = admin.req("GET", "/api/settings")
    ths = d.get("theme") or {}
    check("settings 的插件清单带完整 vars", all("vars" in p and p["vars"].get("--bg") for p in ths.get("plugins", [])))

    print("[2] 黑 ↔ 白切换，全站跟随")
    # 造一个项目，验证预览页也跟
    slug = f"thm-{sfx}"
    body, ct = multipart({"slug": slug, "title": f"主题测试 {slug}", "hours": "2"},
                         [("files", "index.html", HTML)])
    admin.req("POST", "/api/projects", body, ct=ct, raw=True)

    code, d = admin.req("PATCH", "/api/settings", {"theme_plugin": "ivory"})
    th = d.get("theme") or {}
    check("切到象牙", th.get("plugin") == "ivory", th.get("plugin"))
    check("象牙画布", th.get("vars", {}).get("--bg") == IVORY_BG, th.get("vars", {}).get("--bg"))
    check("scheme 变 light", th.get("vars", {}).get("--scheme") == "light", th.get("vars", {}).get("--scheme"))
    check("主色跟随主题默认", th.get("raw") == ivory["default_accent"], th.get("raw"))
    code, _, portal = admin.fetch("/portal")
    v = root_vars(portal)
    check("门户 --bg 变浅色", v.get("bg", "").strip() == IVORY_BG, v.get("bg"))
    check("门户 --scheme=light", v.get("scheme", "").strip() == "light", v.get("scheme"))
    check("门户 --surface 白卡", v.get("surface", "").strip() == "#ffffff", v.get("surface"))
    code, _, prev = admin.fetch(f"/v/{slug}")
    check("预览页同款画布", root_vars(prev).get("bg", "").strip() == IVORY_BG, root_vars(prev).get("bg"))

    code, d = admin.req("PATCH", "/api/settings", {"theme_plugin": "noir"})
    th = d.get("theme") or {}
    check("切回玄夜", th.get("plugin") == "noir" and th.get("vars", {}).get("--bg") == NOIR_BG, th.get("vars", {}).get("--bg"))
    code, _, portal = admin.fetch("/portal")
    check("门户回深色", root_vars(portal).get("bg", "").strip() == NOIR_BG, root_vars(portal).get("bg"))

    print("[3] 主色微调照旧")
    code, d = admin.req("PATCH", "/api/settings", {"theme_accent": "#3b5bdb"})
    th = d.get("theme") or {}
    check("PATCH 主色生效", th.get("accent") == "#3b5bdb" and th.get("rgb") == "59,91,219", th.get("accent"))
    check("custom 标记", th.get("custom") is True, th.get("custom"))
    check("soft 是 rgba 派生", str(th.get("soft")).startswith("rgba(59,91,219,"), th.get("soft"))
    # 极浅的主色：深色画布上要被提亮
    code, d = admin.req("PATCH", "/api/settings", {"theme_accent": "#1f2328"})
    got = (d.get("theme") or {}).get("accent") or ""
    code2, _, portal = admin.fetch("/portal")
    v = root_vars(portal)
    check("近黑主色在深底被提亮", got != "#1f2328" and v.get("brand", "").strip() == got, [got, v.get("brand")])

    print("[4] 示例插件：安装 → 启用 → 卸载")
    code, d = admin.req("POST", "/api/settings/themes/install", {"source": "example"})
    check("示例安装成功", code == 200 and (d.get("plugin") or {}).get("id") == "aurora-example", d)
    meta2 = admin.req("GET", "/api/meta")[1].get("theme", {})
    check("清单里出现示例", "aurora-example" in [p["id"] for p in meta2.get("plugins", [])])
    check("示例是安装版", next((p for p in meta2["plugins"] if p["id"] == "aurora-example"), {}).get("builtin") is False)

    code, d = admin.req("PATCH", "/api/settings", {"theme_plugin": "aurora-example"})
    th = d.get("theme") or {}
    check("启用示例主题", th.get("plugin") == "aurora-example", th.get("plugin"))
    check("示例画布生效", th.get("vars", {}).get("--bg") == "#0d1021", th.get("vars", {}).get("--bg"))
    code, _, portal = admin.fetch("/portal")
    check("门户吃到示例画布", root_vars(portal).get("bg", "").strip() == "#0d1021", root_vars(portal).get("bg"))

    code, d = admin.req("DELETE", "/api/settings/themes/aurora-example")
    check("卸载成功", code == 200, d)
    meta3 = admin.req("GET", "/api/meta")[1].get("theme", {})
    check("清单里示例消失", "aurora-example" not in [p["id"] for p in meta3.get("plugins", [])])
    check("卸载当前主题回默认", meta3.get("plugin") == "noir", meta3.get("plugin"))

    code, d = admin.req("DELETE", "/api/settings/themes/noir")
    check("内置不可卸载", code == 422, code)
    code, d = admin.req("DELETE", "/api/settings/themes/no-such")
    check("卸载不存在 → 422", code == 422, code)
    code, d = admin.req("PATCH", "/api/settings", {"theme_plugin": "no-such"})
    check("启用不存在 → 422", code == 422, code)

    print("[5] 商店输入守卫（不连真实仓库）")
    code, d = admin.req("POST", "/api/settings/themes/preview", {"repo": ""})
    check("空仓库 → 422", code == 422, code)
    code, d = admin.req("POST", "/api/settings/themes/preview", {"repo": "不是仓库的输入!!"})
    # 垃圾输入走 200 + ok:false 的统一通道，错误话术要能看懂
    check("垃圾输入 → ok:false 且话能看懂",
          d.get("ok") is False and "仓库" in str(d.get("error", "")), d)
    anon = Client(args.url)
    code, _ = anon.req("POST", "/api/settings/themes/preview", {"repo": "a/b"})
    check("未登录不能逛商店", code == 401, code)

    print("[6] 还原")
    code, d = admin.req("PATCH", "/api/settings", {"theme_plugin": orig_plugin, "theme_accent": orig_accent})
    check("主题与主色已还原", (d.get("theme") or {}).get("plugin") == orig_plugin
          and (d.get("theme") or {}).get("raw") == orig_accent, d.get("theme", {}).get("plugin"))

    code, _ = admin.req("DELETE", f"/api/projects/{slug}")
    check("临时项目已清理", code == 200)

    print(f"\n{len(PASS)}/{len(PASS) + len(FAIL)} 通过")
    if FAIL:
        print("失败：")
        for f in FAIL:
            print("  -", f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
