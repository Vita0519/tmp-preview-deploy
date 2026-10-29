"""落盘存储：每个项目一个目录，路径全部做穿越校验。"""
import mimetypes
import os
import re
import shutil
import time
import zipfile
from pathlib import Path

from .config import FILES_DIR, ZIPS_DIR

mimetypes.add_type("application/wasm", ".wasm")
mimetypes.add_type("model/gltf-binary", ".glb")
mimetypes.add_type("model/gltf+json", ".gltf")
mimetypes.add_type("image/avif", ".avif")
mimetypes.add_type("application/javascript", ".mjs")
mimetypes.add_type("text/html", ".htm")

TEXTUAL = {".html", ".htm", ".css", ".js", ".mjs", ".json", ".svg", ".txt", ".xml", ".map"}


def slugify(name: str) -> str:
    raw = str(name or "").strip()
    s = re.sub(r"[^a-z0-9\-_]+", "-", raw.lower()).strip("-")
    if not s:
        h = 0
        for ch in raw:
            h = (h * 31 + ord(ch)) % 0xFFFFFF
        s = "p-" + format(h, "x")
    return s[:60]


def safe_rel(name: str) -> str:
    p = str(name or "").replace("\\", "/").lstrip("/")
    parts = [x for x in p.split("/") if x not in ("", ".", "..")]
    out = "/".join(parts)
    return out[:400]


def media_type(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    mt, _ = mimetypes.guess_type(path)
    if ext in (".html", ".htm"):
        return "text/html; charset=utf-8"
    if ext in (".js", ".mjs"):
        return "application/javascript; charset=utf-8"
    if ext == ".css":
        return "text/css; charset=utf-8"
    if ext == ".json":
        return "application/json; charset=utf-8"
    if ext == ".svg":
        return "image/svg+xml"
    return mt or "application/octet-stream"


def project_dir(slug: str) -> Path:
    return FILES_DIR / slug


def zip_path(slug: str) -> Path:
    return ZIPS_DIR / f"{slug}.zip"


def resolve_in_project(slug: str, rel: str) -> Path | None:
    """把请求路径解析到项目目录内，越界返回 None。"""
    base = project_dir(slug).resolve()
    target = (base / safe_rel(rel)).resolve()
    if target != base and base not in target.parents:
        return None
    return target


async def write_uploads(slug: str, uploads) -> tuple[int, int, str | None]:
    """把上传文件写进临时目录后原子替换；返回 (文件数, 总字节, 入口文件)。"""
    import asyncio

    FILES_DIR.mkdir(parents=True, exist_ok=True)
    tmp = FILES_DIR / f".tmp-{slug}"
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)

    count = 0
    total = 0
    names: list[str] = []
    for up in uploads:
        rel = safe_rel(getattr(up, "filename", "") or "")
        if not rel:
            continue
        dest = tmp / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        size = 0
        with open(dest, "wb") as fh:
            while True:
                chunk = await up.read(1024 * 512)
                if not chunk:
                    break
                fh.write(chunk)
                size += len(chunk)
        count += 1
        total += size
        names.append(rel)
    await asyncio.sleep(0)

    target = project_dir(slug)
    old = FILES_DIR / f".old-{slug}"
    if old.exists():
        shutil.rmtree(old, ignore_errors=True)
    if target.exists():
        os.replace(target, old)
    os.replace(tmp, target)
    if old.exists():
        shutil.rmtree(old, ignore_errors=True)

    entry = "index.html" if "index.html" in names else ("index.htm" if "index.htm" in names else None)
    return count, total, entry


def save_zip_file(slug: str, src: Path) -> None:
    ZIPS_DIR.mkdir(parents=True, exist_ok=True)
    dest = zip_path(slug)
    tmp = ZIPS_DIR / f".{slug}.zip.tmp"
    shutil.copyfile(src, tmp)
    os.replace(tmp, dest)


def remove_project_files(slug: str) -> None:
    d = project_dir(slug)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    z = zip_path(slug)
    if z.exists():
        try:
            z.unlink()
        except OSError:
            pass


def move_project_dir(old_slug: str, new_slug: str) -> None:
    src, dst = project_dir(old_slug), project_dir(new_slug)
    if src.exists():
        src.parent.mkdir(parents=True, exist_ok=True)
        os.replace(src, dst)
    zs, zd = zip_path(old_slug), zip_path(new_slug)
    if zs.exists():
        os.replace(zs, zd)


def build_zip_on_demand(slug: str) -> Path | None:
    """没有预置 zip 时按需打包（结果缓存，项目更新时调用方负责失效）。"""
    src = project_dir(slug)
    if not src.exists():
        return None
    dest = zip_path(slug)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".zip.tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED, allowZip64=True) as z:
        for root, _dirs, files in os.walk(src):
            for fn in files:
                full = Path(root) / fn
                rel = full.relative_to(src).as_posix()
                st = full.stat()
                info = zipfile.ZipInfo(rel, date_time=time.localtime(st.st_mtime)[:6])
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                with open(full, "rb") as fh:
                    z.writestr(info, fh.read())
    os.replace(tmp, dest)
    return dest


def file_list(slug: str, limit: int = 500) -> list[dict]:
    base = project_dir(slug)
    out: list[dict] = []
    if not base.exists():
        return out
    for root, _dirs, files in os.walk(base):
        for fn in files:
            full = Path(root) / fn
            try:
                st = full.stat()
            except OSError:
                continue
            out.append(
                {
                    "path": full.relative_to(base).as_posix(),
                    "size": st.st_size,
                    "mtime": int(st.st_mtime * 1000),
                }
            )
            if len(out) >= limit:
                return out
    out.sort(key=lambda x: x["path"])
    return out
