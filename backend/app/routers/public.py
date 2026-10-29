"""访客侧：项目文件直出、zip 下载、预览外壳、门户列表。"""
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

from .. import author, config, defaults, pages, storage, views
from ..db import db, get_setting
from ..security import now_ms, resolve_user

router = APIRouter(tags=["public"])

NOINDEX = {"X-Robots-Tag": "noindex, nofollow"}

# 失效链接的落点：门户首页。门户本身有权限控制（未登录/不公开时会转去登录），
# 所以这里无脑指 /portal 即可，不需要在跳转处再判一次权限，也不会泄露项目是否存在。
PORTAL_HOME = "/portal?gone=1"


def _wants_html(request: Request) -> bool:
    """页面导航（顶层或 iframe）会带 text/html；图片/脚本这类子资源不会。"""
    return "text/html" in (request.headers.get("accept") or "").lower()


def _broken(request: Request):
    """失效项目：子资源静默 404；页面导航回「能跳出 iframe」的失效页。"""
    if not _wants_html(request):
        return Response(status_code=404)
    return HTMLResponse(
        pages.gone_page(PORTAL_HOME),
        status_code=404,
        headers={**NOINDEX, "Cache-Control": "no-store"},
    )


def _entry_ok(row) -> bool:
    """项目在磁盘上是否真的还有可展示的入口文件。"""
    if row["kind"] != "static":
        return True
    rel = row["entry"] or "index.html"
    target = storage.resolve_in_project(row["slug"], rel)
    return bool(target and target.is_file())


def _only_html(slug: str):
    """根目录只有一个 html 文件时拿它当入口（不少单页站不叫 index.html）。"""
    try:
        base = storage.project_dir(slug)
        if not base.is_dir():
            return None
        htmls = [f for f in base.iterdir() if f.is_file() and f.suffix.lower() in (".html", ".htm")]
    except OSError:
        return None
    return htmls[0] if len(htmls) == 1 else None


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
        "visibility": row["visibility"],
        "created_at": row["created_at"],
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
    if not visible or expired:
        return _broken(request)
    if row["kind"] == "link" and row["link_url"]:
        return RedirectResponse(row["link_url"], status_code=302)

    rel = storage.safe_rel(rel)
    root_request = rel in ("", "/")
    if root_request:
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
        # 根路径但项目里只有一个 html（没叫 index.html）→ 就拿它当入口，别让整站打不开
        if root_request and not target.is_file():
            only = _only_html(slug)
            if only is not None:
                target = only
        if not target.is_file():
            # 整个项目都没有可用入口 = 链接失效，把窗口带回门户而不是在 iframe 里显示 404
            if not _entry_ok(row):
                return _broken(request)
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
    if not visible or expired:
        return RedirectResponse(PORTAL_HOME, status_code=302)
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
    # 项目没了 / 到期了 / 没权限 → 直接回门户，不要再给一个「原地 404 + 倒计时」的四不像
    if not visible or expired:
        return RedirectResponse(PORTAL_HOME, status_code=302)
    # 外链项目：不套外壳、不进 iframe，直接跳到目标站点
    if row["kind"] == "link" and row["link_url"]:
        return RedirectResponse(row["link_url"], status_code=302)
    # 静态项目连入口文件都没有 → 同样是失效链接
    if row["kind"] == "static" and not _entry_ok(row) and _only_html(slug) is None:
        return RedirectResponse(PORTAL_HOME, status_code=302)
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
            author.load(),
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
        "ttl_defaults": defaults.all_defaults(),
        "default_expire_action": get_setting("default_expire_action") or "block",
    }
