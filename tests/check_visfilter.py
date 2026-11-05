"""可见性快筛的语义校验：
- 工具栏「可见性」下拉 = 在当前收藏夹范围内过滤，不换范围
- 侧栏三档 = 跳出收藏夹，看全站这一档
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


VIS_SEL = '.toolbar select:has(option[value="portal"])'


def state(pg):
    return pg.evaluate(
        """(sel) => {
      const visSel = document.querySelector(sel);
      const rows = document.querySelectorAll('tbody tr').length;
      // 只取文字里的最后一段数字，避开「⋯」等噪声
      const onRows = [...document.querySelectorAll('.rail .railrow.on')]
        .map((r) => r.innerText.replace(/\\s+/g, ' ').trim());
      return {
        vis: visSel.value,
        visLabel: visSel.options[visSel.selectedIndex].textContent.trim(),
        rows,
        onRows,
      };
    }""",
        VIS_SEL,
    )


def pick_rail(pg, text):
    pg.locator(".rail .railrow", has_text=text).first.click()
    pg.wait_for_timeout(750)


def pick_kid(pg, text):
    """子收藏夹：父级没展开就先展开（已展开时再点会收起，所以要判一下）"""
    caret = pg.locator('.rail .railrow:has-text("书签栏") .caret').first
    if "open" not in (caret.get_attribute("class") or ""):
        caret.click()
        pg.wait_for_timeout(400)
    pg.locator(".rail .railrow.kid", has_text=text).first.click()
    pg.wait_for_timeout(750)


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    ctx = b.new_context(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
    pg = ctx.new_page()
    pg.goto(BASE + "/", wait_until="networkidle")
    pg.fill('input[autocomplete="username"]', USER)
    pg.fill('input[type="password"]', PASSWORD)
    pg.click('button[type="submit"]')
    pg.wait_for_url(lambda u: "/login" not in u, timeout=15000)
    pg.wait_for_timeout(800)

    # ---------- 基准 ----------
    pick_rail(pg, "全部项目")
    s0 = state(pg)
    print(f"基准：全部项目 {s0['rows']} 行 · 下拉='{s0['visLabel']}' · 高亮={s0['onRows']}")
    check("全部项目时下拉写「全部可见性」", s0["visLabel"] == "全部可见性", s0["visLabel"])

    # ---------- 1. 进子夹 power：范围明显更小，且各档都有数据 ----------
    pick_kid(pg, "power")
    s1 = state(pg)
    print(f"进 power：{s1['rows']} 行 · 下拉='{s1['visLabel']}' · 高亮={s1['onRows']}")
    check("夹内下拉文案变成「本夹全部可见性」", s1["visLabel"] == "本夹全部可见性", s1["visLabel"])
    check("侧栏只高亮 power 一行", len(s1["onRows"]) == 1 and "power" in s1["onRows"][0], s1["onRows"])
    check("子夹项目数明显少于全站", s1["rows"] < s0["rows"], f"{s1['rows']} vs {s0['rows']}")
    power_n = s1["rows"]

    # ---------- 2. 下拉在夹内筛「仅自己」：范围必须留在未归类 ----------
    pg.select_option(VIS_SEL, "portal")
    pg.wait_for_timeout(800)
    s2 = state(pg)
    print(f"夹内筛门户可见：{s2['rows']} 行 · 下拉='{s2['visLabel']}' · 高亮={s2['onRows']}")
    check("夹内筛可见性不跳出收藏夹（侧栏仍高亮 power）",
          len(s2["onRows"]) == 1 and "power" in s2["onRows"][0], s2["onRows"])
    check("筛完行数 < 未筛时的总数（说明真的在筛）", s2["rows"] < power_n, f"{s2['rows']} vs {power_n}")
    check("侧栏三档没有被点亮（它们代表跳全站）",
          not any("仅自己" in r for r in s2["onRows"]), s2["onRows"])
    pg.screenshot(path=f"{OUT}/vis-in-coll.png")

    # ---------- 3. 侧栏点「仅自己」：跳出，看全站 ----------
    pick_rail(pg, "仅自己")
    s3 = state(pg)
    print(f"侧栏点仅自己：{s3['rows']} 行 · 下拉='{s3['visLabel']}' · 高亮={s3['onRows']}")
    check("跳出收藏夹：侧栏高亮变成「仅自己」", any("仅自己" in r for r in s3["onRows"]), s3["onRows"])
    check("跳出后下拉不再带「本夹」前缀", not s3["visLabel"].startswith("本夹"), s3["visLabel"])
    check("跳出后看的是全站这一档，数量远多于夹内筛选结果",
          s3["rows"] > s2["rows"], f"{s3['rows']} vs {s2['rows']}")

    # ---------- 4. 夹内筛同一档后再点侧栏同一档：要跳出去，不是取消 ----------
    pick_kid(pg, "power")
    pg.select_option(VIS_SEL, "portal")
    pg.wait_for_timeout(700)
    pick_rail(pg, "仅自己")
    s4 = state(pg)
    print(f"夹内筛门户 → 点侧栏仅自己：{s4['rows']} 行 · 高亮={s4['onRows']}")
    check("夹内同档点侧栏 = 跳全站这一档（不是取消）",
          any("仅自己" in r for r in s4["onRows"]), s4["onRows"])
    check("结果与直接跳全站一致", s4["rows"] == s3["rows"], f"{s4['rows']} vs {s3['rows']}")

    # ---------- 5. 点「全部项目」复位 ----------
    pick_rail(pg, "全部项目")
    s5 = state(pg)
    check("全部项目清空可见性", s5["visLabel"] == "全部可见性", s5["visLabel"])
    check("全部项目行数 = 基准", s5["rows"] == s0["rows"], f"{s5['rows']} vs {s0['rows']}")

    print(f"\n{ok} 通过 / {fail} 失败")
    b.close()
