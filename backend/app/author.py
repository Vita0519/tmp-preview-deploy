"""站点作者信息：显示名 / 一句话介绍 / 一排社交链接。

存成 settings 里的一条 JSON（key = author），门户页顶部渲染。
链接类型是白名单，URL 统一做规范化，只允许 http(s) 与 mailto。
"""
import json
import re

from .db import set_setting, get_setting

# type -> (默认标签, 图标 key)
TYPE_META: dict[str, dict] = {
    "github": {"label": "GitHub", "icon": "github"},
    "x": {"label": "X", "icon": "x"},
    "mail": {"label": "邮箱", "icon": "mail"},
    "blog": {"label": "博客", "icon": "globe"},
    "douyin": {"label": "抖音", "icon": "music"},
    "wechat": {"label": "微信", "icon": "chat"},
    "bilibili": {"label": "哔哩哔哩", "icon": "play"},
    "zhihu": {"label": "知乎", "icon": "star"},
    "rss": {"label": "RSS", "icon": "rss"},
    "link": {"label": "链接", "icon": "link"},
}

MAX_LINKS = 12
_MAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SCHEME = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*):")


def _safe_url(url: str) -> str:
    """只放行 http(s)；带了别的协议（javascript: / data: …）一律丢弃。"""
    url = url.strip()
    if not url:
        return ""
    if re.match(r"^https?://", url, re.I):
        return url
    m = _SCHEME.match(url)
    if m:  # 有协议但不是 http(s)，判为非法
        return ""
    return "https://" + url.lstrip("/")


def empty() -> dict:
    return {"name": "", "bio": "", "links": []}


def normalize(raw) -> dict:
    """把前端传来的结构洗成可安全渲染的数据。"""
    if not isinstance(raw, dict):
        return empty()
    out = {
        "name": str(raw.get("name") or "").strip()[:40],
        "bio": str(raw.get("bio") or "").strip()[:120],
        "links": [],
    }
    for item in (raw.get("links") or [])[:MAX_LINKS]:
        if not isinstance(item, dict):
            continue
        typ = item.get("type") if item.get("type") in TYPE_META else "link"
        url = str(item.get("url") or "").strip()[:400]
        label = str(item.get("label") or "").strip()[:20] or TYPE_META[typ]["label"]
        if typ == "mail":
            addr = url[len("mailto:"):] if url.lower().startswith("mailto:") else url
            if not _MAIL.match(addr):
                continue
            url = f"mailto:{addr}"
        else:
            url = _safe_url(url)
            if not url:
                continue
            if not re.match(r"^https?://[^\s]+$", url, re.I):
                continue
        out["links"].append({"type": typ, "label": label, "url": url})
    return out


def load() -> dict:
    raw = get_setting("author") or ""
    if not raw:
        return empty()
    try:
        return normalize(json.loads(raw))
    except (ValueError, TypeError):
        return empty()


def save(raw) -> dict:
    data = normalize(raw)
    set_setting("author", json.dumps(data, ensure_ascii=False))
    return data


def is_blank(a: dict) -> bool:
    return not (a.get("name") or a.get("bio") or a.get("links"))
