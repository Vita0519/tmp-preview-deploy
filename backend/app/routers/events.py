"""操作日志查询（v2.5.0）。

成员只能看到自己账号产生的、或发生在自己项目上的事件；管理员看全部。
单次最多 200 条，按时间倒序；用 before 游标翻页。
"""
import json

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
        "title": r["title"],
        "detail": r["detail"],
        "diff": diff,
    }


@router.get("/events")
def list_events(
    since: int | None = Query(None, description="毫秒时间戳，只要这之后的"),
    before: int | None = Query(None, description="翻页游标：只要 id 小于它的"),
    slug: str | None = None,
    action: str | None = None,
    actor: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(current_user),
):
    where, args = [], []
    if user["role"] != "admin":
        where.append("(e.user_id=? OR e.project_id IN (SELECT id FROM projects WHERE owner_id=?))")
        args += [user["id"], user["id"]]
    if since:
        where.append("e.at>?")
        args.append(int(since))
    if before:
        where.append("e.id<?")
        args.append(int(before))
    if slug:
        where.append("e.slug=?")
        args.append(slug)
    if action:
        acts = [a.strip() for a in action.split(",") if a.strip()][:20]
        if acts:
            where.append(f"e.action IN ({','.join('?' * len(acts))})")
            args += acts
    if actor and user["role"] == "admin":
        where.append("u.username=?")
        args.append(actor)
    sql = (
        "SELECT e.id, e.at, e.user_id, e.action, e.detail, e.slug, e.title, e.diff, "
        "u.username, u.key_label FROM events e LEFT JOIN users u ON u.id=e.user_id"
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY e.id DESC LIMIT ?"
    args.append(limit)
    with db() as conn:
        rows = conn.execute(sql, args).fetchall()
    items = [_row(r) for r in rows]
    return {
        "items": items,
        "next_before": items[-1]["id"] if len(items) == limit else None,
    }
