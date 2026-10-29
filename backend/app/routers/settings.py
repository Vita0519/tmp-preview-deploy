"""系统设置（站点标题、默认时长、门户可见性）。"""
from fastapi import APIRouter, Depends

from .. import config
from ..db import all_settings, db, get_setting, set_setting, tx
from ..security import admin_user

router = APIRouter(prefix="/api/settings", tags=["settings"])


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
        "public_portal": s.get("public_portal") == "1",
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
    if "default_ttl_hours" in payload:
        try:
            v = max(0.0, float(payload["default_ttl_hours"]))
        except (TypeError, ValueError):
            v = config.DEFAULT_TTL_HOURS
        set_setting("default_ttl_hours", str(v))
    if "public_portal" in payload:
        set_setting("public_portal", "1" if payload["public_portal"] else "0")
    return {
        "ok": True,
        "site_title": get_setting("site_title") or config.SITE_TITLE,
        "default_ttl_hours": float(get_setting("default_ttl_hours") or config.DEFAULT_TTL_HOURS),
        "public_portal": get_setting("public_portal", "0") == "1",
    }
