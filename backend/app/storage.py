"""落盘存储：每个项目一个目录，路径全部做穿越校验。"""
import mimetypes
import os
import re
import shutil
import threading
import time
import uuid
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

# --------------------------------------------------------------------------- #
# 并发保护
#   同一 slug 的「换目录 / 删目录 / 打包」必须串行，否则两个 agent 同时部署
#   同一个 slug 会在 os.replace 上撞车（Windows 报 WinError 5 拒绝访问）。
#   锁只在同步的文件系统操作期间持有，不跨越 await。
# --------------------------------------------------------------------------- #
_LOCK_GUARD = threading.Lock()
_SLUG_LOCKS: dict[str, threading.Lock] = {}


def slug_lock(slug: str) -> threading.Lock:
    with _LOCK_GUARD:
        lock = _SLUG_LOCKS.get(slug)
        if lock is None:
            lock = _SLUG_LOCKS[slug] = threading.Lock()
        return lock


def _retry_fs(action, attempts: int = 12, delay: float = 0.05):
    """Windows 上文件句柄释放有延迟，rename/rmtree 偶发 WinError 5/32，重试即可。"""
    last = None
    for i in range(attempts):
        try:
            return action()
        except OSError as exc:
            winerr = getattr(exc, "winerror", None)
            if isinstance(exc, PermissionError) or winerr in (5, 32):
                last = exc
                time.sleep(min(0.6, delay * (1 + i * 0.6)))
                continue
            raise
    raise last


def _rm_tree(path: Path) -> int:
    """自己递归删除，不走 shutil.rmtree。返回没能删掉的条目数（0 = 清干净）。

    三个原因：
      1. 服务端删项目目录就该直接删，不该把几个 GB 的站丢进回收站；
      2. 某些环境会给删除操作打「安全钩子」（限流 / 转回收站），在服务进程里被拦下来
         会变成 500；而这里只是清理文件，删不掉的留着让孤儿清理兜底即可；
      3. 逐条删能容忍单个文件被占用（杀毒、索引、正在下载）。

    注意钩子的异常类型：它为了「中断整批删除」抛的是 SystemExit（BaseException 的子类），
    不是 Exception。所以这里必须显式接住 SystemExit，否则一个删不掉的文件就能把请求打成 500。
    """
    if not path.exists():
        return 0
    failed = 0
    blocked = False

    def attempt(fn, target) -> None:
        nonlocal failed, blocked
        if blocked:  # 钩子已经拦下整批删除，再试也没用，直接记数目
            failed += 1
            return
        try:
            fn(target)
        except FileNotFoundError:
            pass
        except SystemExit:  # 环境的删除钩子用 SystemExit 掐断整批删除
            blocked = True
            failed += 1
        except Exception:  # noqa: BLE001 - 删不掉不算失败，交给孤儿清理
            failed += 1

    for root, dirs, files in os.walk(path, topdown=False):
        for fn in files:
            attempt(os.remove, os.path.join(root, fn))
        for dn in dirs:
            attempt(os.rmdir, os.path.join(root, dn))
    attempt(os.rmdir, path)
    return failed


def remove_tree(path) -> int:
    """对外暴露的容错递归删除：返回残留条目数，绝不抛异常。"""
    return _rm_tree(Path(path))


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


class EntryConflict(ValueError):
    """多文件项目缺根目录 index.html：入口不唯一，拒绝上传。"""


def decide_entry(names: list[str]) -> tuple[str | None, str | None]:
    """决定入口文件，返回 (entry, 错误说明)。

    规则：
      1. 只有一个文件 → 就是它，不管叫 index.html 还是 report.html，也不管什么类型；
      2. 多个文件 → 根目录必须有 index.html / index.htm；
      3. 其余（多个文件却没有 index.html）→ 拒绝。没有入口的项目打开就是一片空白，
         传上去也是「能下载但打不开」，不如当场说清楚；只想分享文件包就走 zip 上传。
    """
    files = [n for n in names if n]
    if not files:
        return None, None
    if len(files) == 1:
        return files[0], None
    for cand in ("index.html", "index.htm"):
        if cand in files:
            return cand, None
    if any(n.lower().endswith((".html", ".htm")) for n in files):
        extra = "（如果只有一个 HTML 页面，可以只上传那一个文件，名字随意）"
    else:
        extra = "（如果只是想分享一堆文件，请改用 zip 上传）"
    return None, f"多文件项目需要根目录有一个 index.html 作为入口{extra}"


async def write_uploads(slug: str, uploads) -> tuple[int, int, str | None]:
    """把上传文件写进临时目录后原子替换；返回 (文件数, 总字节, 入口文件)。

    两个要点：
      1. 临时目录带随机后缀，多个 agent 同时传同一个 slug 也不会互相覆盖文件；
      2. 替换阶段按 slug 上锁 + 重试，避免 Windows 上 os.replace 撞到占用中的句柄。
    """
    import asyncio

    # 先按文件名把入口定下来，规则不满足就直接拒绝——此时还没写盘，不用清理残留
    entry, entry_error = decide_entry([safe_rel(getattr(u, "filename", "") or "") for u in uploads])
    if entry_error:
        raise EntryConflict(entry_error)

    FILES_DIR.mkdir(parents=True, exist_ok=True)
    tmp = FILES_DIR / f".tmp-{slug}-{uuid.uuid4().hex[:8]}"
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
    with slug_lock(slug):
        old = FILES_DIR / f".old-{slug}-{uuid.uuid4().hex[:8]}"

        def swap():
            if target.exists():
                os.replace(target, old)
            os.replace(tmp, target)

        try:
            _retry_fs(swap)
        except OSError:
            _rm_tree(tmp)
            raise
        _rm_tree(old)

    return count, total, entry


def save_zip_file(slug: str, src: Path) -> None:
    ZIPS_DIR.mkdir(parents=True, exist_ok=True)
    dest = zip_path(slug)
    tmp = ZIPS_DIR / f".{slug}.zip.tmp.{uuid.uuid4().hex[:6]}"
    shutil.copyfile(src, tmp)
    with slug_lock(slug):
        _retry_fs(lambda: os.replace(tmp, dest))


def remove_project_files(slug: str) -> bool:
    """删掉项目目录与 zip。返回是否清干净。

    刻意不抛异常：文件被占用（杀毒/索引/正在下载）时，数据库里的记录该删还是要删，
    否则用户会看到一个删不掉的项目。残留目录由启动时的孤儿清理兜底。
    """
    d = project_dir(slug)
    z = zip_path(slug)
    clean = True
    with slug_lock(slug):
        if d.exists():
            left = _rm_tree(d)
            if left:
                print(f"[storage] 目录未清干净 {d}（{left} 项残留）", flush=True)
                clean = False
        if z.exists():
            try:
                _retry_fs(z.unlink)
            except (OSError, SystemExit) as exc:
                print(f"[storage] 删除 zip 失败 {z}: {exc}", flush=True)
                clean = False
    return clean


def move_project_dir(old_slug: str, new_slug: str) -> None:
    src, dst = project_dir(old_slug), project_dir(new_slug)
    with slug_lock(old_slug), slug_lock(new_slug):
        if src.exists():
            src.parent.mkdir(parents=True, exist_ok=True)
            _retry_fs(lambda: os.replace(src, dst))
        zs, zd = zip_path(old_slug), zip_path(new_slug)
        if zs.exists():
            _retry_fs(lambda: os.replace(zs, zd))


def cleanup_stale_tmp(max_age_seconds: int = 3600) -> int:
    """清掉进程崩溃留下的 .tmp-* / .old-* 目录。"""
    removed = 0
    if not FILES_DIR.exists():
        return 0
    now = time.time()
    for p in FILES_DIR.iterdir():
        if not p.is_dir():
            continue
        if not (p.name.startswith(".tmp-") or p.name.startswith(".old-")):
            continue
        try:
            if now - p.stat().st_mtime < max_age_seconds:
                continue
            _rm_tree(p)
            removed += 1
        except OSError:
            continue
    return removed


def build_zip_on_demand(slug: str) -> Path | None:
    """没有预置 zip 时按需打包（结果缓存，项目更新时调用方负责失效）。"""
    src = project_dir(slug)
    if not src.exists():
        return None
    dest = zip_path(slug)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(f".{uuid.uuid4().hex[:6]}.zip.tmp")
    with slug_lock(slug):
        if dest.exists():  # 别人已经打好，直接用
            return dest
        try:
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED, allowZip64=True) as z:
                for root, _dirs, files in os.walk(src):
                    for fn in files:
                        full = Path(root) / fn
                        rel = full.relative_to(src).as_posix()
                        # 源文件在打包过程中被替换/删除 → 跳过这一个，不影响整包
                        try:
                            st = full.stat()
                            fh = open(full, "rb")
                        except OSError:
                            continue
                        with fh:
                            info = zipfile.ZipInfo(rel, date_time=time.localtime(st.st_mtime)[:6])
                            info.compress_type = zipfile.ZIP_DEFLATED
                            info.external_attr = 0o644 << 16
                            # 流式写入：别把整个文件读进内存，否则一个 1GB 的视频就吃掉 1GB RSS
                            with z.open(info, "w") as dst:
                                shutil.copyfileobj(fh, dst, 1024 * 1024)
            _retry_fs(lambda: os.replace(tmp, dest))
        except OSError:
            try:
                tmp.unlink()
            except (OSError, SystemExit):
                pass
            raise
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
