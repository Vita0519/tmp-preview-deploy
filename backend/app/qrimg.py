"""关于页二维码：赞赏码与群二维码，管理员上传，落在 DATA_DIR/branding。

命名：`qr-pay.<ext>` / `qr-group.<ext>`，每个槽只保留一份。
没上传时返回空，前端隐藏对应区块。
"""
from __future__ import annotations

import os
from pathlib import Path

ALLOWED = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}

MAX_BYTES = 2 * 1024 * 1024
NAMES = ("wechat", "alipay", "group")
LABELS = {"wechat": "微信赞赏", "alipay": "支付宝赞赏", "group": "群二维码"}
OFF_SUFFIX = ".off"
SOFT_DELETE_ERRORS = (Exception, SystemExit)


def dir_path() -> Path:
    from .config import DATA_DIR

    return Path(DATA_DIR) / "branding"


def _candidates(name: str) -> list[Path]:
    d = dir_path()
    if not d.is_dir():
        return []
    return [d / f"qr-{name}{ext}" for ext in ALLOWED if (d / f"qr-{name}{ext}").is_file()]


def _mtime(f: Path) -> int:
    try:
        return f.stat().st_mtime_ns
    except OSError:
        return 0


def find(name: str) -> Path | None:
    files = _candidates(name)
    if not files:
        return None
    return files[0] if len(files) == 1 else max(files, key=_mtime)


def current(name: str) -> dict | None:
    f = find(name)
    if f is None:
        return None
    try:
        st = f.stat()
    except OSError:
        return None
    return {
        "path": f,
        "url": f"/api/settings/qr/{name}?v={st.st_mtime_ns}",
        "mime": ALLOWED.get(f.suffix.lower(), "application/octet-stream"),
        "size": st.st_size,
    }


def save(name: str, filename: str, data: bytes) -> dict:
    if name not in NAMES:
        raise ValueError("未知的二维码类型")
    ext = Path(str(filename or "")).suffix.lower()
    if ext not in ALLOWED:
        raise ValueError("二维码只支持 png / jpg / webp")
    if not data:
        raise ValueError("上传的文件是空的")
    if len(data) > MAX_BYTES:
        raise ValueError(f"图片不能超过 {MAX_BYTES // 1024 // 1024}MB")

    d = dir_path()
    d.mkdir(parents=True, exist_ok=True)
    target = d / f"qr-{name}{ext}"
    target.write_bytes(data)
    remove(name, keep=target)
    return current(name) or {}


def remove(name: str, keep: Path | None = None) -> bool:
    d = dir_path()
    if not d.is_dir():
        return False
    kept = keep.name if keep is not None else None
    removed = False
    for f in _candidates(name):
        if kept is not None and f.name == kept:
            continue
        try:
            f.unlink()
            removed = True
            continue
        except SOFT_DELETE_ERRORS as exc:
            print(f"[qrimg] unlink {f.name} failed: {exc!r}"[:300])
        off = f.with_name(f.name + OFF_SUFFIX)
        try:
            if off.exists():
                off.unlink()
            os.replace(f, off)
            removed = True
        except SOFT_DELETE_ERRORS as exc:
            print(f"[qrimg] rename {f.name} failed: {exc!r}"[:300])
    for junk in d.glob(f"qr-{name}*{OFF_SUFFIX}"):
        try:
            junk.unlink()
        except SOFT_DELETE_ERRORS:
            pass
    return removed


def payload() -> dict:
    out: dict = {"max_kb": MAX_BYTES // 1024, "formats": ["png", "jpg", "webp"]}
    for name in NAMES:
        cur = current(name)
        out[name] = (
            {"url": cur["url"], "size": cur["size"], "label": LABELS[name]} if cur else None
        )
    return out
