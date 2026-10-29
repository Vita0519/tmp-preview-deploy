"""运行配置：全部走环境变量，容器内外行为一致。"""
import os
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)) or default)
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)) or default)
    except ValueError:
        return default


def _bool(name: str, default: bool = False) -> bool:
    v = _env(name, "1" if default else "0").lower()
    return v in ("1", "true", "yes", "on")


# 仓库根目录（backend/app/config.py → 上三层）
BASE_DIR = Path(__file__).resolve().parents[2]

# 数据根目录：容器内挂 /data，本地默认 ./data
DATA_DIR = Path(_env("DATA_DIR", str(BASE_DIR / "data"))).resolve()
DB_PATH = DATA_DIR / "db.sqlite3"
FILES_DIR = DATA_DIR / "projects"
ZIPS_DIR = DATA_DIR / "zips"

SITE_TITLE = _env("SITE_TITLE", "临时预览站")
SITE_SUBTITLE = _env("SITE_SUBTITLE", "到期自动回收 · 多 Agent 共享")

# 门户顶部「作者名片」的初始值。刻意用中性占位身份，不写任何真实姓名/联系方式。
AUTHOR_NAME = _env("AUTHOR_NAME", "vita")
AUTHOR_BIO = _env("AUTHOR_BIO", "互联网混子")

DEFAULT_TTL_HOURS = _float("DEFAULT_TTL_HOURS", 24)

# 按可见性区分的默认存活时长（小时，0 = 永久）。未单独配置时回落到 DEFAULT_TTL_HOURS。
TTL_BY_VISIBILITY = {
    "portal": _float("DEFAULT_TTL_PORTAL_HOURS", 6),
    "link": _float("DEFAULT_TTL_LINK_HOURS", 12),
    "private": _float("DEFAULT_TTL_PRIVATE_HOURS", 0),
}
MAX_UPLOAD_MB = _int("MAX_UPLOAD_MB", 1024)

# 首次启动自动创建的管理员
ADMIN_USERNAME = _env("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = _env("ADMIN_PASSWORD", "")
ADMIN_DISPLAY_NAME = _env("ADMIN_DISPLAY_NAME", "管理员")

SESSION_DAYS = _int("SESSION_DAYS", 7)
COOKIE_NAME = _env("COOKIE_NAME", "pv_sid")
COOKIE_SECURE = _bool("COOKIE_SECURE", False)

# 是否允许匿名访问 /portal 列表（默认关闭：只认直链）
PUBLIC_PORTAL = _bool("PUBLIC_PORTAL", False)

TZ_NAME = _env("TZ", "Asia/Shanghai")

DIST_DIR = BASE_DIR / "frontend" / "dist"
