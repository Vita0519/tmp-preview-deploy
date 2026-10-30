"""主题：一套「主色 + 中性色画布」，控制台 / 门户 / 预览页 / 错误页共用。

参考网页配色的 60-30-10 黄金比例：60% 是画布与留白（中性色），30% 是卡片与容器，
只有 10% 是主色（按钮、圆环、进度条、选中态）。所以「换主题」不能只换一个色块，
中性色的冷暖决定整体气质，主色只负责强调——这里把两者打包成「配色系列」。

主色照旧全部派生（hover / 浅底 / 描边 / 渐变深色），中性色每套只给 4 个锚点
（画布 bg、正文 ink、次要 ink2），其余由它们混出来，避免一格一格手调调到不可用。
派生公式与 frontend/src/theme.js 保持一致。
"""
from __future__ import annotations

DEFAULT = "#0f766e"

# ---------------------------------------------------------------- 配色系列
# 每套 = 主色 + 画布底 + 两级文字色。其余中性色由这三个锚点混出来。
SERIES = [
    {
        "key": "classic",
        "name": "经典墨绿",
        "desc": "暖灰画布 + 墨绿强调，克制耐看，内容始终是主角",
        "use": "通用后台 / 长期使用",
        "accent": "#0f766e",
        "bg": "#f6f7f5",
        "ink": "#14161a",
        "ink2": "#4a5057",
    },
    {
        "key": "tech",
        "name": "科技感",
        "desc": "冷灰蓝底 + 电光蓝，理性、精确、有速度感",
        "use": "开发者工具 / 数据看板",
        "accent": "#2563eb",
        "bg": "#f3f5fa",
        "ink": "#0f172a",
        "ink2": "#475467",
    },
    {
        "key": "macaron",
        "name": "马卡龙",
        "desc": "奶油粉底 + 玫瑰粉，明亮柔和，带一点甜",
        "use": "作品集 / 活动页 / 面向 C 端",
        "accent": "#d9557a",
        "bg": "#fdf0f3",
        "ink": "#2b2226",
        "ink2": "#6b565d",
    },
    {
        "key": "morandi",
        "name": "莫兰迪",
        "desc": "灰米画布 + 雾霭蓝，低饱和、有灰度，安静高级",
        "use": "设计工作室 / 品牌展示",
        "accent": "#5d7280",
        "bg": "#f3f1ed",
        "ink": "#2f3336",
        "ink2": "#5c6367",
    },
    {
        "key": "ink",
        "name": "新中式",
        "desc": "宣纸底 + 朱砂红，温润庄重，留白即呼吸",
        "use": "政务公文 / 传统文化",
        "accent": "#a8332b",
        "bg": "#f8f4ec",
        "ink": "#2a241f",
        "ink2": "#5d554c",
    },
    {
        "key": "minimal",
        "name": "极简黑白",
        "desc": "纯灰画布 + 近黑，去掉所有颜色干扰，只留结构",
        "use": "文档站 / 摄影作品",
        "accent": "#1f2328",
        "bg": "#f7f7f8",
        "ink": "#111315",
        "ink2": "#4d5157",
    },
]

BY_KEY = {s["key"]: s for s in SERIES}
DEFAULT_SERIES = "classic"

# 兼容旧设置项 theme_accent 的「预设色板」：仍然可以只换主色（中性色跟随当前系列）
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


def _lum(c: str) -> float:
    def ch(v: float) -> float:
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = _rgb(c)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


# 主色要同时当「按钮底」和「浅底上的文字」用，跟白底的对比度低于这个值就撑不住
MIN_CONTRAST = 3.0


def readable(brand: str) -> str:
    """主色在白底上必须看得见，不够就等比压深（色相不动），别让人选个淡黄就全站灰掉。"""
    if contrast(brand, "#ffffff") >= MIN_CONTRAST:
        return brand
    lo, hi = 0.0, 0.88
    for _ in range(18):
        mid = (lo + hi) / 2
        if contrast(mix(brand, "#000000", mid), "#ffffff") >= MIN_CONTRAST:
            hi = mid
        else:
            lo = mid
    return mix(brand, "#000000", hi)


def series_of(key: object) -> dict:
    """按 key 取系列；不认识就回经典墨绿。"""
    return BY_KEY.get(str(key or "").strip(), BY_KEY[DEFAULT_SERIES])


def series_by_accent(accent: object) -> dict | None:
    """反查：这个主色属于哪套系列（设置页用来判断「当前是哪张卡」）。"""
    want = normalize(accent)
    for s in SERIES:
        if s["accent"] == want:
            return s
    return None


def neutral_of(key: object) -> dict:
    """系列 → 整套中性色。只给 3 个锚点，剩下 8 个混出来。"""
    s = series_of(key)
    bg, ink, ink2 = s["bg"], s["ink"], s["ink2"]
    return {
        # 画布：--bg 是主体 60%，--bg-2 用于从上到下的极淡渐变起手
        "bg": bg,
        "bg-2": mix("#ffffff", bg, 0.42),
        "bg-deep": mix(bg, ink, 0.025),
        # 容器：卡片固定纯白，次级容器用这两个
        "surface-2": mix("#ffffff", bg, 0.48),
        "surface-3": mix(bg, ink, 0.012),
        # 文字：正文 / 次要 / 弱 / 更弱
        "ink": ink,
        "ink-2": ink2,
        "ink-3": mix(ink2, bg, 0.28),
        "ink-4": mix(ink2, bg, 0.55),
        # 描边：两档，1px 分层靠它们
        "line": mix(bg, ink, 0.065),
        "line-2": mix(bg, ink, 0.14),
        # 需要自己拼 rgba 时用
        "ink-rgb": "%d,%d,%d" % _rgb(ink),
        "bg-rgb": "%d,%d,%d" % _rgb(bg),
    }


def palette(accent: str | None = None, series: str | None = None) -> dict:
    """主色 + 中性色 → 整套色板。"""
    raw = normalize(accent if accent else current())
    brand = readable(raw)
    key = series if series else current_series()
    r, g, b = _rgb(brand)
    s = series_of(key)
    return {
        "accent": brand,
        # 用户原本填的值（可能太淡，已被 readable 压深）
        "raw": raw,
        "adjusted": brand != raw,
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
        # 系列
        "series": s["key"],
        "series_name": s["name"],
        "neutral": neutral_of(s["key"]),
    }


def css_vars(accent: str | None = None, series: str | None = None) -> str:
    """注入到页面 <style> 开头的 :root 变量块（品牌色 + 中性色画布）。"""
    p = palette(accent, series)
    n = p["neutral"]
    return (
        ":root{--brand:%s;--brand-hover:%s;--brand-soft:%s;--brand-line:%s;"
        "--brand-deep:%s;--brand-light:%s;--brand-rgb:%s;"
        "--bg:%s;--bg-2:%s;--bg-deep:%s;--surface-2:%s;--surface-3:%s;"
        "--ink:%s;--ink-2:%s;--ink-3:%s;--ink-4:%s;--line:%s;--line-2:%s;"
        "--ink-rgb:%s;--bg-rgb:%s}"
        % (
            p["accent"], p["hover"], p["soft"], p["line"], p["deep"], p["light"], p["rgb"],
            n["bg"], n["bg-2"], n["bg-deep"], n["surface-2"], n["surface-3"],
            n["ink"], n["ink-2"], n["ink-3"], n["ink-4"], n["line"], n["line-2"],
            n["ink-rgb"], n["bg-rgb"],
        )
    )


def series_payload() -> list[dict]:
    """给设置页/前端的系列清单：带上完整中性色，卡片可以直接按真实配色渲染。"""
    out = []
    for s in SERIES:
        out.append(
            {
                "key": s["key"],
                "name": s["name"],
                "desc": s["desc"],
                "use": s["use"],
                "accent": s["accent"],
                "neutral": neutral_of(s["key"]),
            }
        )
    return out


_cache: dict[str, object] = {"at": 0.0, "value": DEFAULT, "series": DEFAULT_SERIES}


def _load() -> None:
    value, key = DEFAULT, DEFAULT_SERIES
    try:
        from .db import get_setting

        key = series_of(get_setting("theme_series")).get("key") or DEFAULT_SERIES
        value = normalize(get_setting("theme_accent") or BY_KEY[key]["accent"])
    except Exception:  # noqa: BLE001 - 库还没建好时不要让页面挂掉
        value, key = DEFAULT, DEFAULT_SERIES
    _cache["value"] = value
    _cache["series"] = key


def current() -> str:
    """当前生效的主色（设置里没写就用默认）。带 5 秒缓存，页面渲染不额外打库。"""
    import time

    if time.monotonic() - float(_cache["at"] or 0) < 5:
        return str(_cache["value"])
    _load()
    _cache["at"] = time.monotonic()
    return str(_cache["value"])


def current_series() -> str:
    """当前生效的配色系列 key。"""
    import time

    if time.monotonic() - float(_cache["at"] or 0) < 5:
        return str(_cache["series"])
    _load()
    _cache["at"] = time.monotonic()
    return str(_cache["series"])


def reset_cache() -> None:
    _cache["at"] = 0.0
