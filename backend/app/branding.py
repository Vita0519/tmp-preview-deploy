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
OFF_SUFFIX = ".off"  # 删不掉时改成这个后缀，挪出 find() 的匹配范围


def dir_path() -> Path:
    from .config import DATA_DIR

    return Path(DATA_DIR) / "branding"


def _candidates() -> list[Path]:
    """目录里所有候选图标文件（正常情况下只有一个）。"""
    d = dir_path()
    if not d.is_dir():
        return []
    out = []
    for ext in ALLOWED:
        f = d / f"{STEM}{ext}"
        if f.is_file():
            out.append(f)
    return out


def _mtime(f: Path) -> int:
    """纳秒级 mtime，用来在同一秒内也能分出「谁是新写的」。"""
    try:
        return f.stat().st_mtime_ns
    except OSError:
        return 0


def find() -> Path | None:
    """当前生效的图标。

    万一目录里残留了多份（旧文件删不掉时会发生，比如环境开了删除保护或者
    文件被别的进程占着），取最新改过的那份，保证「换了图就是新图」。
    """
    files = _candidates()
    if not files:
        return None
    if len(files) == 1:
        return files[0]
    return max(files, key=_mtime)


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
        # 带上 mtime，换图之后浏览器不会继续用老缓存（用纳秒，同一秒里换两次也不会撞）
        "url": f"/site-icon?v={st.st_mtime_ns}",
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
    target = d / f"{STEM}{ext}"
    # 先落盘再清理：万一旧的删不掉，find() 会按 mtime 取最新这份，仍然是新图
    target.write_bytes(data)
    remove(keep=target)  # 只留一份：换了格式就把旧的删掉
    return current() or {}


def remove(keep: Path | None = None) -> bool:
    """删掉自定义图标，回到内置图标。

    删文件这件事可能失败：环境的删除保护会直接抛异常让 Python 侧接不住、
    文件也可能被浏览器/杀软占着。这里不能因为一个删不掉的文件把接口打成
    500，所以分两步走——先试 unlink，失败就改名成 `*.off` 挪出匹配范围，
    `find()` 自然就看不到它了。

    `keep` 留给 save() 用：刚写下去的那份别删。
    """
    d = dir_path()
    if not d.is_dir():
        return False
    kept = keep.name if keep is not None else None
    removed = False
    for f in _candidates():
        if kept is not None and f.name == kept:
            continue
        try:
            f.unlink()
            removed = True
            continue
        except Exception as exc:  # noqa: BLE001 - 删除保护抛的不是 OSError
            print(f"[branding] unlink {f.name} failed, falling back to rename: {exc!r}"[:400])
        try:
            f.rename(f.with_name(f.name + OFF_SUFFIX))
            removed = True
        except Exception as exc:  # noqa: BLE001
            print(f"[branding] rename {f.name} failed: {exc!r}"[:400])
    _sweep()  # 顺手清掉之前留下的 .off 残骸
    return removed


def _sweep() -> None:
    """清掉 `.off` 残骸，清不掉就算了，不影响功能。"""
    d = dir_path()
    if not d.is_dir():
        return
    for junk in d.glob(f"*{OFF_SUFFIX}"):
        try:
            junk.unlink()
        except Exception:  # noqa: BLE001
            pass


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
