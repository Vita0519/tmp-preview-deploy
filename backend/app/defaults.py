"""按可见性计算默认存活时长。

三种可见性（门户 / 链接 / 私有）各自有一套默认时长，管理员可在设置页调整，
未在库里配置时回落到环境变量（config.TTL_BY_VISIBILITY）。0 小时表示永久。
"""
from . import config
from .db import get_setting
from .security import now_ms

VISIBILITIES = ("portal", "link", "private")

# 前端表格/表单里用的短标签
LABELS = {"portal": "门户可见", "link": "持链接可见", "private": "仅自己可见"}


def ttl_hours(visibility: str) -> float:
    """返回该可见性的默认小时数（0 = 永久）。"""
    vis = visibility if visibility in VISIBILITIES else "link"
    raw = (get_setting(f"default_ttl_{vis}") or "").strip()
    if raw != "":
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    return max(0.0, float(config.TTL_BY_VISIBILITY.get(vis, config.DEFAULT_TTL_HOURS)))


def expiry_for(visibility: str, base: int | None = None) -> int | None:
    """按可见性默认时长算出到期时间戳；默认永久时返回 None。"""
    hours = ttl_hours(visibility)
    if hours <= 0:
        return None
    return (base if base is not None else now_ms()) + int(hours * 3600_000)


def all_defaults() -> dict:
    return {vis: ttl_hours(vis) for vis in VISIBILITIES}
