"""定时自动备份：每天在设定的整点把全站备份写到 <DATA_DIR>/backups/，只留最近 N 份。

- 时间按服务器（容器）本地时区；docker-compose 里设 TZ=Asia/Shanghai 即按北京时间。
- backups/ 不进备份包，也不会被恢复挪走，否则备份会套娃、恢复会把自己的后路删了。
"""
from __future__ import annotations

import asyncio
import re
import shutil
import threading
import time
from pathlib import Path

from . import backup, config
from .db import get_setting, set_setting

DIR = Path(config.DATA_DIR) / "backups"
NAME_RE = re.compile(r"^auto-\d{8}-\d{6}\.zip$")
_RUN = threading.Lock()
TICK = 300  # 每 5 分钟看一眼是不是到点了


def _int(raw: object, lo: int, hi: int, default: int) -> int:
    try:
        n = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return n if lo <= n <= hi else default


def conf() -> dict:
    return {
        "enabled": get_setting("auto_backup_enabled", "0") == "1",
        "hour": _int(get_setting("auto_backup_hour", "3"), 0, 23, 3),
        "keep": _int(get_setting("auto_backup_keep", "7"), 1, 60, 7),
    }


def save_conf(payload: dict) -> dict:
    if "enabled" in payload:
        set_setting("auto_backup_enabled", "1" if payload["enabled"] else "0")
    if "hour" in payload:
        set_setting("auto_backup_hour", str(_int(payload["hour"], 0, 23, 3)))
    if "keep" in payload:
        set_setting("auto_backup_keep", str(_int(payload["keep"], 1, 60, 7)))
    c = conf()
    prune(c["keep"])
    return c


def list_files() -> list[dict]:
    if not DIR.is_dir():
        return []
    out = []
    for p in DIR.iterdir():
        if p.is_file() and NAME_RE.match(p.name):
            st = p.stat()
            out.append({"name": p.name, "size": st.st_size, "at": int(st.st_mtime * 1000)})
    return sorted(out, key=lambda x: x["name"], reverse=True)


def path_of(name: str) -> Path | None:
    if not NAME_RE.match(str(name or "")):
        return None
    p = DIR / name
    return p if p.is_file() else None


def prune(keep: int) -> int:
    n = 0
    for f in list_files()[keep:]:
        try:
            (DIR / f["name"]).unlink()
            n += 1
        except OSError as exc:
            print(f"[autobackup] 删不掉 {f['name']}：{exc}", flush=True)
    return n


def status() -> dict:
    files = list_files()
    return {
        **conf(),
        "last_at": _int(get_setting("auto_backup_last_at", "0"), 0, 1 << 62, 0),
        "last_error": get_setting("auto_backup_last_error", ""),
        "server_time": time.strftime("%Y-%m-%d %H:%M %Z"),
        "files": files,
        "total_size": sum(f["size"] for f in files),
        "disk_free": shutil.disk_usage(str(Path(config.DATA_DIR))).free if Path(config.DATA_DIR).exists() else 0,
    }


def run_now() -> dict:
    if not _RUN.acquire(blocking=False):
        raise RuntimeError("已有一份自动备份正在进行")
    try:
        name = time.strftime("auto-%Y%m%d-%H%M%S.zip")
        try:
            p = backup.build_zip(DIR / name)
        except Exception as exc:  # noqa: BLE001
            set_setting("auto_backup_last_error", f"{time.strftime('%m-%d %H:%M')} {exc}"[:300])
            raise
        set_setting("auto_backup_last_at", str(backup.now_ms()))
        set_setting("auto_backup_last_error", "")
        prune(conf()["keep"])
        return {"name": p.name, "size": p.stat().st_size}
    finally:
        _RUN.release()


def tick() -> None:
    c = conf()
    if not c["enabled"]:
        return
    lt = time.localtime()
    if lt.tm_hour != c["hour"]:
        return
    today = time.strftime("%Y%m%d", lt)
    if get_setting("auto_backup_last_day", "") == today:
        return
    set_setting("auto_backup_last_day", today)  # 先记再跑：失败也不在这一小时里反复重试
    r = run_now()
    print(f"[autobackup] 完成 {r['name']} {r['size']} bytes", flush=True)


async def loop(stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await asyncio.to_thread(tick)
        except Exception as exc:  # noqa: BLE001
            print(f"[autobackup] 失败：{exc}", flush=True)
        try:
            await asyncio.wait_for(stop.wait(), timeout=TICK)
        except asyncio.TimeoutError:
            continue
