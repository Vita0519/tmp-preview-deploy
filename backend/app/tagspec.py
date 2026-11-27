"""标签规则：一处定义，上传 / 外链 / 改属性 / 批量打标签全部走这里。

为什么要立规矩：标签是自由输入，不设上限就会变成「前端 / 前端 / 前 端 / 前端开发 / 前端开发组」
这种一团乱麻——筛选条越堆越长，同一个意思分散在好几个标签里，最后没人愿意用。

规则（硬约束，超了直接 422，不静默截断——静默截断会让人以为加上了）：

| 项 | 值 | 理由 |
|---|---|---|
| 每个项目最多 | 6 个 | 门户卡片一行放得下，也逼着挑重点 |
| 单个标签长度 | 1–12 字 | 「数据可视化」够用，再长就该写进描述 |
| 允许字符 | 中英文、数字、`+ # . - _` | 不许空格，空格会让「前端 验收」变成一个怪标签 |
| 去重 | 归一化后去重、保序 | `Vue` / `vue` / `VUE` 是同一个 |
| 归一化 | 全角转半角、英文转小写 | 避免同一标签出现多个写法 |
| 全站标签池 | 300 个 | 池满只能复用已有标签；无引用的标签会被回收 |

`clean()` 只做纯字符串校验（不碰库），`set_tags()` 里再做一次池上限检查。
"""
from __future__ import annotations

import re
import unicodedata

# ---- 规则常量（前端通过 /api/settings 的 tags 字段拿到同一份） ----
MAX_TAGS = 6          # 每个项目最多几个标签（硬上限；设置页可往小调）
MAX_LEN = 12          # 单个标签最多几个字符（中文按 1 个算）
POOL_MAX = 300        # 全站不同标签总数上限
BAR_MAX = 40          # 门户标签条最多显示几个（0 = 全部，硬上限就是它）

# 分隔符：半角/全角逗号、顿号、分号、空白
SEP = re.compile(r"[,，、;；\s]+")
# 允许的字符：\w 在 Python 里已包含中文，再加几个工程上常用的符号
ALLOWED = re.compile(r"^[\w+#.\-]+$", re.UNICODE)


class TagError(ValueError):
    """标签不合规。由 main.py 统一转成 422，detail 直接给人看。"""


def normalize_name(raw: object) -> str:
    """全角转半角、去首尾空白、英文转小写。只做归一化，不校验。"""
    s = unicodedata.normalize("NFKC", str(raw or ""))
    return s.strip().lower()


def split(raw: object) -> list[str]:
    """把「前端, 验收 / v2」拆成 ['前端','验收','v2']；已经是列表就逐个归一化。"""
    if raw is None or raw == "":
        return []
    if isinstance(raw, (list, tuple, set)):
        parts = [str(x) for x in raw]
    else:
        parts = SEP.split(str(raw))
    return [p for p in (normalize_name(x) for x in parts) if p]


def why_bad(name: str) -> str | None:
    """单个标签不合规的原因；合规返回 None。"""
    if len(name) > MAX_LEN:
        return f"标签「{name}」太长了：最多 {MAX_LEN} 个字"
    if not ALLOWED.match(name):
        return f"标签「{name}」含有不允许的字符：只能中英文、数字和 + # . - _"
    return None


def clean(raw: object, *, limit: bool = True, max_tags: int | None = None) -> list[str]:
    """校验 + 归一化 + 去重，返回可以直接入库的标签列表。

    不合规抛 TagError（消息面向使用者，可直接展示）。
    `max_tags` 由调用方从设置里取（管理员可以调低到 1–6），不传就用默认 6。
    """
    cap = MAX_TAGS if max_tags is None else clamp_max_tags(max_tags)
    out: list[str] = []
    for name in split(raw):
        if name in out:
            continue
        bad = why_bad(name)
        if bad:
            raise TagError(bad)
        out.append(name)
    if limit and len(out) > cap:
        raise TagError(f"每个项目最多 {cap} 个标签，你填了 {len(out)} 个")
    return out


def clamp_max_tags(raw: object) -> int:
    """把设置里的值收进 1–MAX_TAGS；空值或垃圾值回落到默认。"""
    try:
        n = int(float(str(raw).strip()))
    except (TypeError, ValueError):
        return MAX_TAGS
    return max(1, min(MAX_TAGS, n))


def clamp_bar_limit(raw: object) -> int:
    """门户标签条显示数量：0（全部）或 4–BAR_MAX。"""
    try:
        n = int(float(str(raw).strip()))
    except (TypeError, ValueError):
        return 12
    if n <= 0:
        return 0
    return max(4, min(BAR_MAX, n))


def rules(max_per_project: int | None = None, bar_limit: int | None = None) -> dict:
    """给前端 / 文档用的规则说明。"""
    return {
        "max_per_project": MAX_TAGS if max_per_project is None else clamp_max_tags(max_per_project),
        "max_per_project_cap": MAX_TAGS,
        "max_len": MAX_LEN,
        "pool_max": POOL_MAX,
        "bar_limit": 12 if bar_limit is None else clamp_bar_limit(bar_limit),
        "bar_limit_max": BAR_MAX,
        "allowed": "中英文、数字与 + # . - _",
        "separators": ", ， 、 ; ； 和空格",
        "note": "全角自动转半角、英文统一小写，重名标签会合并",
    }


def normalize_rows(conn) -> dict:
    """把存量标签按新规则过一遍：归一化、合并重名、每项目截到 6 个、删掉没人用的。

    只在库刚建好、或首次升级到有标签规则的版本时跑一次（由 init_db 的开关位守着）。
    """
    stats = {"merged": 0, "dropped": 0, "trimmed": 0, "renamed": 0, "orphans": 0}
    rows = conn.execute(
        "SELECT pt.project_id, pt.tag_id, t.name FROM project_tags pt "
        "JOIN tags t ON t.id=pt.tag_id ORDER BY pt.project_id, pt.rowid"
    ).fetchall()

    # 项目 → 保序去重后的标签名
    by_project: dict[int, list[str]] = {}
    for r in rows:
        names = by_project.setdefault(r["project_id"], [])
        raw_name = r["name"]
        name = normalize_name(raw_name)[:MAX_LEN]
        if not name or not ALLOWED.match(name):
            stats["dropped"] += 1
            continue
        # 只差大小写 / 全角半角（3D vs 3d）也算要改：跨项目的同名标签不会在下面撞成
        # merged，光看 merged/dropped/trimmed 会漏掉它们，库里就一直是两种写法
        if name != raw_name:
            stats["renamed"] += 1
        if name in names:
            stats["merged"] += 1
            continue
        if len(names) >= MAX_TAGS:
            stats["trimmed"] += 1
            continue
        names.append(name)

    changed = stats["merged"] or stats["dropped"] or stats["trimmed"] or stats["renamed"]
    if not changed:
        return stats

    conn.execute("DELETE FROM project_tags")
    conn.execute("DELETE FROM tags")
    for pid, names in by_project.items():
        for name in names:
            conn.execute("INSERT OR IGNORE INTO tags(name) VALUES(?)", (name,))
            row = conn.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()
            if row:
                conn.execute(
                    "INSERT OR IGNORE INTO project_tags(project_id, tag_id) VALUES(?,?)",
                    (pid, row["id"]),
                )
    print(f"[migrate] 标签规范化：合并 {stats['merged']}、丢弃 {stats['dropped']}、"
          f"超出上限截掉 {stats['trimmed']}、统一写法 {stats['renamed']}", flush=True)
    return stats


def prune_orphans(conn) -> int:
    """删掉没有任何项目在用的标签，返回删了几个。"""
    cur = conn.execute(
        "DELETE FROM tags WHERE id NOT IN (SELECT tag_id FROM project_tags)"
    )
    return cur.rowcount or 0


def pool_usage(conn) -> dict:
    """当前标签池占用情况，给设置页展示。"""
    used = conn.execute("SELECT COUNT(*) AS n FROM tags").fetchone()["n"]
    orphans = conn.execute(
        "SELECT COUNT(*) AS n FROM tags WHERE id NOT IN (SELECT tag_id FROM project_tags)"
    ).fetchone()["n"]
    tagged = conn.execute(
        "SELECT COUNT(DISTINCT project_id) AS n FROM project_tags"
    ).fetchone()["n"]
    return {"used": used, "orphans": orphans, "tagged_projects": tagged, "pool_max": POOL_MAX}
