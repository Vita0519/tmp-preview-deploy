"""访问计数：内存累加 + 周期批量落库（避免每次访问写盘）。"""
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from .config import TZ_NAME
from .db import connect

_lock = threading.Lock()
_buffer: dict[int, int] = {}
_downloads: dict[int, int] = {}


def bump(project_id: int, n: int = 1) -> None:
    if not project_id:
        return
    with _lock:
        _buffer[project_id] = _buffer.get(project_id, 0) + n


def bump_download(project_id: int) -> None:
    if not project_id:
        return
    with _lock:
        _downloads[project_id] = _downloads.get(project_id, 0) + 1


def pending() -> int:
    with _lock:
        return sum(_buffer.values()) + sum(_downloads.values())


def today() -> str:
    return datetime.now(ZoneInfo(TZ_NAME)).strftime("%Y-%m-%d")


def flush() -> int:
    """把缓冲写进 DB；返回落库的条数。"""
    with _lock:
        views, downloads = dict(_buffer), dict(_downloads)
        _buffer.clear()
        _downloads.clear()
    if not views and not downloads:
        return 0
    t = int(time.time() * 1000)
    day = today()
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        for pid, n in views.items():
            conn.execute(
                "UPDATE projects SET views = views + ?, last_viewed_at = ? WHERE id = ?",
                (n, t, pid),
            )
            conn.execute(
                "INSERT INTO daily_views(project_id, day, count) VALUES(?,?,?) "
                "ON CONFLICT(project_id, day) DO UPDATE SET count = count + excluded.count",
                (pid, day, n),
            )
        for pid, n in downloads.items():
            conn.execute("UPDATE projects SET downloads = downloads + ? WHERE id = ?", (n, pid))
        conn.execute("COMMIT")
    except Exception:
        # 写失败就把计数还回缓冲，不丢数据
        with _lock:
            for pid, n in views.items():
                _buffer[pid] = _buffer.get(pid, 0) + n
            for pid, n in downloads.items():
                _downloads[pid] = _downloads.get(pid, 0) + n
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        conn.close()
    return len(views) + len(downloads)


def reset(project_id: int) -> None:
    with _lock:
        _buffer.pop(project_id, None)
