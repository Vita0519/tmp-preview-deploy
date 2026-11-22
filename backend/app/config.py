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


def _version() -> str:
    """版本号统一放仓库根 VERSION，改一处、跑 scripts/sync_version.py 同步其他文件。"""
    try:
        return (BASE_DIR / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"


VERSION = _env("VERSION", _version())

# 数据根目录：容器内挂 /data，本地默认 ./data
DATA_DIR = Path(_env("DATA_DIR", str(BASE_DIR / "data"))).resolve()
DB_PATH = DATA_DIR / "db.sqlite3"
FILES_DIR = DATA_DIR / "projects"
ZIPS_DIR = DATA_DIR / "zips"

SITE_TITLE = _env("SITE_TITLE", "临时预览站")
SITE_SUBTITLE = _env("SITE_SUBTITLE", "到期自动回收 · 多 Agent 共享")

# 项目标识：AGPL-3.0 §7(b) 附加条款要求再分发/对外服务时保留署名，
# 所以这几项会在门户页脚、登录页、设置页「关于」里显示，改之前先看 NOTICE。
PROJECT_NAME = _env("PROJECT_NAME", "tmp-preview")
PROJECT_URL = _env("PROJECT_URL", "https://github.com/Vita0519/tmp-preview-deploy")
PROJECT_AUTHOR = _env("PROJECT_AUTHOR", "Vita0519")
PROJECT_LICENSE = "AGPL-3.0-only"
# Agent 接入指南页：由项目方托管，不随部署域名变化；fork 后可换成自己的
SKILL_GUIDE_URL = _env("SKILL_GUIDE_URL", "https://pre.allfather.top/v/agent-guide")

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

# 主题商店取文件的镜像前缀（可选）：raw.githubusercontent 不通的网络上，
# 填一个 {repo}/{ref}/{path} 形式的自建/第三方镜像，如 https://ghfast.top/https://raw.githubusercontent.com
THEME_RAW_MIRROR = _env("THEME_RAW_MIRROR", "")

# 主题商店的 GitHub API Token（可选）：未认证限额 60 次/小时，配 Token 提到 5000
THEME_GH_TOKEN = _env("THEME_GH_TOKEN", "")

TZ_NAME = _env("TZ", "Asia/Shanghai")

DIST_DIR = BASE_DIR / "frontend" / "dist"
