"""版本检查：对比 GitHub 上的最新 Release，带 1 小时缓存。

出站请求可能被墙或超时，失败只返回 error，不抛异常——前端静默处理即可。
"""
from __future__ import annotations

import json
import re
import time
import urllib.request

from .config import PROJECT_URL, VERSION

CACHE_TTL = 3600
FALLBACK_REPO = "Vita0519/tmp-preview-deploy"
_cache: dict = {"at": 0.0, "data": None}


def repo() -> str:
    m = re.search(r"github\.com/([^/]+/[^/#?]+)", PROJECT_URL or "")
    return m.group(1) if m else FALLBACK_REPO


def _parts(v: str) -> list[int]:
    out: list[int] = []
    for x in re.split(r"[.+-]", str(v).strip().lstrip("v")):
        out.append(int(x) if x.isdigit() else 0)
    return out + [0] * (3 - len(out))


def newer(latest: str, current: str) -> bool:
    return _parts(latest) > _parts(current)


def check(force: bool = False) -> dict:
    now = time.time()
    if not force and _cache["data"] and now - _cache["at"] < CACHE_TTL:
        data = dict(_cache["data"])
        data["cached"] = True
        return data

    base = {"current": VERSION, "cached": False}
    url = f"https://api.github.com/repos/{repo()}/releases/latest"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": f"tmp-preview/{VERSION}", "Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            payload = json.loads(r.read(200_000).decode("utf-8", "replace"))
    except Exception as exc:  # noqa: BLE001 - 网络错误要原样交给前端
        return {**base, "ok": False, "error": str(getattr(exc, "reason", exc))[:160]}

    latest = str(payload.get("tag_name") or "").lstrip("v")
    result = {
        **base,
        "ok": True,
        "latest": latest,
        "has_update": bool(latest) and newer(latest, VERSION),
        "name": payload.get("name") or payload.get("tag_name") or "",
        "url": payload.get("html_url") or "",
        "published_at": payload.get("published_at") or "",
        "notes": (payload.get("body") or "").strip()[:4000],
    }
    _cache["at"] = now
    _cache["data"] = result
    return result
