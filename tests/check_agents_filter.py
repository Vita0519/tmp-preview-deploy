"""成员管理的搜索 / 筛选 / 排序校验。
后端结果与页面显示逐项对拍，避免只测了 UI 没测查询。
"""
import os

from playwright.sync_api import sync_playwright

BASE = os.environ.get("PV_BASE", "http://127.0.0.1:8000")
USER = os.environ.get("PV_USER", "admin")
PASSWORD = os.environ.get("PV_PASS", "admin123")
OUT = os.environ.get("PV_SHOTS", "C:/tmp/shots")
os.makedirs(OUT, exist_ok=True)

ok = fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  [ok] {name}")
    else:
        fail += 1
        print(f"  [!!] {name}  {extra}")


def page_state(pg):
    return pg.evaluate(
        """() => {
      const trs = [...document.querySelectorAll('.panel.only-wide tbody tr')]
        .filter((tr) => !tr.querySelector('.skel'));
      const users = trs.map((tr) => (tr.querySelector('.pslug') || {}).textContent || '')
        .map((s) => s.trim().replace(/^@/, '')).filter(Boolean);
      const pager = document.querySelector('.pager');
      return {
        rows: trs.length,
        users,
        emptyText: (document.querySelector('.panel.only-wide td.dim') || {}).innerText || '',
        head: (document.querySelector('.topbar .sub') || {}).innerText.replace(/\\s+/g, ' ').trim(),
        info: pager ? pager.querySelector('span').innerText.replace(/\\s+/g, ' ').trim() : null,
        clearBtn: !!document.querySelector('.toolbar .btn.ghost'),
      };
    }"""
    )


def api(pg, qs=""):
    return pg.evaluate(
        """(qs) => fetch('/api/agents?' + qs).then((r) => r.json())""", qs
    )


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    ctx = b.new_context(viewport={"width": 1600, "height": 1100}, device_scale_factor=1)
    pg = ctx.new_page()
    pg.goto(BASE + "/", wait_until="networkidle")
    pg.fill('input[autocomplete="username"]', USER)
    pg.fill('input[type="password"]', PASSWORD)
    pg.click('button[type="submit"]')
    pg.wait_for_url(lambda u: "/login" not in u, timeout=15000)
    pg.goto(BASE + "/agents", wait_until="networkidle")
    pg.wait_for_timeout(900)

    base = api(pg, "limit=0")
    total = base["total"]
    all_names = [a["username"] for a in base["items"]]
    print(f"成员总数 {total}：{', '.join(all_names[:6])} …")

    # ---------- 1. 搜索 ----------
    target = all_names[1]
    pg.fill(".toolbar .search input", target)
    pg.wait_for_timeout(900)
    s = page_state(pg)
    print(f"搜「{target}」：{s['users']}")
    check("搜索命中且只出这个人", s["users"] == [target], s["users"])
    check("顶部显示「N 个匹配」", "匹配" in s["head"], s["head"])
    check("出现「清除筛选」按钮", s["clearBtn"] is True)

    # 搜一个必定搜不到的
    pg.fill(".toolbar .search input", "zzz_no_such_agent")
    pg.wait_for_timeout(900)
    s0 = page_state(pg)
    check("搜不到时给空状态提示", "没有匹配" in s0["emptyText"], s0["emptyText"])
    check("搜不到时一个成员都不显示（空状态那行不算人）", s0["users"] == [], s0["users"])
    pg.screenshot(path=f"{OUT}/agents-empty.png")

    # 按绑定 Agent 名搜（key_label）
    kv = next((a for a in base["items"] if a["key_label"] and a["key_label"] != a["username"]), None)
    if kv:
        pg.fill(".toolbar .search input", kv["key_label"])
        pg.wait_for_timeout(900)
        s1 = page_state(pg)
        check(f"按绑定 Agent「{kv['key_label']}」也能搜到", kv["username"] in s1["users"], s1["users"])

    pg.fill(".toolbar .search input", "")
    pg.wait_for_timeout(800)

    # ---------- 2. 角色筛选 ----------
    for role, label in (("admin", "全部角色"), ("viewer", "仅门户"), ("publisher", "可发布")):
        want = [a["username"] for a in base["items"] if a["role"] == role]
        pg.select_option(".toolbar select", role)  # 第 1 个下拉 = 角色
        pg.wait_for_timeout(850)
        got = page_state(pg)["users"]
        print(f"筛角色 {role}：{len(got)} 人（后端 {len(want)} 人）")
        check(f"角色筛选 {role} 与后端一致", sorted(got) == sorted(want), f"{got} vs {want}")

    pg.select_option(".toolbar select", "")
    pg.wait_for_timeout(700)

    # ---------- 3. 状态筛选 ----------
    disabled = [a["username"] for a in base["items"] if not a["active"]]
    sel_status = ".toolbar select >> nth=1"
    pg.select_option(sel_status, "disabled")
    pg.wait_for_timeout(800)
    got = page_state(pg)["users"]
    check("状态筛「已停用」与后端一致", sorted(got) == sorted(disabled), f"{got} vs {disabled}")
    pg.select_option(sel_status, "active")
    pg.wait_for_timeout(800)
    got = page_state(pg)["users"]
    enabled = [a["username"] for a in base["items"] if a["active"]]
    # 只比当前页（默认 20/页），后端那次是 limit=0 的全量
    check("状态筛「已启用」与后端一致", got == enabled[: len(got)], f"{len(got)} vs {len(enabled)} 人")
    pg.select_option(sel_status, "")
    pg.wait_for_timeout(700)

    # ---------- 4. 排序 ----------
    sort_sel = ".toolbar select >> nth=2"
    cases = [
        ("views", "desc", "访问次数降序"),
        ("views", "asc", "访问次数升序"),
        ("created_at", "asc", "创建时间升序"),
        ("created_at", "desc", "创建时间降序"),
        ("last_login_at", "desc", "最近登录降序"),
        ("projects", "desc", "项目数降序"),
    ]
    for field, direction, label in cases:
        pg.select_option(sort_sel, field)
        pg.wait_for_timeout(300)
        cur = pg.locator(".toolbar .btn.icon").inner_text().strip()
        for _ in range(2):  # 先把方向拨到 desc
            if pg.locator(".toolbar .btn.icon").inner_text().strip() == "↓":
                break
            pg.click(".toolbar .btn.icon")
            pg.wait_for_timeout(200)
        if direction == "asc":
            pg.click(".toolbar .btn.icon")
            pg.wait_for_timeout(250)
        pg.wait_for_timeout(750)
        want = [a["username"] for a in api(pg, f"limit=0&sort={field}&order={direction}")["items"]]
        got = page_state(pg)["users"]
        print(f"{label}：前 3 = {got[:3]}")
        check(f"{label} 顺序与后端一致", got[:20] == want[:20], f"{got[:3]} vs {want[:3]}")

    # ---------- 5. 排序 + 筛选叠加 ----------
    pg.select_option(".toolbar select", "publisher")
    pg.wait_for_timeout(800)
    want = [a["username"] for a in api(pg, "limit=0&role=publisher&sort=projects&order=desc")["items"]]
    got = page_state(pg)["users"]
    check("筛选 + 排序能叠加", got == want[: len(got)], f"{got[:3]} vs {want[:3]}")
    pg.screenshot(path=f"{OUT}/agents-filtered.png")

    # ---------- 6. 清除筛选 ----------
    pg.click(".toolbar .btn.ghost")
    pg.wait_for_timeout(900)
    s2 = page_state(pg)
    check("清除筛选后恢复第一页默认顺序", s2["rows"] == min(20, total), s2["rows"])
    check("清除后顶部回到「N 个账号」", "账号" in s2["head"], s2["head"])
    check("清除后按钮自己消失", s2["clearBtn"] is False)

    print(f"\n{ok} 通过 / {fail} 失败")
    b.close()
