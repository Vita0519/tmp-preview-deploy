"""系统设置（站点标题、主题色、站点图标、按可见性的默认时长、到期策略、门户可见性）。"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .. import author, branding, config, defaults, tagspec, theme, version
from ..db import (
    all_settings,
    db,
    clamp_portal_max,
    get_setting,
    log_event,
    portal_max,
    set_setting,
    tag_bar_limit,
    tag_cap,
)
from ..pages import ICONS
from ..security import admin_user

router = APIRouter(prefix="/api/settings", tags=["settings"])

EXPIRE_ACTIONS = ("block", "delete")


def _num(raw, fallback: float) -> float:
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return fallback


def _theme_payload(s: dict | None = None) -> dict:
    """主题：当前主色派生族 + 当前主题插件全部语义令牌 + 已装插件清单（含内置）。

    设置页的插件清单带每套的完整 vars（点卡片就能本地预览整套令牌）；
    /api/meta 那份保持精简，只有当前插件的 vars。
    """
    p = theme.payload()
    p["plugins"] = [
        {**m, "vars": (theme.get_plugin(m["id"]) or {}).get("vars", {})} for m in p["plugins"]
    ]
    pid = p["plugin"]
    current = next((x for x in p["plugins"] if x["id"] == pid), None)
    # 主色被手改过（不等于当前主题的默认主色）→ 前端把「自定义」标为选中
    p["custom"] = bool(current) and theme.normalize(p["raw"]) != theme.normalize(current.get("default_accent"))
    return p


@router.get("")
def read_settings(user: dict = Depends(admin_user)):
    s = all_settings()
    with db() as conn:
        counts = conn.execute(
            "SELECT COUNT(*) projects, COALESCE(SUM(size_bytes),0) size FROM projects WHERE status<>'deleted'"
        ).fetchone()
        users = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        events = conn.execute(
            "SELECT at, action, detail FROM events ORDER BY at DESC LIMIT 20"
        ).fetchall()
    return {
        "site_title": s.get("site_title") or config.SITE_TITLE,
        "default_ttl_hours": float(s.get("default_ttl_hours") or config.DEFAULT_TTL_HOURS),
        "ttl_defaults": defaults.all_defaults(),
        "default_expire_action": s.get("default_expire_action") or "block",
        "public_portal": s.get("public_portal") == "1",
        "portal_max": portal_max(),
        "theme": _theme_payload(s),
        "site_icon": _icon_payload(),
        "tags": _tags_payload(),
        "author": author.load(),
        "author_types": [
            {"key": k, "label": v["label"], "paths": ICONS.get(v["icon"], "")}
            for k, v in author.TYPE_META.items()
        ],
        "runtime": {
            "data_dir": str(config.DATA_DIR),
            "projects": counts["projects"],
            "size_bytes": counts["size"],
            "agents": users,
            "max_upload_mb": config.MAX_UPLOAD_MB,
            "session_days": config.SESSION_DAYS,
            "tz": config.TZ_NAME,
        },
        "events": [{"at": e["at"], "action": e["action"], "detail": e["detail"]} for e in events],
    }


@router.patch("")
async def update_settings(payload: dict, user: dict = Depends(admin_user)):
    if "site_title" in payload:
        set_setting("site_title", str(payload["site_title"]).strip()[:60])

    # 兼容旧字段：只改「链接可见」这一档，避免把其余两档一起冲掉
    if "default_ttl_hours" in payload and "ttl_defaults" not in payload:
        set_setting("default_ttl_hours", str(_num(payload["default_ttl_hours"], 24)))

    ttl = payload.get("ttl_defaults")
    if isinstance(ttl, dict):
        for vis in defaults.VISIBILITIES:
            if vis in ttl:
                set_setting(f"default_ttl_{vis}", str(_num(ttl[vis], 0)))

    if payload.get("default_expire_action") in EXPIRE_ACTIONS:
        set_setting("default_expire_action", payload["default_expire_action"])
    if "public_portal" in payload:
        set_setting("public_portal", "1" if payload["public_portal"] else "0")
    if "portal_max" in payload:
        set_setting("portal_max", str(clamp_portal_max(payload["portal_max"])))
    if "author" in payload:
        author.save(payload["author"])
    # 换主题插件：主色跟着换（除非这次请求同时指定了主色，那就以主色为准——允许选完主题再微调）
    if payload.get("theme_plugin"):
        pid = str(payload["theme_plugin"]).strip().lower()
        m = theme.get_plugin(pid)
        if not m:
            raise HTTPException(status_code=422, detail=theme.plugin_error(pid))
        set_setting("theme_plugin", pid)
        if "theme_accent" not in payload:
            set_setting("theme_accent", m.get("default_accent") or theme.DEFAULT)
        theme.reset_cache()
    if "theme_accent" in payload:
        set_setting("theme_accent", theme.normalize(payload["theme_accent"]))
        theme.reset_cache()

    # 标签的两条软限制：每个项目能打几个、门户标签条放几个
    if "tag_max_per_project" in payload:
        set_setting("tag_max_per_project", str(tagspec.clamp_max_tags(payload["tag_max_per_project"])))
    if "tag_bar_limit" in payload:
        set_setting("tag_bar_limit", str(tagspec.clamp_bar_limit(payload["tag_bar_limit"])))

    return {
        "ok": True,
        "site_title": get_setting("site_title") or config.SITE_TITLE,
        "default_ttl_hours": float(get_setting("default_ttl_hours") or config.DEFAULT_TTL_HOURS),
        "ttl_defaults": defaults.all_defaults(),
        "default_expire_action": get_setting("default_expire_action") or "block",
        "public_portal": get_setting("public_portal", "0") == "1",
        "portal_max": portal_max(),
        "theme": _theme_payload(),
        "site_icon": _icon_payload(),
        "tags": _tags_payload(),
        "author": author.load(),
    }


def _icon_payload() -> dict:
    return branding.payload()


def _tags_payload() -> dict:
    """标签规则 + 当前占用，设置页据此显示「已用 42 / 300」。"""
    with db() as conn:
        usage = tagspec.pool_usage(conn)
        cap = tag_cap(conn)
        bar = tag_bar_limit(conn)
    return {**tagspec.rules(max_per_project=cap, bar_limit=bar), **usage}


@router.get("/version")
def version_check(force: bool = False, user: dict = Depends(admin_user)):
    """对比 GitHub 最新 Release；失败返回 ok=false，前端静默处理。"""
    return version.check(force)


@router.post("/tags/prune")
def prune_tags(user: dict = Depends(admin_user)):
    """清掉没有任何项目在用的标签，池子腾出空间。"""
    with db() as conn:
        removed = tagspec.prune_orphans(conn)
    if removed:
        log_event("settings", user["id"], None, f"清理未使用标签 {removed} 个")
    return {"ok": True, "removed": removed, "tags": _tags_payload()}


@router.post("/icon")
async def upload_icon(file: UploadFile = File(...), user: dict = Depends(admin_user)):
    """上传站点图标。同一时间只保留一份，换格式会替换掉旧的。"""
    data = await file.read()
    try:
        cur = branding.save(file.filename or "", data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, "site_icon": _icon_payload(), "url": cur.get("url", "")}


@router.delete("/icon")
def delete_icon(user: dict = Depends(admin_user)):
    """删掉自定义图标，回到内置的沙漏套装。"""
    branding.remove()
    return {"ok": True, "site_icon": _icon_payload()}


# ---------------- 主题商店 ----------------

EXAMPLE_REPO = "Vita0519/tmp-preview-deploy"
EXAMPLE_PATH = "examples/theme-plugin/theme.json"


@router.post("/themes/preview")
async def themes_preview(body: dict = ..., user: dict = Depends(admin_user)):
    """主题商店预览：给一个 GitHub 仓库（owner/repo 或任意 GitHub 链接），枚举里面的 theme.json。"""
    repo = str(body.get("repo") or "").strip()
    if not repo:
        raise HTTPException(status_code=422, detail="请填写仓库")
    return theme.store_preview(repo)


@router.post("/themes/install")
async def themes_install(body: dict = ..., user: dict = Depends(admin_user)):
    """安装一个主题插件：{repo, path, ref} 从 GitHub 拉，或 {source:"example"} 装仓库自带的示例。"""
    if str(body.get("source") or "") == "example":
        # 示例插件随仓库分发（examples/theme-plugin/），演示完整安装链路，不依赖外网
        f = config.BASE_DIR / "examples" / "theme-plugin" / "theme.json"
        if not f.is_file():
            raise HTTPException(status_code=404, detail="示例插件不存在")
        meta = theme.install_manifest(f.read_bytes(), "example")
        return {"ok": True, "plugin": meta, "theme": _theme_payload()}

    repo = str(body.get("repo") or "").strip()
    path = str(body.get("path") or "").strip()
    if not repo or not path:
        raise HTTPException(status_code=422, detail="缺少仓库或文件路径")
    ref = str(body.get("ref") or "").strip()
    try:
        meta = theme.store_install(repo, ref, path)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"从 GitHub 拉取失败：{e}") from e
    return {"ok": True, "plugin": meta, "theme": _theme_payload()}


@router.delete("/themes/{pid}")
def themes_delete(pid: str, user: dict = Depends(admin_user)):
    try:
        theme.uninstall(pid)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return {"ok": True, "theme": _theme_payload()}


@router.get("/themes/{pid}/preview.png")
def themes_preview_image(pid: str, user: dict = Depends(admin_user)):
    from fastapi.responses import Response

    p = theme.PLUGINS_DIR / str(pid).strip().lower() / "preview.png"
    if not p.is_file():
        raise HTTPException(status_code=404, detail="没有预览图")
    return Response(p.read_bytes(), media_type="image/png")
