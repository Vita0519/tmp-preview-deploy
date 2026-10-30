"""站点图标：允许管理员上传自己的 favicon，覆盖内置的沙漏套装。

文件落在 `DATA_DIR/branding/site-icon.<ext>`，只保留一份（换格式时旧的先删）。
没有上传时全站继续用 `frontend/public` 里那套生成的图标。
"""
from __future__ import annotations

from pathlib import Path

# 允许的类型与对应 MIME
ALLOWED = {
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}

MAX_BYTES = 512 * 1024  # 512KB 足够放一个 1024 的画布图标了
STEM = "site-icon"


def dir_path() -> Path:
    from .config import DATA_DIR

    return Path(DATA_DIR) / "branding"


def find() -> Path | None:
    d = dir_path()
    if not d.is_dir():
        return None
    for ext in ALLOWED:
        f = d / f"{STEM}{ext}"
        if f.is_file():
            return f
    return None


def current() -> dict | None:
    """当前自定义图标的信息；没上传返回 None。"""
    f = find()
    if f is None:
        return None
    try:
        st = f.stat()
    except OSError:
        return None
    ext = f.suffix.lower()
    return {
        "path": f,
        # 带上 mtime，换图之后浏览器不会继续用老缓存
        "url": f"/site-icon?v={int(st.st_mtime)}",
        "ext": ext.lstrip("."),
        "mime": ALLOWED.get(ext, "application/octet-stream"),
        "size": st.st_size,
    }


def save(filename: str, data: bytes) -> dict:
    """保存上传的图标，返回新图标信息。类型/大小不合法时抛 ValueError。"""
    ext = Path(str(filename or "")).suffix.lower()
    if ext not in ALLOWED:
        raise ValueError("图标格式只支持 png / svg / ico / jpg / webp")
    if not data:
        raise ValueError("上传的文件是空的")
    if len(data) > MAX_BYTES:
        raise ValueError(f"图标不能超过 {MAX_BYTES // 1024}KB")
    if ext == ".svg":
        head = data[:512].lstrip().lower()
        if b"<svg" not in head and b"<?xml" not in head:
            raise ValueError("这个文件看起来不是有效的 SVG")

    d = dir_path()
    d.mkdir(parents=True, exist_ok=True)
    remove()  # 只留一份：换了格式就把旧的删掉
    target = d / f"{STEM}{ext}"
    target.write_bytes(data)
    return current() or {}


def remove() -> bool:
    """删掉自定义图标，回到内置图标。"""
    d = dir_path()
    if not d.is_dir():
        return False
    removed = False
    for ext in ALLOWED:
        f = d / f"{STEM}{ext}"
        if not f.exists():
            continue
        try:
            f.unlink()
            removed = True
        except OSError:
            pass
    return removed


def payload() -> dict:
    """给设置页 / 门户 / 前端用的图标信息，所有接口共用同一个形状。

    没上传时也返回一份（custom=False、url 为空），前端据此回落到内置图标。
    """
    cur = current()
    info = {
        "custom": bool(cur),
        "url": "",
        "ext": "",
        "size": 0,
        "max_kb": MAX_BYTES // 1024,
        "formats": ["png", "svg", "ico", "jpg", "webp"],
    }
    if cur:
        info.update({"url": cur["url"], "ext": cur["ext"], "size": cur["size"]})
    return info
