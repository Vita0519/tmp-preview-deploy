"""操作日志查询（v2.5.0，v2.5.1 加分页 / 关键字 / 时间范围 / 统计）。

成员只能看到自己账号产生的、或发生在自己项目上的事件；管理员看全部。
两种翻页：
- page + page_size：返回 total，给日志页的页码分页用；
- before 游标：老接口，agentctl 在用，保持不变。
"""
import json
import time

from fastapi import APIRouter, Depends, Query

from ..db import db
from ..security import current_user

router = APIRouter(prefix="/api", tags=["events"])


def _row(r) -> dict:
    diff = None
    if r["diff"]:
        try:
            diff = json.loads(r["diff"])
        except ValueError:
            diff = None
    return {
        "id": r["id"],
        "at": r["at"],
        "action": r["action"],
        "actor": r["username"] or ("系统" if r["user_id"] is None else f"#{r['user_id']}"),
        "actor_label": r["key_label"] or "",
        "slug": r["slug"],
        # 项目当前（而不是当时）的 slug：项目改过名之后，老日志也能点到正确地址。
        # 项目已删则为 None，前端据此把「查看相关对象」换成「项目已删除」。
        "project_id": r["project_id"],
        "live_slug": r["live_slug"],
        "title": r["title"],
        "detail": r["detail"],
        "diff": diff,
    }


@router.get("/events")
def list_events(
    since: int | None = Query(None, description="毫秒时间戳，只要这之后的"),
    until: int | None = Query(None, description="毫秒时间戳，只要这之前的"),
    before: int | None = Query(None, description="翻页游标：只要 id 小于它的"),
    slug: str | None = None,
    action: str | None = None,
    actor: str | None = None,
    q: str | None = Query(None, max_length=100, description="关键字：名称 / slug / 操作人 / 详情"),
    page: int | None = Query(None, ge=1, le=10000),
    page_size: int = Query(20, ge=5, le=100),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(current_user),
):
    scope, sargs = [], []
    if user["role"] != "admin":
        scope.append("(e.user_id=? OR e.project_id IN (SELECT id FROM projects WHERE owner_id=?))")
        sargs += [user["id"], user["id"]]
    where, args = list(scope), list(sargs)
    if since:
        where.append("e.at>?")
        args.append(int(since))
    if until:
        where.append("e.at<?")
        args.append(int(until))
    if slug:
        where.append("e.slug=?")
        args.append(slug)
    if action:
        acts = [a.strip() for a in action.split(",") if a.strip()][:20]
        if acts:
            where.append(f"e.action IN ({','.join('?' * len(acts))})")
            args += acts
    if actor and user["role"] == "admin":
        if actor == "系统":
            where.append("e.user_id IS NULL")
        else:
            where.append("u.username=?")
            args.append(actor)
    if q and q.strip():
        kw = "%" + q.strip().replace("%", r"\%").replace("_", r"\_") + "%"
        # 项目改过名时，用新 slug 也应该搜得到旧日志，所以快照和现名一起匹配
        where.append(
            "(e.slug LIKE ? ESCAPE '\\' OR p.slug LIKE ? ESCAPE '\\' OR e.title LIKE ? ESCAPE '\\' "
            "OR e.detail LIKE ? ESCAPE '\\' OR u.username LIKE ? ESCAPE '\\')"
        )
        args += [kw] * 5

    # LEFT JOIN projects：拿项目当前的 slug（p.slug），跟事件里的历史快照 e.slug 区分开。
    # 1:1 关联，不影响 COUNT。
    base = (
        "FROM events e LEFT JOIN users u ON u.id=e.user_id "
        "LEFT JOIN projects p ON p.id=e.project_id"
    )
    cond = (" WHERE " + " AND ".join(where)) if where else ""
    cols = (
        "SELECT e.id, e.at, e.user_id, e.action, e.detail, e.slug, e.title, e.diff, "
        "e.project_id, p.slug AS live_slug, "
        "u.username, u.key_label "
    )

    with db() as conn:
        if page is None:
            # 老的游标模式
            cw, ca = list(where), list(args)
            if before:
                cw.append("e.id<?")
                ca.append(int(before))
            c2 = (" WHERE " + " AND ".join(cw)) if cw else ""
            rows = conn.execute(f"{cols}{base}{c2} ORDER BY e.id DESC LIMIT ?", ca + [limit]).fetchall()
            items = [_row(r) for r in rows]
            return {"items": items, "next_before": items[-1]["id"] if len(items) == limit else None}

        total = conn.execute(f"SELECT COUNT(*) {base}{cond}", args).fetchone()[0]
        rows = conn.execute(
            f"{cols}{base}{cond} ORDER BY e.id DESC LIMIT ? OFFSET ?",
            args + [page_size, (page - 1) * page_size],
        ).fetchall()

        # 顶部统计：只受权限范围影响，不受筛选影响；「今天」按服务器本地时区零点
        lt = time.localtime()
        day0 = int(time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1)) * 1000)
        sw = " AND ".join(scope + ["e.at>=?"])
        sa = sargs + [day0]
        today = conn.execute(f"SELECT COUNT(*) {base} WHERE {sw}", sa).fetchone()[0]
        actors = conn.execute(
            f"SELECT COUNT(DISTINCT COALESCE(e.user_id, -1)) {base} WHERE {sw}", sa
        ).fetchone()[0]
        risky = conn.execute(
            f"SELECT COUNT(*) {base} WHERE {sw} AND e.action IN "
            "('delete','expire_delete','expire_block','restore','agent_delete')",
            sa,
        ).fetchone()[0]
        actor_opts = []
        if user["role"] == "admin":
            actor_opts = [
                r[0] for r in conn.execute(
                    "SELECT DISTINCT u.username FROM events e JOIN users u ON u.id=e.user_id "
                    "ORDER BY u.username LIMIT 100"
                ).fetchall()
            ]

    return {
        "items": [_row(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "stats": {"today": today, "actors_today": actors, "risky_today": risky},
        "actors": actor_opts,
    }
