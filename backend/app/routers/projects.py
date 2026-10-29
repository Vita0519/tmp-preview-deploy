"""项目相关 API：列表（筛选/排序/分面）、上传、改属性、删除、批量操作。"""
import os
import re
import shutil
import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from .. import config, storage, views
from ..db import db, log_event, set_tags, tx
from ..security import current_user, now_ms
from ..serializers import PROJECT_SELECT, project_dict

router = APIRouter(prefix="/api", tags=["projects"])

SORT_FIELDS = {
    "views": "p.views",
    "created_at": "p.created_at",
    "updated_at": "p.updated_at",
    "expires_at": "p.expires_at",
    "title": "p.title",
    "size_bytes": "p.size_bytes",
    "downloads": "p.downloads",
    "last_viewed_at": "p.last_viewed_at",
}

KINDS = {"static", "zip", "link"}
VISIBILITY = {"portal", "link", "private"}
EXPIRE_ACTIONS = {"block", "delete"}


def origin_of(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}".rstrip("/")


def _scope_clause(user: dict) -> tuple[str, list]:
    if user["role"] == "admin":
        return "1=1", []
    return "p.owner_id = ?", [user["id"]]


def _parse_tags(raw) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, (list, tuple)):
        parts = [str(x) for x in raw]
    else:
        parts = re.split(r"[,，]", str(raw))
    out: list[str] = []
    for p in parts:
        p = p.strip()[:24]
        if p and p not in out:
            out.append(p)
    return out[:12]


def _hours_to_expiry(hours) -> int | None:
    try:
        h = float(hours)
    except (TypeError, ValueError):
        return None
    if h <= 0:
        return None
    return now_ms() + int(h * 3600_000)


def can_edit(user: dict, row) -> bool:
    return user["role"] == "admin" or row["owner_id"] == user["id"]


def fetch_project(slug: str, user: dict):
    with db() as conn:
        row = conn.execute(PROJECT_SELECT + " WHERE p.slug = ?", (slug,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not can_edit(user, row):
        raise HTTPException(status_code=403, detail="无权操作该项目")
    return row


@router.get("/projects")
def list_projects(
    request: Request,
    q: str = "",
    agent: str = "",
    tag: list[str] | None = None,
    kind: str = "",
    status: str = "online",
    visibility: str = "",
    expiring_hours: float = 0,
    sort: str = "updated_at",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
    user: dict = Depends(current_user),
):
    now = now_ms()
    scope_sql, scope_args = _scope_clause(user)
    where = [scope_sql]
    args: list = list(scope_args)

    if q.strip():
        like = "%" + q.strip().replace("%", "").replace("_", "") + "%"
        where.append("(p.title LIKE ? OR p.description LIKE ? OR p.slug LIKE ?)")
        args += [like, like, like]

    if agent and user["role"] == "admin":
        where.append("u.username = ?")
        args.append(agent)

    if kind and kind in KINDS:
        where.append("p.kind = ?")
        args.append(kind)

    if visibility and visibility in VISIBILITY:
        where.append("p.visibility = ?")
        args.append(visibility)

    tag_names = [t for t in (tag or []) if not t.startswith("kind:")]
    if tag_names:
        marks = ",".join("?" * len(tag_names))
        where.append(
            f"EXISTS (SELECT 1 FROM project_tags pt JOIN tags t ON t.id=pt.tag_id "
            f"WHERE pt.project_id=p.id AND t.name IN ({marks}))"
        )
        args += tag_names

    expired_expr = "(p.status='expired' OR (p.expires_at IS NOT NULL AND p.expires_at<=?))"
    if status == "online":
        where.append("p.status='active' AND (p.expires_at IS NULL OR p.expires_at>?)")
        args.append(now)
    elif status == "expired":
        where.append(expired_expr)
        args.append(now)
    elif status == "permanent":
        where.append("p.status='active' AND p.expires_at IS NULL")
    elif status == "deleted":
        where.append("p.status='deleted'")
    else:
        where.append("p.status<>'deleted'")

    if expiring_hours and expiring_hours > 0:
        where.append("p.expires_at IS NOT NULL AND p.expires_at <= ? AND p.expires_at > ?")
        args += [now + int(expiring_hours * 3600_000), now]

    where_sql = " AND ".join(where)
    col = SORT_FIELDS.get(sort, SORT_FIELDS["updated_at"])
    direction = "ASC" if str(order).lower() == "asc" else "DESC"
    limit = max(1, min(int(limit or 50), 500))
    offset = max(0, int(offset or 0))

    with db() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) c FROM projects p LEFT JOIN users u ON u.id=p.owner_id WHERE {where_sql}",
            args,
        ).fetchone()["c"]
        rows = conn.execute(
            f"{PROJECT_SELECT} WHERE {where_sql} ORDER BY {col} {direction}, p.id {direction} "
            f"LIMIT ? OFFSET ?",
            args + [limit, offset],
        ).fetchall()
        items = []
        for r in rows:
            tags = [x["name"] for x in conn.execute(
                "SELECT t.name FROM project_tags pt JOIN tags t ON t.id=pt.tag_id "
                "WHERE pt.project_id=? ORDER BY t.name", (r["id"],)
            ).fetchall()]
            items.append(project_dict(r, origin_of(request), tags))
        facets = _facets(conn, scope_sql, scope_args, now)
        stats = _stats(conn, scope_sql, scope_args, now)

    return JSONResponse({
        "items": items,
        "total": total,
        "server_now": now,
        "stats": stats,
        "facets": facets,
    })


def _facets(conn, scope_sql: str, scope_args: list, now: int) -> dict:
    agents = [
        {"username": r["username"], "display_name": r["display_name"] or r["username"], "count": r["c"]}
        for r in conn.execute(
            f"SELECT u.username, u.display_name, COUNT(*) c FROM projects p "
            f"JOIN users u ON u.id=p.owner_id WHERE {scope_sql} AND p.status<>'deleted' "
            f"GROUP BY u.id ORDER BY c DESC",
            scope_args,
        ).fetchall()
    ]
    tags = [
        {"name": r["name"], "count": r["c"]}
        for r in conn.execute(
            f"SELECT t.name, COUNT(*) c FROM project_tags pt "
            f"JOIN tags t ON t.id=pt.tag_id JOIN projects p ON p.id=pt.project_id "
            f"WHERE {scope_sql} AND p.status<>'deleted' GROUP BY t.id ORDER BY c DESC, t.name LIMIT 60",
            scope_args,
        ).fetchall()
    ]
    kinds = {
        r["kind"]: r["c"]
        for r in conn.execute(
            f"SELECT p.kind, COUNT(*) c FROM projects p WHERE {scope_sql} AND p.status<>'deleted' "
            f"GROUP BY p.kind",
            scope_args,
        ).fetchall()
    }
    return {"agents": agents, "tags": tags, "kinds": kinds}


def _stats(conn, scope_sql: str, scope_args: list, now: int) -> dict:
    row = conn.execute(
        f"SELECT COUNT(*) total, "
        f"SUM(CASE WHEN p.status='active' AND (p.expires_at IS NULL OR p.expires_at>?) THEN 1 ELSE 0 END) online, "
        f"SUM(CASE WHEN p.status='active' AND p.expires_at IS NOT NULL AND p.expires_at>? "
        f"         AND p.expires_at<=? THEN 1 ELSE 0 END) expiring, "
        f"SUM(p.views) views, SUM(p.downloads) downloads, SUM(p.size_bytes) size "
        f"FROM projects p WHERE {scope_sql} AND p.status<>'deleted'",
        [now, now, now + 86400_000] + scope_args,
    ).fetchone()
    today_views = conn.execute(
        f"SELECT COALESCE(SUM(d.count),0) c FROM daily_views d JOIN projects p ON p.id=d.project_id "
        f"WHERE d.day=? AND {scope_sql}",
        [views.today()] + scope_args,
    ).fetchone()["c"]
    return {
        "total": row["total"] or 0,
        "online": row["online"] or 0,
        "expiring_24h": row["expiring"] or 0,
        "views": row["views"] or 0,
        "views_today": today_views or 0,
        "downloads": row["downloads"] or 0,
        "size_bytes": row["size"] or 0,
    }


@router.get("/stats/trend")
def stats_trend(days: int = 14, user: dict = Depends(current_user)):
    scope_sql, scope_args = _scope_clause(user)
    days = max(3, min(days, 60))
    with db() as conn:
        rows = conn.execute(
            f"SELECT d.day, SUM(d.count) c FROM daily_views d JOIN projects p ON p.id=d.project_id "
            f"WHERE {scope_sql} GROUP BY d.day ORDER BY d.day DESC LIMIT ?",
            scope_args + [days],
        ).fetchall()
    data = [{"day": r["day"], "count": r["c"]} for r in rows][::-1]
    return {"items": data}


@router.get("/projects/{slug}")
def get_project(slug: str, request: Request, user: dict = Depends(current_user)):
    row = fetch_project(slug, user)
    with db() as conn:
        tags = [x["name"] for x in conn.execute(
            "SELECT t.name FROM project_tags pt JOIN tags t ON t.id=pt.tag_id "
            "WHERE pt.project_id=? ORDER BY t.name", (row["id"],)
        ).fetchall()]
        daily = [
            {"day": r["day"], "count": r["c"]}
            for r in conn.execute(
                "SELECT day, count c FROM daily_views WHERE project_id=? ORDER BY day DESC LIMIT 14",
                (row["id"],),
            ).fetchall()
        ][::-1]
        events = [
            {"at": r["at"], "action": r["action"], "detail": r["detail"]}
            for r in conn.execute(
                "SELECT at, action, detail FROM events WHERE project_id=? ORDER BY at DESC LIMIT 20",
                (row["id"],),
            ).fetchall()
        ]
        counts = conn.execute(
            "SELECT COUNT(*) c FROM tags"
        ).fetchone()
    item = project_dict(row, origin_of(request), tags)
    item["files"] = storage.file_list(slug)
    item["daily_views"] = daily
    item["events"] = events
    item["tag_count"] = counts["c"]
    return item


async def _save_upload(upload, dest: Path) -> int:
    size = 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as fh:
        while True:
            chunk = await upload.read(1024 * 512)
            if not chunk:
                break
            fh.write(chunk)
            size += len(chunk)
    return size


@router.post("/projects")
async def upload_project(request: Request, user: dict = Depends(current_user)):
    form = await request.form()
    slug_in = str(form.get("slug") or "").strip()
    title = str(form.get("title") or "").strip()
    description = str(form.get("description") or "").strip()
    hours_raw = form.get("hours")
    forever = str(form.get("forever") or "").lower() in ("1", "true", "yes", "on")
    expire_action = str(form.get("expire_action") or "block")
    if expire_action not in EXPIRE_ACTIONS:
        expire_action = "block"
    allow_download = str(form.get("allow_download") or "").lower() in ("1", "true", "yes", "on")
    visibility = str(form.get("visibility") or "link")
    if visibility not in VISIBILITY:
        visibility = "link"
    tags = _parse_tags(form.get("tags"))
    owner_username = str(form.get("owner") or "").strip()

    files = [f for f in form.getlist("files") if getattr(f, "filename", "")]
    zip_up = form.get("zip")
    zip_up = zip_up if getattr(zip_up, "filename", "") else None
    if not files and not zip_up:
        raise HTTPException(status_code=400, detail="没有收到文件")

    slug = storage.slugify(slug_in or title or (files[0].filename if files else "project"))
    title = title or slug

    with db() as conn:
        existing = conn.execute("SELECT * FROM projects WHERE slug=?", (slug,)).fetchone()
        owner_id = user["id"]
        if user["role"] == "admin" and owner_username:
            urow = conn.execute("SELECT id FROM users WHERE username=?", (owner_username,)).fetchone()
            if not urow:
                raise HTTPException(status_code=400, detail=f"成员 {owner_username} 不存在")
            owner_id = urow["id"]
        if existing and not can_edit(user, existing):
            raise HTTPException(status_code=409, detail="该 slug 已被其他成员占用")

    # 已有项目：保留归属者
    if existing:
        owner_id = existing["owner_id"] or owner_id

    kind = "static" if files else "zip"
    file_count = 0
    total = 0
    entry = None
    if files:
        file_count, total, entry = await storage.write_uploads(slug, files)

    zip_name = None
    if zip_up:
        tmpdir = Path(tempfile.mkdtemp(prefix="pvzip-"))
        tmp = tmpdir / "upload.zip"
        try:
            zsize = await _save_upload(zip_up, tmp)
            storage.save_zip_file(slug, tmp)
            zip_name = zip_up.filename or f"{slug}.zip"
            total += zsize if not files else 0
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    limit_bytes = config.MAX_UPLOAD_MB * 1024 * 1024
    if total > limit_bytes:
        storage.remove_project_files(slug)
        raise HTTPException(status_code=413, detail=f"超过单项目上限 {config.MAX_UPLOAD_MB}MB")

    t = now_ms()
    if existing:
        if hours_raw not in (None, ""):
            expires_at = None if forever else _hours_to_expiry(hours_raw)
        elif forever:
            expires_at = None
        else:
            expires_at = existing["expires_at"]
    else:
        expires_at = None if forever else (_hours_to_expiry(hours_raw) if hours_raw not in (None, "") else now_ms() + int(config.DEFAULT_TTL_HOURS * 3600_000))

    if kind == "zip" and zip_up:
        allow_download = True

    with tx() as conn:
        if existing:
            conn.execute(
                "UPDATE projects SET title=?, description=?, kind=?, entry=?, file_count=?, size_bytes=?, "
                "has_zip=?, zip_name=?, visibility=?, allow_download=?, expire_action=?, expires_at=?, "
                "status='active', updated_at=? WHERE id=?",
                (
                    title, description, kind, entry, file_count, total,
                    1 if zip_up else 0, zip_name, visibility, 1 if allow_download else 0,
                    expire_action, expires_at, t, existing["id"],
                ),
            )
            pid = existing["id"]
        else:
            cur = conn.execute(
                "INSERT INTO projects(slug, title, description, owner_id, kind, entry, file_count, size_bytes, "
                "has_zip, zip_name, visibility, allow_download, expire_action, expires_at, status, "
                "created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,'active',?,?)",
                (
                    slug, title, description, owner_id, kind, entry, file_count, total,
                    1 if zip_up else 0, zip_name, visibility, 1 if allow_download else 0,
                    expire_action, expires_at, t, t,
                ),
            )
            pid = cur.lastrowid
        set_tags(conn, pid, tags)

    log_event("upload" if not existing else "replace", user["id"], pid, f"{slug} {file_count} files")
    with db() as conn:
        row = conn.execute(PROJECT_SELECT + " WHERE p.id=?", (pid,)).fetchone()
        tag_list = [x["name"] for x in conn.execute(
            "SELECT t.name FROM project_tags pt JOIN tags t ON t.id=pt.tag_id WHERE pt.project_id=?",
            (pid,),
        ).fetchall()]
    return project_dict(row, origin_of(request), tag_list)


@router.post("/projects/link")
async def create_link(request: Request, user: dict = Depends(current_user)):
    body = await request.json()
    url = str(body.get("link_url") or "").strip()
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url.lstrip("/")
    if not re.match(r"^https?://[^\s]+$", url, re.I):
        raise HTTPException(status_code=400, detail="链接不合法")
    title = str(body.get("title") or "").strip() or url
    slug = storage.slugify(body.get("slug") or title)
    hours = body.get("hours")
    expires_at = None if body.get("forever") else (_hours_to_expiry(hours) if hours else now_ms() + int(config.DEFAULT_TTL_HOURS * 3600_000))
    t = now_ms()
    visibility = body.get("visibility") if body.get("visibility") in VISIBILITY else "link"
    with tx() as conn:
        if conn.execute("SELECT 1 FROM projects WHERE slug=?", (slug,)).fetchone():
            raise HTTPException(status_code=409, detail="slug 已存在")
        cur = conn.execute(
            "INSERT INTO projects(slug, title, description, owner_id, kind, link_url, visibility, "
            "expire_action, expires_at, status, created_at, updated_at) VALUES(?,?,?,?,'link',?,?,?,?,'active',?,?)",
            (slug, title, str(body.get("description") or ""), user["id"], url, visibility,
             "block", expires_at, t, t),
        )
        pid = cur.lastrowid
        set_tags(conn, pid, _parse_tags(body.get("tags")))
    log_event("link", user["id"], pid, slug)
    with db() as conn:
        row = conn.execute(PROJECT_SELECT + " WHERE p.id=?", (pid,)).fetchone()
    return project_dict(row, origin_of(request), _parse_tags(body.get("tags")))


@router.patch("/projects/{slug}")
async def patch_project(slug: str, request: Request, user: dict = Depends(current_user)):
    row = fetch_project(slug, user)
    body = await request.json()
    sets: list[str] = []
    args: list = []
    tags = None

    if "title" in body:
        sets.append("title=?")
        args.append(str(body["title"]).strip()[:200] or row["title"])
    if "description" in body:
        sets.append("description=?")
        args.append(str(body["description"])[:1000])
    if "visibility" in body and body["visibility"] in VISIBILITY:
        sets.append("visibility=?")
        args.append(body["visibility"])
    if "allow_download" in body:
        sets.append("allow_download=?")
        args.append(1 if body["allow_download"] else 0)
    if "expire_action" in body and body["expire_action"] in EXPIRE_ACTIONS:
        sets.append("expire_action=?")
        args.append(body["expire_action"])
    if "tags" in body:
        tags = _parse_tags(body["tags"])

    if body.get("permanent"):
        sets.append("expires_at=NULL")
    elif "hours" in body and body["hours"] not in (None, ""):
        sets.append("expires_at=?")
        args.append(_hours_to_expiry(body["hours"]))
    elif "expires_at" in body:
        v = body["expires_at"]
        sets.append("expires_at=?")
        args.append(None if not v else int(v))

    if body.get("revive"):
        sets.append("status='active'")

    new_slug = str(body.get("slug") or "").strip()
    renaming = bool(new_slug) and new_slug != slug
    if renaming:
        new_slug = storage.slugify(new_slug)
        with db() as conn:
            if conn.execute("SELECT 1 FROM projects WHERE slug=?", (new_slug,)).fetchone():
                raise HTTPException(status_code=409, detail="新 slug 已被占用")
        sets.append("slug=?")
        args.append(new_slug)

    sets.append("updated_at=?")
    args.append(now_ms())
    args.append(row["id"])

    with tx() as conn:
        conn.execute(f"UPDATE projects SET {', '.join(sets)} WHERE id=?", args)
        if tags is not None:
            set_tags(conn, row["id"], tags)

    if renaming:
        try:
            storage.move_project_dir(slug, new_slug)
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"目录改名失败：{exc}") from exc

    log_event("patch", user["id"], row["id"], str(list(body.keys())))
    with db() as conn:
        fresh = conn.execute(PROJECT_SELECT + " WHERE p.id=?", (row["id"],)).fetchone()
        tag_list = [x["name"] for x in conn.execute(
            "SELECT t.name FROM project_tags pt JOIN tags t ON t.id=pt.tag_id WHERE pt.project_id=?",
            (row["id"],),
        ).fetchall()]
    return project_dict(fresh, origin_of(request), tag_list)


@router.delete("/projects/{slug}")
def delete_project(slug: str, user: dict = Depends(current_user)):
    row = fetch_project(slug, user)
    storage.remove_project_files(row["slug"])
    views.reset(row["id"])
    with db() as conn:
        conn.execute("DELETE FROM projects WHERE id=?", (row["id"],))
    log_event("delete", user["id"], row["id"], row["slug"])
    return {"ok": True, "slug": row["slug"]}


@router.post("/projects/bulk")
async def bulk_action(request: Request, user: dict = Depends(current_user)):
    body = await request.json()
    slugs = [str(s) for s in (body.get("slugs") or [])][:500]
    action = str(body.get("action") or "")
    if not slugs:
        raise HTTPException(status_code=400, detail="未选择项目")
    now = now_ms()
    done, skipped = 0, 0
    with db() as conn:
        rows = conn.execute(
            f"SELECT p.* FROM projects p WHERE p.slug IN ({','.join('?' * len(slugs))})", slugs
        ).fetchall()
    for row in rows:
        if not can_edit(user, row):
            skipped += 1
            continue
        if action == "delete":
            storage.remove_project_files(row["slug"])
            with db() as conn:
                conn.execute("DELETE FROM projects WHERE id=?", (row["id"],))
        elif action in ("expire", "block"):
            with db() as conn:
                conn.execute(
                    "UPDATE projects SET status='expired', expires_at=?, updated_at=? WHERE id=?",
                    (now, now, row["id"]),
                )
        elif action == "permanent":
            with db() as conn:
                conn.execute(
                    "UPDATE projects SET expires_at=NULL, status='active', updated_at=? WHERE id=?",
                    (now, row["id"]),
                )
        elif action == "extend":
            hours = float(body.get("hours") or 24)
            base = row["expires_at"] if row["expires_at"] and row["expires_at"] > now else now
            with db() as conn:
                conn.execute(
                    "UPDATE projects SET expires_at=?, status='active', updated_at=? WHERE id=?",
                    (base + int(hours * 3600_000), now, row["id"]),
                )
        elif action in ("allow_download", "deny_download"):
            with db() as conn:
                conn.execute(
                    "UPDATE projects SET allow_download=?, updated_at=? WHERE id=?",
                    (1 if action == "allow_download" else 0, now, row["id"]),
                )
        elif action == "visibility":
            v = body.get("visibility")
            if v in VISIBILITY:
                with db() as conn:
                    conn.execute("UPDATE projects SET visibility=?, updated_at=? WHERE id=?",
                                 (v, now, row["id"]))
        elif action == "tag_add":
            names = _parse_tags(body.get("tags"))
            with db() as conn:
                for n in names:
                    conn.execute("INSERT OR IGNORE INTO tags(name) VALUES(?)", (n,))
                    trow = conn.execute("SELECT id FROM tags WHERE name=?", (n,)).fetchone()
                    if trow:
                        conn.execute(
                            "INSERT OR IGNORE INTO project_tags(project_id, tag_id) VALUES(?,?)",
                            (row["id"], trow["id"]),
                        )
        else:
            raise HTTPException(status_code=400, detail="未知操作")
        done += 1
    log_event("bulk", user["id"], None, f"{action} x{done}")
    return {"ok": True, "done": done, "skipped": skipped}


@router.post("/projects/{slug}/reset-views")
def reset_views(slug: str, user: dict = Depends(current_user)):
    row = fetch_project(slug, user)
    views.reset(row["id"])
    with db() as conn:
        conn.execute("UPDATE projects SET views=0 WHERE id=?", (row["id"],))
        conn.execute("DELETE FROM daily_views WHERE project_id=?", (row["id"],))
    return {"ok": True, "views": 0}
