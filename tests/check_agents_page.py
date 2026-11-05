"""成员管理分页校验：页大小、翻页、边界、翻页不重不漏。"""
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


def snap(pg):
    return pg.evaluate(
        """() => {
      const trs = [...document.querySelectorAll('.panel.only-wide tbody tr')]
        .filter((tr) => !tr.querySelector('td.skel, .skel'));
      const users = trs.map((tr) => (tr.querySelector('.pslug') || {}).textContent || '')
        .map((s) => s.trim().replace(/^@/, '')).filter(Boolean);
      const pager = document.querySelector('.pager');
      const btns = pager ? [...pager.querySelectorAll('button')] : [];
      return {
        rows: trs.length,
        users,
        head: (document.querySelector('.topbar .sub') || {}).textContent || '',
        info: pager ? pager.querySelector('span').innerText.replace(/\\s+/g, ' ').trim() : null,
        prevDisabled: btns[0] ? btns[0].disabled : null,
        nextDisabled: btns[1] ? btns[1].disabled : null,
        sizeVal: pager ? Number(pager.querySelector('select').value) : null,
      };
    }"""
    )


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    ctx = b.new_context(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
    pg = ctx.new_page()
    pg.goto(BASE + "/", wait_until="networkidle")
    pg.fill('input[autocomplete="username"]', USER)
    pg.fill('input[type="password"]', PASSWORD)
    pg.click('button[type="submit"]')
    pg.wait_for_url(lambda u: "/login" not in u, timeout=15000)
    pg.wait_for_timeout(600)

    pg.goto(BASE + "/agents", wait_until="networkidle")
    pg.wait_for_timeout(900)
    pg.screenshot(path=f"{OUT}/agents-p1.png")

    total = pg.evaluate("() => fetch('/api/agents?limit=1').then(r=>r.json()).then(d=>d.total)")
    print(f"后端 total = {total}")

    s1 = snap(pg)
    print(f"第1页：{s1['rows']} 行 · 头='{s1['head'].strip()}' · {s1['info']}")
    check("顶部显示全量账号数（不是当页条数）", str(total) in s1["head"], s1["head"])
    check("默认每页 20", s1["sizeVal"] == 20, s1["sizeVal"])
    check("第 1 页满 20 条", s1["rows"] == min(20, total), s1["rows"])
    check("第 1 页「上一页」禁用", s1["prevDisabled"] is True, s1["prevDisabled"])
    check("分页文案含页码", "第 1 /" in (s1["info"] or ""), s1["info"])

    page1_users = s1["users"]

    # ---- 翻到最后一页 ----
    pg.click(".pager button:has-text('下一页')")
    pg.wait_for_timeout(900)
    s2 = snap(pg)
    print(f"第2页：{s2['rows']} 行 · {s2['info']}")
    check("第 2 页剩下 total-20 条", s2["rows"] == total - 20, f"{s2['rows']} vs {total-20}")
    check("最后一页「下一页」禁用", s2["nextDisabled"] is True, s2["nextDisabled"])
    check("第 2 页「上一页」可用", s2["prevDisabled"] is False, s2["prevDisabled"])
    pg.screenshot(path=f"{OUT}/agents-p2.png")

    all_users = page1_users + s2["users"]
    check("两页合起来不重不漏", len(all_users) == total and len(set(all_users)) == total,
          f"{len(all_users)} / 去重 {len(set(all_users))} / total {total}")

    # ---- 回上一页 ----
    pg.click(".pager button:has-text('上一页')")
    pg.wait_for_timeout(800)
    s3 = snap(pg)
    check("回到第 1 页顺序一致", s3["users"] == page1_users, f"{s3['users'][:3]} vs {page1_users[:3]}")

    # ---- 每页条数改成 50 ----
    pg.select_option(".pager select", "50")
    pg.wait_for_timeout(900)
    s4 = snap(pg)
    print(f"50/页：{s4['rows']} 行 · {s4['info']}")
    check("50/页时一次显示全部", s4["rows"] == total, f"{s4['rows']} vs {total}")
    check("50/页时只剩 1 页", s4["nextDisabled"] is True and s4["prevDisabled"] is True, s4)
    pg.screenshot(path=f"{OUT}/agents-50.png")

    # ---- 后端直查：offset 越界返回空 ----
    tail = pg.evaluate(
        """async () => {
      const d = await fetch('/api/agents?limit=20&offset=999').then((r) => r.json());
      const e = await fetch('/api/agents?limit=20&offset=-5').then((r) => r.json());
      return {empty: d.items.length, total: d.total, negOffset: e.offset, negLen: e.items.length};
    }"""
    )
    check("offset 越界返回空列表但 total 还在", tail["empty"] == 0 and tail["total"] == total, tail)
    check("负数 offset 归零，返回第一页", tail["negOffset"] == 0 and tail["negLen"] == min(20, total), tail)

    print(f"\n{ok} 通过 / {fail} 失败")
    b.close()
