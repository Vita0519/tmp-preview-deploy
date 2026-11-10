"""全站备份与恢复。

备份 = 一个 zip：数据库快照 + 项目文件 + zip 包 + 站点图标 + manifest。
数据库用 sqlite3 的在线备份 API 拷一份一致的快照，WAL 里没落盘的事务也会带上，
不能直接复制 .sqlite3 文件（正写着会拷到半截）。

恢复 = 校验 → 解压到临时目录 → 把现网数据整体挪到 `.backup-before-restore-<时间>/`
→ 换上新数据 → 跑一遍迁移 → 清进程内缓存。**旧数据永远留在那里**，恢复坏了还能手工挪回来。
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
import threading
import time
import zipfile
from pathlib import Path

from . import config, theme

MANIFEST = "manifest.json"
LOCK = threading.Lock()

# 表结构里「迁移能自己补上」的列：老备份缺这些没关系，restore 完 init_db 会加。
MIGRATABLE_COLS = {
    "projects": {"collection_id"},
    "users": {"key_label", "key_created_at", "key_last_used_at", "key_uses"},
}

# 新代码会用到的列。缺了迁不回来的，说明这个包比「上一个版本」还老，
# 提前拒绝（不动现网），而不是换上去之后每个接口都 500。
REQUIRED_COLS = {
    "projects": {
        "id", "slug", "title", "owner_id", "kind", "visibility", "allow_download",
        "expire_action", "expires_at", "status", "views", "downloads",
        "created_at", "updated_at",
    },
    "users": {
        "id", "username", "display_name", "role", "password_hash", "api_key",
        "active", "created_at",
    },
}


def now_ms() -> int:
    return int(time.time() * 1000)


def _counts(conn) -> dict:
    def one(sql: str) -> int:
        try:
            return int(conn.execute(sql).fetchone()[0])
        except sqlite3.Error:
            return 0

    return {
        # 只数活着的项目：删掉的项目记录还留在表里（软删），数进去会跟界面对不上
        "projects": one("SELECT COUNT(*) FROM projects WHERE status='active'"),
        "users": one("SELECT COUNT(*) FROM users"),
        "collections": one("SELECT COUNT(*) FROM collections"),
        "tags": one("SELECT COUNT(*) FROM tags"),
    }


def build_zip() -> Path:
    """打一个全站备份包，返回 zip 路径（调用方负责删）。"""
    with LOCK:
        work = Path(tempfile.mkdtemp(prefix="pvbackup-"))
        snap = work / "db.sqlite3"
        src = sqlite3.connect(str(config.DB_PATH), timeout=15)
        try:
            dst = sqlite3.connect(str(snap))
            try:
                src.backup(dst)
                counts = _counts(dst)
            finally:
                dst.close()
        finally:
            src.close()

        (work / MANIFEST).write_text(
            json.dumps(
                {
                    "app": "tmp-preview-deploy",
                    "format": 1,
                    "created_at": now_ms(),
                    "counts": counts,
                    "site_title": _site_title(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        out = Path(tempfile.mkdtemp(prefix="pvbackupzip-")) / f"preview-backup-{time.strftime('%Y%m%d-%H%M%S')}.zip"
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            z.write(snap, "db.sqlite3")
            z.write(work / MANIFEST, MANIFEST)
            for folder, prefix in (
                (config.FILES_DIR, "projects"),
                (config.ZIPS_DIR, "zips"),
                (Path(config.DATA_DIR) / "branding", "branding"),
            ):
                if not folder.is_dir():
                    continue
                for p in folder.rglob("*"):
                    if p.is_file():
                        z.write(p, str(Path(prefix) / p.relative_to(folder)))
        _rm_tree(work)
        return out


def _site_title() -> str:
    try:
        from .db import get_setting

        return get_setting("site_title") or config.SITE_TITLE
    except Exception:  # noqa: BLE001 - 备份不能因为一个标题失败
        return config.SITE_TITLE


def _preflight(conn) -> None:
    """换数据之前先看这个库能不能被当前版本用。

    只差 collection_id / key_* 这类「迁移能补」的列 → 放行，restore 完会自动补；
    连 kind / status 这种都没有 → 说明包比上一个版本还老，直接拒绝，别把现网换了再炸。
    """
    problems: list[str] = []
    for table, want in REQUIRED_COLS.items():
        try:
            have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        except sqlite3.Error as exc:
            problems.append(f"{table}（{exc}）")
            continue
        missing = want - have - MIGRATABLE_COLS.get(table, set())
        if missing:
            problems.append(f"{table} 缺少 {', '.join(sorted(missing))}")
    if problems:
        raise ValueError(
            "这个备份比当前版本老太多，恢复后会缺字段："
            + "；".join(problems)
            + "。请先用保存这个备份时的版本升级到新版，再重新备份后恢复。"
        )


def inspect(zip_path: Path) -> dict:
    """看一个备份包里有什么，恢复前先给用户确认。"""
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        if "db.sqlite3" not in names:
            raise ValueError("这个 zip 里没有 db.sqlite3，不像是本站的备份")
        info = {"db": True, "files": 0, "zips": 0, "branding": 0, "manifest": None}
        for n in names:
            if n.startswith("projects/"):
                info["files"] += 1
            elif n.startswith("zips/"):
                info["zips"] += 1
            elif n.startswith("branding/"):
                info["branding"] += 1
        if MANIFEST in names:
            try:
                info["manifest"] = json.loads(z.read(MANIFEST).decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                info["manifest"] = None
        return info


def restore(zip_path: Path) -> dict:
    """用备份包覆盖现网数据。返回 {restored, backup_dir, counts}。"""
    with LOCK:
        info = inspect(zip_path)  # 结构不对直接抛 ValueError，不动现网
        tmp = Path(tempfile.mkdtemp(prefix="pvrestore-"))
        try:
            with zipfile.ZipFile(zip_path) as z:
                for member in z.namelist():
                    # 防 zip slip：只接受相对路径，且落点在 tmp 内
                    dest = (tmp / member).resolve()
                    if not str(dest).startswith(str(tmp.resolve())):
                        raise ValueError("备份包里有可疑路径")
                z.extractall(tmp)

            db_file = tmp / "db.sqlite3"
            conn = sqlite3.connect(str(db_file))
            try:
                tables = {r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()}
                missing = {"projects", "users"} - tables
                if missing:
                    raise ValueError(f"备份里的数据库缺少表：{', '.join(sorted(missing))}")
                _preflight(conn)
                counts = _counts(conn)
            finally:
                conn.close()

            stamp = time.strftime("%Y%m%d-%H%M%S")
            safety = Path(config.DATA_DIR) / f".backup-before-restore-{stamp}"
            safety.mkdir(parents=True, exist_ok=True)

            # 内存里还没落库的访问计数属于「旧世界」，必须先写回旧库再搬家，
            # 否则换库之后 flush 会按老项目 id 去改新库的计数。
            try:
                from . import views

                views.flush()
            except Exception as exc:  # noqa: BLE001
                print(f"[backup] 恢复前刷新访问计数失败：{exc}", flush=True)

            targets = [
                (config.DB_PATH, "db.sqlite3"),
                (config.FILES_DIR, "projects"),
                (config.ZIPS_DIR, "zips"),
                (Path(config.DATA_DIR) / "branding", "branding"),
                # WAL 的两个侧文件必须跟着走：留下旧 -wal，SQLite 会把它当成
                # 新库的日志往下重放，恢复完就是一堆错乱数据
                (Path(str(config.DB_PATH) + "-wal"), "db.sqlite3-wal"),
                (Path(str(config.DB_PATH) + "-shm"), "db.sqlite3-shm"),
            ]
            # 先 checkpoint 把 -wal 掏空，再搬
            try:
                conn = sqlite3.connect(str(config.DB_PATH), timeout=10)
                try:
                    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                finally:
                    conn.close()
            except sqlite3.Error as exc:
                print(f"[backup] 恢复前 checkpoint 失败：{exc}", flush=True)
            # 1) 现网数据先挪进安全区
            for live, name in targets:
                if live.exists():
                    dest = safety / name
                    if dest.exists():
                        shutil.rmtree(dest, ignore_errors=True) if dest.is_dir() else dest.unlink()
                    shutil.move(str(live), str(dest))
            # 2) 备份包里的数据换上去
            for live, name in targets:
                src = tmp / name
                if src.exists():
                    live.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), str(live))
                elif name in ("projects", "zips"):
                    live.mkdir(parents=True, exist_ok=True)

            # 3) 进程内的缓存（配色等）跟着换
            theme.reset_cache()

            # 4) 老备份包里的库是旧结构：恢复完必须立刻跑一遍迁移。
            #    不然新代码去查 collection_id / key_label 会直接 500，
            #    得等重启（启动时才 init_db）才正常——「恢复成功但打不开」就是这么来的。
            migrated, migrate_error = True, None
            try:
                from .db import init_db

                init_db()
            except Exception as exc:  # noqa: BLE001 - 迁移失败也要把话说清楚，别吞
                migrated, migrate_error = False, str(exc)
                print(f"[backup] 恢复后迁移失败：{exc}", flush=True)

            # 迁移会改数据（无主项目收归管理员、agent 角色改名），计数按迁移后的库再数一遍
            try:
                conn = sqlite3.connect(str(config.DB_PATH), timeout=10)
                try:
                    counts = _counts(conn)
                finally:
                    conn.close()
            except sqlite3.Error as exc:
                print(f"[backup] 恢复后重新计数失败：{exc}", flush=True)

            return {
                "ok": True,
                "counts": counts,
                "backup_dir": str(safety),
                "files": info["files"],
                "zips": info["zips"],
                "migrated": migrated,
                "migrate_error": migrate_error,
            }
        finally:
            _rm_tree(tmp)


def _rm_tree(path: Path) -> bool:
    """删一棵树，删不掉也绝不把调用方搞挂。

    开发机上的安全删除钩子遇到「一次删太多文件」会抛 SystemExit（不是 Exception），
    真实部署里没有这层；所以这里统一兜住，失败就返回 False 让上层降级处理。
    """
    try:
        shutil.rmtree(path, ignore_errors=True)
        return True
    except (Exception, SystemExit) as exc:  # noqa: BLE001
        print(f"[backup] 删不掉 {path.name}：{exc}", flush=True)
        return False


def cleanup_old_safety(keep: int = 3) -> int:
    """安全区只留最近几份，免得磁盘越攒越满。

    删不掉的（被宿主守卫拦住）改名丢进 `.trash/`，至少不再算进安全区，
    磁盘告警好过悄悄占满。
    """
    data = Path(config.DATA_DIR)
    if not data.is_dir():
        return 0
    dirs = sorted(
        [p for p in data.glob(".backup-before-restore-*") if p.is_dir()],
        key=lambda p: p.name,
        reverse=True,
    )
    trash = data / ".trash"
    n = 0
    for d in dirs[keep:]:
        if _rm_tree(d):
            n += 1
            continue
        try:
            trash.mkdir(parents=True, exist_ok=True)
            d.rename(trash / d.name)
            print(f"[backup] {d.name} 删不掉，已移到 .trash/，请手工清理", flush=True)
        except OSError as exc:
            print(f"[backup] 连改名都失败 {d.name}：{exc}", flush=True)
        n += 1
    return n
