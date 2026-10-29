"""访客侧：项目文件直出、zip 下载、预览外壳、门户列表。"""
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

from .. import config, pages, storage, views
from ..db import db, get_setting
from ..security import now_ms, resolve_user

router = APIRouter(tags=["public"])

NOINDEX = {"X-Robots-Tag": "noindex, nofollow"}


def _load(slug: str):
    with db() as conn:
        return conn.execute(
            "SELECT p.*, u.display_name AS owner_display_name, u.username AS owner_username "
            "FROM projects p LEFT JOIN users u ON u.id=p.owner_id WHERE p.slug=?",
            (slug,),
        ).fetchone()


def _public_state(row, user) -> tuple[bool, bool]:
    """返回 (可见, 已过期)。"""
    if not row or row["status"] == "deleted":
        return False, False
    expired = row["status"] == "expired" or (
        row["expires_at"] is not None and row["expires_at"] <= now_ms()
    )
    if row["visibility"] == "private":
        allowed = bool(user) and (
            user["role"] == "admin" or row["owner_id"] == user["id"]
        )
        if not allowed:
            return False, expired
    return True, expired


def _row_tags(row) -> list[str]:
    with db() as conn:
        return [
            r["name"]
            for r in conn.execute(
                "SELECT t.name FROM project_tags pt JOIN tags t ON t.id=pt.tag_id "
                "WHERE pt.project_id=? ORDER BY t.name",
                (row["id"],),
            ).fetchall()
        ]


def _dict(row, origin: str) -> dict:
    return {
        "slug": row["slug"],
        "title": row["title"],
        "description": row["description"],
        "kind": row["kind"],
        "entry": row["entry"],
        "file_count": row["file_count"],
        "size_bytes": row["size_bytes"],
        "allow_download": bool(row["allow_download"]),
        "expires_at": row["expires_at"],
        "expired": row["status"] == "expired"
        or (row["expires_at"] is not None and row["expires_at"] <= now_ms()),
        "views": row["views"],
        "tags": _row_tags(row),
        "owner": {"display_name": row["owner_display_name"] or row["owner_username"] or ""}
        if row["owner_username"]
        else None,
        "link_url": row["link_url"],
        "preview_url": f"{origin}/v/{row['slug']}",
    }


@router.get("/api/public/p/{slug}")
def public_info(slug: str, request: Request):
    row = _load(slug)
    user = resolve_user(request)
    visible, _expired = _public_state(row, user)
    if not visible:
        raise HTTPException(status_code=404, detail="项目不存在")
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    data = _dict(row, f"{proto}://{host}")
    data["server_now"] = now_ms()
    return data


def _serve_file(slug: str, rel: str, request: Request):
    row = _load(slug)
    user = resolve_user(request)
    visible, expired = _public_state(row, user)
    if not visible:
        return HTMLResponse(pages.error_page(404, "页面不存在", "链接可能有误，或该项目已被移除"), status_code=404)
    if expired:
        return HTMLResponse(
            pages.error_page(410, "项目已到期", "该项目已超过设定的存活时长，访问已停止"),
            status_code=410,
        )
    if row["kind"] == "link" and row["link_url"]:
        return RedirectResponse(row["link_url"], status_code=302)

    rel = storage.safe_rel(rel)
    if rel in ("", "/"):
        rel = row["entry"] or "index.html"

    target = storage.resolve_in_project(slug, rel)
    if target is None:
        return HTMLResponse(pages.error_page(404, "路径非法", "请求的路径超出了项目范围"), status_code=404)

    if not target.is_file():
        # 目录 / 无扩展名 → 试 index.html；再退化到入口文件（SPA）
        if not os.path.splitext(rel)[1]:
            for cand in (f"{rel.rstrip('/')}/index.html", row["entry"], "index.html"):
                if not cand:
                    continue
                probe = storage.resolve_in_project(slug, cand)
                if probe and probe.is_file():
                    target = probe
                    break
        if not target.is_file():
            return HTMLResponse(pages.error_page(404, "页面不存在", "该项目里找不到这个文件"), status_code=404)

    st = target.stat()
    etag = f'W/"{st.st_mtime_ns}-{st.st_size}"'
    is_entry = row["entry"] and target.name == os.path.basename(row["entry"])
    cache = "no-store" if is_entry else "public, max-age=300"

    headers = {"ETag": etag, "Cache-Control": cache, **NOINDEX}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)

    if is_entry and request.method == "GET" and "text/html" in (request.headers.get("accept") or ""):
        views.bump(row["id"])

    media = storage.media_type(str(target))
    if media.startswith("text/") or media in ("application/javascript", "application/json"):
        headers["Content-Type"] = media
        with open(target, "rb") as fh:
            return Response(fh.read(), headers=headers)

    return FileResponse(target, media_type=media, headers=headers)


@router.get("/p/{slug}")
def serve_root(slug: str, request: Request):
    return _serve_file(slug, "", request)


@router.get("/p/{slug}/{file_path:path}")
def serve_file(slug: str, file_path: str, request: Request):
    return _serve_file(slug, file_path, request)


@router.get("/download/{slug}")
async def download(slug: str, request: Request):
    row = _load(slug)
    user = resolve_user(request)
    visible, expired = _public_state(row, user)
    if not visible:
        return HTMLResponse(pages.error_page(404, "项目不存在", "链接可能有误，或该项目已被移除"), status_code=404)
    if expired:
        return HTMLResponse(
            pages.error_page(410, "项目已到期", "该项目已超过设定的存活时长，下载已停止"), status_code=410
        )
    if row["kind"] == "link":
        return RedirectResponse(row["link_url"] or "/", status_code=302)
    if not row["allow_download"]:
        return HTMLResponse(pages.error_page(403, "未开放下载", "该项目仅支持在线预览"), status_code=403)

    path = storage.zip_path(slug)
    if not path.exists():
        path = await run_in_threadpool(storage.build_zip_on_demand, slug)
    if not path or not path.exists():
        return HTMLResponse(pages.error_page(404, "没有可下载的内容", "该项目没有文件"), status_code=404)

    views.bump_download(row["id"])
    filename = row["zip_name"] or f"{slug}.zip"
    return FileResponse(
        path,
        media_type="application/zip",
        filename=filename,
        headers={"Cache-Control": "no-store", **NOINDEX},
    )


@router.get("/v/{slug}")
def preview(slug: str, request: Request):
    row = _load(slug)
    user = resolve_user(request)
    visible, expired = _public_state(row, user)
    if not visible:
        return HTMLResponse(
            pages.error_page(404, "页面不存在", "链接可能有误，或该项目已被移除"), status_code=404
        )
    data = _dict(row, "")
    data["expired"] = expired
    site_title = get_setting("site_title") or config.SITE_TITLE
    return HTMLResponse(
        pages.preview_page(data, now_ms(), site_title),
        status_code=410 if expired else 200,
        headers=NOINDEX,
    )


@router.get("/portal")
def portal(request: Request):
    user = resolve_user(request)
    env_public = config.PUBLIC_PORTAL
    db_public = get_setting("public_portal", "0") == "1"
    if not (env_public or db_public or user):
        return RedirectResponse("/", status_code=302)

    now = now_ms()
    with db() as conn:
        rows = conn.execute(
            "SELECT p.*, u.display_name AS owner_display_name, u.username AS owner_username "
            "FROM projects p LEFT JOIN users u ON u.id=p.owner_id "
            "WHERE p.visibility='portal' AND p.status='active' "
            "AND (p.expires_at IS NULL OR p.expires_at>?) ORDER BY p.created_at DESC LIMIT 200",
            (now,),
        ).fetchall()

    items = []
    for r in rows:
        d = _dict(r, "")
        d["tags"] = _row_tags(r)
        items.append(d)
    return HTMLResponse(
        pages.portal_page(
            items,
            get_setting("site_title") or config.SITE_TITLE,
            config.SITE_SUBTITLE,
            now,
            bool(user),
        ),
        headers=NOINDEX,
    )


@router.get("/api/meta")
def meta():
    from ..db import db as _db
    with _db() as conn:
        row = conn.execute("SELECT COUNT(*) c FROM projects WHERE status='active'").fetchone()
    return {
        "site_title": get_setting("site_title") or config.SITE_TITLE,
        "subtitle": config.SITE_SUBTITLE,
        "version": "2.0.0",
        "online": row["c"],
        "public_portal": get_setting("public_portal", "0") == "1" or config.PUBLIC_PORTAL,
    }
