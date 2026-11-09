"""许可证与署名校验。

AGPL-3.0 的「署名」不是写个文件就完了，得真的出现在用户看得见的地方：
文件层（LICENSE / NOTICE / README / SKILL / package.json / Dockerfile / 脚本头）
+ 运行时（门户页脚、登录页、设置页「关于」）。

任何一处被删掉都算违约，所以这里逐项钉死。
"""
import json
import os
import re

from playwright.sync_api import sync_playwright

BASE = os.environ.get("PV_BASE", "http://127.0.0.1:8000")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USER = os.environ.get("PV_USER", "admin")
PASSWORD = os.environ.get("PV_PASS", "admin123")
OUT = os.environ.get("PV_SHOTS", "C:/tmp/shots")
os.makedirs(OUT, exist_ok=True)

REPO_URL = "https://github.com/Vita0519/tmp-preview-deploy"
AUTHOR = "Vita0519"

ok = fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  [ok] {name}")
    else:
        fail += 1
        print(f"  [!!] {name}  {extra}")


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


# ---------------- 一、文件层 ----------------
print("== 文件层 ==")

lic = read("LICENSE")
check("LICENSE 存在且是 AGPL 正文", "GNU AFFERO GENERAL PUBLIC LICENSE" in lic, lic[:60])
check("LICENSE 是第 3 版", "Version 3, 19 November 2007" in lic)
check("LICENSE 条款完整（有结尾）", "END OF TERMS AND CONDITIONS" in lic)
check("LICENSE 没被截断（正文 ≥600 行）", len(lic.splitlines()) >= 600, len(lic.splitlines()))
check("LICENSE 不是别的许可证", "MIT License" not in lic and "Apache License" not in lic)

notice = read("NOTICE")
check("NOTICE 有版权声明", "Copyright (C) 2026" in notice and AUTHOR in notice, notice[:80])
check("NOTICE 指向仓库", REPO_URL in notice)
check("NOTICE 引用 §7(b) 附加条款", "7(b)" in notice)
check("NOTICE 明确要求保留署名", "保留署名" in notice or "署名" in notice)
check("NOTICE 说明 AGPL 第 13 条（网络服务给源码）", "13" in notice and "源码" in notice)

readme = read("README.md")
check("README 声明 AGPL-3.0-only", "AGPL-3.0-only" in readme)
check("README 链接到 LICENSE", "](LICENSE)" in readme)
check("README 链接到 NOTICE", "](NOTICE)" in readme)
check("README 写了署名不能删", "Powered by tmp-preview" in readme and "署名" in readme)
check("README 提到商业授权", "书面" in readme and "授权" in readme)

skill_root = read("SKILL.md")
check("根 SKILL 有许可小节", "许可与署名" in skill_root and "AGPL-3.0-only" in skill_root)
agent_skill = read("skills/tmp-preview-agent/SKILL.md")
check(
    "Agent 技能包有许可小节",
    "许可与署名" in agent_skill and "AGPL-3.0-only" in agent_skill,
)
check(
    "Agent 技能包警告别删署名",
    "页脚" in agent_skill and ("署名" in agent_skill),
)
agent_notice = read("skills/tmp-preview-agent/NOTICE")
check(
    "技能包自带 NOTICE（单独拷走也不丢署名）",
    "Copyright (C) 2026" in agent_notice and "AGPL-3.0" in agent_notice,
    agent_notice[:60],
)

pkg = json.loads(read("frontend/package.json"))
check("package.json 标了 license", pkg.get("license") == "AGPL-3.0-only", pkg.get("license"))

docker = read("Dockerfile")
check(
    "Dockerfile 带 OCI 许可标注",
    'org.opencontainers.image.licenses="AGPL-3.0-only"' in docker,
)
check("Dockerfile 带源码地址", "org.opencontainers.image.source" in docker)

for rel in ("cli/agentctl.py", "skills/tmp-preview-agent/scripts/agentctl.py"):
    body = read(rel)
    check(
        f"{rel} 头部署名",
        "AGPL-3.0" in body[:1200] and AUTHOR in body[:1200],
        body[:200].replace("\n", " "),
    )

fe_main = read("frontend/src/main.js")
check("前端入口带许可头", "AGPL-3.0" in fe_main[:400])
be_main = read("backend/app/main.py")
check("后端入口带许可头", "AGPL-3.0" in be_main[:400])

# 有没有人把署名做成「可以关掉的开关」——许可要求它常驻，不能是配置项
cfg = read("backend/app/config.py")
check(
    "署名不是可选开关（没有开关式环境变量）",
    not re.search(r"SHOW_?CREDIT|HIDE_?FOOTER|BRANDING_?OFF", cfg),
)

# ---------------- 二、运行时 ----------------
print("\n== 运行时 ==")


def api(path):
    import urllib.request

    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with op.open(BASE + path, timeout=20) as r:
        return json.loads(r.read())


meta = api("/api/meta")
proj = meta.get("project") or {}
print("  meta.project:", proj)
check("meta 下发项目名", proj.get("name") == "tmp-preview", proj)
check("meta 下发仓库地址", proj.get("url") == REPO_URL, proj)
check("meta 下发许可", proj.get("license") == "AGPL-3.0-only", proj)
check("meta 下发作者", AUTHOR in (proj.get("author") or ""), proj)

import urllib.request

op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
with op.open(BASE + "/portal", timeout=20) as r:
    portal = r.read().decode("utf-8")
check("门户页脚有署名链接", 'class="flink credit"' in portal)
check("门户署名指向仓库", f'href="{REPO_URL}"' in portal, "href 不对")
check("门户署名文案是 Powered by", "Powered by tmp-preview" in portal)
check("门户署名带 title 说明许可", "AGPL-3.0-only" in portal)

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
    pg = ctx.new_page()

    # 登录页署名
    pg.goto(BASE + "/login", wait_until="networkidle")
    pg.wait_for_timeout(600)
    credit = pg.locator(".login-card .credit")
    check("登录页有署名", credit.count() == 1, credit.count())
    if credit.count():
        txt = credit.inner_text().strip()
        print("  登录页署名:", txt)
        check("登录页署名含项目名与许可", "tmp-preview" in txt and "AGPL" in txt, txt)
        box = credit.bounding_box()
        check("登录页署名真的可见（有尺寸）", box and box["width"] > 40 and box["height"] > 8, box)
        check("登录页署名指到仓库", credit.get_attribute("href") == REPO_URL)
    pg.screenshot(path=f"{OUT}/license-login.png")

    # 登录 → 设置页「关于 / 许可」
    pg.fill('input[autocomplete="username"]', USER)
    pg.fill('input[type="password"]', PASSWORD)
    pg.click('button[type="submit"]')
    pg.wait_for_url(lambda u: "/login" not in u, timeout=15000)
    pg.goto(BASE + "/settings", wait_until="networkidle")
    pg.wait_for_timeout(1200)

    panel = pg.locator("#about")
    check("设置页有「关于 / 许可」面板", panel.count() == 1, panel.count())
    check("侧栏导航里有关于入口", pg.locator(".setnav a", has_text="关于").count() >= 1)
    if panel.count():
        body = panel.inner_text()
        print("  关于面板:", body.replace("\n", " | ")[:120])
        check("关于面板写明许可", "AGPL-3.0-only" in body, body[:80])
        check("关于面板写明作者", AUTHOR in body)
        check("关于面板给出源码地址", REPO_URL in body)
        links = panel.locator("a")
        hrefs = [links.nth(i).get_attribute("href") for i in range(links.count())]
        check("关于面板能点到仓库", REPO_URL in hrefs, hrefs)
        check(
            "关于面板能点到许可证全文",
            any("gnu.org/licenses/agpl" in (h or "") for h in hrefs),
            hrefs,
        )
    pg.screenshot(path=f"{OUT}/license-settings.png", full_page=False)

    # 窄屏：门户页脚署名不能被挤掉
    narrow = ctx.new_page()
    narrow.set_viewport_size({"width": 420, "height": 800})
    narrow.goto(BASE + "/portal", wait_until="networkidle")
    narrow.wait_for_timeout(500)
    c2 = narrow.locator(".flink.credit").first
    box2 = c2.bounding_box() if c2.count() else None
    print("  窄屏署名 box:", box2)
    check("窄屏下署名仍在页面上", bool(box2), box2)
    check(
        "窄屏下署名没被裁掉（宽度够、在视口内）",
        bool(box2) and box2["width"] > 60 and 0 <= box2["x"] and box2["x"] + box2["width"] <= 430,
        box2,
    )
    narrow.screenshot(path=f"{OUT}/license-portal-narrow.png", full_page=False)

    b.close()

print(f"\n{ok} 通过 / {fail} 失败")
