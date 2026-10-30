"""主题色：一处配置，控制台 / 门户 / 预览页 / 错误页共用。

只让管理员选一个「主色」，其余（hover、浅底、描边、渐变深色）全部派生，
避免让人一格一格调到不可用的对比度。派生公式与 frontend/src/theme.js 保持一致。
"""
from __future__ import annotations

# 默认墨绿，与站点图标同一色系
DEFAULT = "#0f766e"

# 设置页给的预设色板（都验过在浅底上足够清楚）
PRESETS = [
    ("墨绿", "#0f766e"),
    ("靛蓝", "#3b5bdb"),
    ("深青", "#0b7285"),
    ("藏紫", "#6741d9"),
    ("砖红", "#c2410c"),
    ("玫红", "#be1250"),
    ("赭石", "#a16207"),
    ("石板", "#475569"),
]


def normalize(raw: object) -> str:
    """把 #abc / #aabbcc / 带空格的输入收敛成 #aabbcc；非法就回默认。"""
    s = str(raw or "").strip().lower()
    if not s.startswith("#"):
        s = "#" + s
    body = s[1:]
    if len(body) == 3 and all(c in "0123456789abcdef" for c in body):
        body = "".join(c * 2 for c in body)
    if len(body) == 6 and all(c in "0123456789abcdef" for c in body):
        return "#" + body
    return DEFAULT


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = normalize(hex_color)[1:]
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _hex(rgb: tuple[float, float, float]) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(v))) for v in rgb)


def mix(a: str, b: str, t: float) -> str:
    """a 与 b 按 t（b 的占比）混合。"""
    ra, rb = _rgb(a), _rgb(b)
    return _hex(tuple(ra[i] * (1 - t) + rb[i] * t for i in range(3)))


def palette(accent: str | None = None) -> dict:
    """主色 → 整套品牌色板。"""
    brand = normalize(accent)
    r, g, b = _rgb(brand)
    return {
        "accent": brand,
        # hover 比主色略深，按下不发灰
        "hover": mix(brand, "#000000", 0.12),
        # 浅底：白底里掺一点主色，用作胶囊、选中态背景
        "soft": mix("#ffffff", brand, 0.07),
        # 描边：主色 22% 透明度
        "line": f"rgba({r},{g},{b},.22)",
        # 渐变收尾用的深色
        "deep": mix(brand, "#000000", 0.32),
        # 渐变起手用的亮色
        "light": mix(brand, "#ffffff", 0.18),
        # 需要自己拼 rgba 时用
        "rgb": f"{r},{g},{b}",
    }


def css_vars(accent: str | None = None) -> str:
    """注入到页面 <style> 开头的 :root 变量块。"""
    p = palette(accent)
    return (
        ":root{--brand:%s;--brand-hover:%s;--brand-soft:%s;--brand-line:%s;"
        "--brand-deep:%s;--brand-light:%s;--brand-rgb:%s}"
        % (p["accent"], p["hover"], p["soft"], p["line"], p["deep"], p["light"], p["rgb"])
    )


_cache: dict[str, object] = {"at": 0.0, "value": DEFAULT}


def current() -> str:
    """当前生效的主色（设置里没写就用默认）。带 5 秒缓存，页面渲染不额外打库。"""
    import time

    now = time.monotonic()
    if now - float(_cache["at"] or 0) < 5:
        return str(_cache["value"])
    value = DEFAULT
    try:
        from .db import get_setting

        value = normalize(get_setting("theme_accent") or DEFAULT)
    except Exception:  # noqa: BLE001 - 库还没建好时不要让页面挂掉
        value = DEFAULT
    _cache["at"] = now
    _cache["value"] = value
    return value


def reset_cache() -> None:
    _cache["at"] = 0.0
