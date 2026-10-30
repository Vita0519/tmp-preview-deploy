"""系统设置（站点标题、主题色、站点图标、按可见性的默认时长、到期策略、门户可见性）。"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from .. import author, branding, config, defaults, theme
from ..db import all_settings, db, get_setting, set_setting
from ..pages import ICONS
from ..security import admin_user

router = APIRouter(prefix="/api/settings", tags=["settings"])

EXPIRE_ACTIONS = ("block", "delete")


def _num(raw, fallback: float) -> float:
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return fallback


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
        "theme": {**theme.palette(s.get("theme_accent") or theme.DEFAULT),
                  "presets": [{"name": n, "value": v} for n, v in theme.PRESETS]},
        "site_icon": _icon_payload(),
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
    if "author" in payload:
        author.save(payload["author"])
    if "theme_accent" in payload:
        set_setting("theme_accent", theme.normalize(payload["theme_accent"]))
        theme.reset_cache()

    return {
        "ok": True,
        "site_title": get_setting("site_title") or config.SITE_TITLE,
        "default_ttl_hours": float(get_setting("default_ttl_hours") or config.DEFAULT_TTL_HOURS),
        "ttl_defaults": defaults.all_defaults(),
        "default_expire_action": get_setting("default_expire_action") or "block",
        "public_portal": get_setting("public_portal", "0") == "1",
        "theme": {**theme.palette(get_setting("theme_accent") or theme.DEFAULT),
                  "presets": [{"name": n, "value": v} for n, v in theme.PRESETS]},
        "site_icon": _icon_payload(),
        "author": author.load(),
    }


def _icon_payload() -> dict:
    return branding.payload()


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
