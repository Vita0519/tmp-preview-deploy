"""访客侧：项目文件直出、zip 下载、预览外壳、门户列表、RSS。"""
import os
from html import escape
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response

from .. import author, branding, config, defaults, namerule, pages, storage, tagspec, theme, views
from ..db import db, get_setting, portal_cols, portal_max, tag_bar_limit, tag_cap
from ..security import now_ms, resolve_user

router = APIRouter(tags=["public"])

NOINDEX = {"X-Robots-Tag": "noindex, nofollow"}

# 失效链接的落点：门户首页。门户本身有权限控制（未登录/不公开时会转去登录），
# 所以这里无脑指 /portal 即可，不需要在跳转处再判一次权限，也不会泄露项目是否存在。
PORTAL_HOME = "/portal?gone=1"

# 门户一次最多取多少个（前端在其上做筛选/排序/分页）。
# 公开门户可能被大量项目灌满，必须有个天花板；超出部分由页面明确提示，不静默截断。


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
    keys = row.keys()
    owner = None
    if row["owner_username"]:
        owner = {
            "id": row["owner_id"],
            "username": row["owner_username"],
            "display_name": row["owner_display_name"] or row["owner_username"],
        }
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
        # 到期动作：门户要用它区分「到期删除」和「到期停访」，别让访客猜
        "expire_action": row["expire_action"] or "block",
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
        "expired": row["status"] == "expired"
        or (row["expires_at"] is not None and row["expires_at"] <= now_ms()),
        "views": row["views"],
        "tags": _row_tags(row),
        # 归属：谁建的/谁挂的外链就归谁。门户要按成员筛选，所以 id 也得带上
        "owner_id": row["owner_id"] if "owner_id" in keys else None,
        "owner": owner,
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


@router.get("/download/{slug}/{rel:path}")
async def download_single_file(slug: str, rel: str, request: Request):
    """项目里的单个文件直接下载。

    文件夹传上来就是一份能带走的文件集合：整包走 `/download/<slug>`，
    单个文件走这里，不用再单独传一次 zip 或另建外链。
    """
    row = _load(slug)
    user = resolve_user(request)
    visible, expired = _public_state(row, user)
    if not visible or expired:
        return RedirectResponse(PORTAL_HOME, status_code=302)
    if row["kind"] != "static":
        return RedirectResponse(f"/download/{slug}", status_code=302)
    if not row["allow_download"]:
        return HTMLResponse(pages.error_page(403, "未开放下载", "该项目仅支持在线预览"), status_code=403)

    target = storage.resolve_in_project(slug, rel)
    if not target or not target.is_file():
        return HTMLResponse(pages.error_page(404, "文件不存在", "这个路径下没有文件"), status_code=404)

    views.bump_download(row["id"])
    return FileResponse(
        target,
        media_type=storage.media_type(str(target)),
        filename=Path(target).name,
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
    # 外链项目：走本地短链，先记一次访问再 302 到源站。
    # 对访客来说仍然是一次跳转，没有中间页，也不会套 iframe；好处是圆环能统计到访问。
    if row["kind"] == "link" and row["link_url"]:
        if request.method == "GET" and _wants_html(request):
            views.bump(row["id"])
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
    # 门户是纯前端筛选/排序/分页：一次给够，别让人翻两页就翻空。
    # 上限仍然要有，否则公开门户被人刷几千个项目会把首页撑爆。
    with db() as conn:
        rows = conn.execute(
            "SELECT p.*, u.display_name AS owner_display_name, u.username AS owner_username "
            "FROM projects p LEFT JOIN users u ON u.id=p.owner_id "
            "WHERE p.visibility='portal' AND p.status='active' "
            "AND (p.expires_at IS NULL OR p.expires_at>?) ORDER BY p.created_at DESC LIMIT ?",
            (now, portal_max()),
        ).fetchall()
        total_public = conn.execute(
            "SELECT COUNT(*) c FROM projects WHERE visibility='portal' AND status='active' "
            "AND (expires_at IS NULL OR expires_at>?)",
            (now,),
        ).fetchone()["c"]

    items = [_dict(r, "") for r in rows]
    return HTMLResponse(
        pages.portal_page(
            items,
            get_setting("site_title") or config.SITE_TITLE,
            config.SITE_SUBTITLE,
            now,
            bool(user),
            author.load(),
            theme.current(),
            truncated=max(0, total_public - len(items)),
            tag_limit=tag_bar_limit(),
            cols=portal_cols(),
        ),
        headers=NOINDEX,
    )


@router.get("/rss.xml")
@router.get("/feed.xml")
def rss(request: Request):
    """门户的 RSS：只收门户可见且还没过期的项目。

    门户不公开且访客没登录时直接 404——给阅读器一个 HTML 登录页没有意义。
    """
    user = resolve_user(request)
    if not (config.PUBLIC_PORTAL or get_setting("public_portal", "0") == "1" or user):
        return Response(status_code=404)

    now = now_ms()
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM projects WHERE visibility='portal' AND status='active' "
            "AND (expires_at IS NULL OR expires_at>?) ORDER BY created_at DESC LIMIT ?",
            (now, portal_max()),  # 与门户同一上限（设置页可调）
        ).fetchall()

    base = _base_url(request)
    site_title = get_setting("site_title") or config.SITE_TITLE
    items = []
    for r in rows:
        link = f"{base}/v/{r['slug']}"
        desc = (r["description"] or "").strip() or _rss_desc(r)
        tags = "".join(
            f"<category>{escape(t)}</category>" for t in _row_tags(r)[:5]
        )
        items.append(
            "<item>"
            f"<title>{escape(r['title'])}</title>"
            f"<link>{escape(link)}</link>"
            f"<guid isPermaLink=\"true\">{escape(link)}</guid>"
            f"<pubDate>{_rfc822(r['created_at'])}</pubDate>"
            f"<description>{escape(desc)}</description>"
            f"{tags}"
            "</item>"
        )

    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">'
        "<channel>"
        f"<title>{escape(site_title)}</title>"
        f"<link>{escape(base + '/portal')}</link>"
        f"<description>{escape(config.SITE_SUBTITLE or site_title)}</description>"
        "<language>zh-CN</language>"
        f"<lastBuildDate>{_rfc822(now)}</lastBuildDate>"
        f'<atom:link href="{escape(base + "/rss.xml")}" rel="self" type="application/rss+xml"/>'
        f'<generator>tmp-preview</generator>'
        + "".join(items)
        + "</channel></rss>"
    )
    return Response(
        content=body,
        media_type="application/rss+xml; charset=utf-8",
        headers={"Cache-Control": "public, max-age=120", **NOINDEX},
    )


def _rss_desc(row) -> str:
    """没写简介时给一句有信息量的默认描述。"""
    kind = row["kind"]
    if kind == "link":
        return "外链项目"
    size = row["size_bytes"] or 0
    human = f"{size / 1024 / 1024:.1f} MB" if size >= 1024 * 1024 else f"{max(1, size // 1024)} KB"
    count = row["file_count"] or 0
    exp = row["expires_at"]
    tail = "长期有效" if not exp else f"到期 {_short_day(exp)}"
    return f"{count} 个文件 · {human} · {tail}"


def _rfc822(ts_ms: int) -> str:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime.fromtimestamp(ts_ms / 1000, ZoneInfo(config.TZ_NAME)).strftime(
        "%a, %d %b %Y %H:%M:%S %z"
    )


def _short_day(ts_ms: int) -> str:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime.fromtimestamp(ts_ms / 1000, ZoneInfo(config.TZ_NAME)).strftime("%m-%d %H:%M")


def _icon_info():
    return branding.payload()


def _base_url(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"


@router.get("/site-icon")
def site_icon():
    """自定义站点图标。没上传过就 404，页面会回落到内置图标。"""
    cur = branding.current()
    if not cur:
        return Response(status_code=404)
    return FileResponse(
        cur["path"],
        media_type=cur["mime"],
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/site.webmanifest")
def webmanifest():
    """动态 manifest：图标跟着站点图标走，主题色跟着主色走。"""
    cur = branding.current()
    title = get_setting("site_title") or config.SITE_TITLE
    if cur:
        icons = [{"src": cur["url"], "sizes": "any", "type": cur["mime"], "purpose": "any"}]
    else:
        icons = [
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ]
    return JSONResponse(
        {
            "name": title,
            "short_name": title,
            "start_url": "/",
            "display": "standalone",
            "background_color": "#0b0d10",
            "theme_color": theme.palette(theme.current())["accent"],
            "icons": icons,
        },
        media_type="application/manifest+json",
    )


@router.get("/api/meta")
def meta():
    from ..db import db as _db
    with _db() as conn:
        row = conn.execute("SELECT COUNT(*) c FROM projects WHERE status='active'").fetchone()
    return {
        "site_title": get_setting("site_title") or config.SITE_TITLE,
        "subtitle": config.SITE_SUBTITLE,
        "version": config.VERSION,
        "online": row["c"],
        "public_portal": get_setting("public_portal", "0") == "1" or config.PUBLIC_PORTAL,
        "ttl_defaults": defaults.all_defaults(),
        "default_expire_action": get_setting("default_expire_action") or "block",
        # 控制台首屏就要上色，不能等设置页接口；载荷含当前主题插件的全部语义令牌
        "theme": theme.payload(),
        "site_icon": _icon_info(),
        "tags": tagspec.rules(max_per_project=tag_cap(), bar_limit=tag_bar_limit()),
        "title_rule": namerule.rules(),
        "rss": "/rss.xml",
        # 署名信息：前端登录页与设置页「关于」直接用它，别在前端另抄一份
        "project": {
            "name": config.PROJECT_NAME,
            "url": config.PROJECT_URL,
            "author": config.PROJECT_AUTHOR,
            "license": config.PROJECT_LICENSE,
            "skill_guide": config.SKILL_GUIDE_URL,
        },
    }
