"""后台任务：访问计数批量落库 + 到期清理 + 孤儿目录清理。"""
import asyncio
import time

from . import storage, tagspec, views
from .db import db, log_event, prune_events

TICK_FLUSH = 3.0
TICK_SWEEP = 60.0
ORPHAN_EVERY = 30  # 每 30 轮（约 30 分钟）扫一次没人认领的目录


def sweep() -> dict:
    now = int(time.time() * 1000)
    with db() as conn:
        rows = conn.execute(
            "SELECT id, slug, title, expire_action FROM projects "
            "WHERE status='active' AND expires_at IS NOT NULL AND expires_at<=?",
            (now,),
        ).fetchall()
    blocked, purged = 0, 0
    for r in rows:
        if r["expire_action"] == "delete":
            storage.remove_project_files(r["slug"])
            views.reset(r["id"])
            with db() as conn:
                conn.execute("DELETE FROM projects WHERE id=?", (r["id"],))
                tagspec.prune_orphans(conn)  # 项目被删，它独有的标签一并回收
            log_event("expire_delete", None, r["id"], r["slug"], slug=r["slug"], title=r["title"])
            purged += 1
        else:
            with db() as conn:
                conn.execute("UPDATE projects SET status='expired' WHERE id=?", (r["id"],))
            log_event("expire_block", None, r["id"], r["slug"], slug=r["slug"], title=r["title"])
            blocked += 1
    return {"blocked": blocked, "purged": purged}


def sweep_orphans(grace_seconds: int = 600) -> int:
    """删掉数据库里已经没有记录的目录。

    删除接口在文件被占用时会让记录先走、目录留下，这里负责收尾；
    宽限期避免把「刚上传完、还没提交事务」的目录误删。
    """
    with db() as conn:
        known = {r["slug"] for r in conn.execute("SELECT slug FROM projects").fetchall()}
    removed = 0
    now = time.time()
    for p in storage.FILES_DIR.iterdir():
        if not p.is_dir() or p.name.startswith(".") or p.name in known:
            continue
        try:
            if now - p.stat().st_mtime < grace_seconds:
                continue
        except OSError:
            continue
        storage.remove_tree(p)
        removed += 1
    return removed


async def flush_loop(stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            views.flush()
        except Exception as exc:  # 计数失败不影响主流程
            print(f"[views] flush failed: {exc}", flush=True)
        try:
            await asyncio.wait_for(stop.wait(), timeout=TICK_FLUSH)
        except asyncio.TimeoutError:
            continue


async def sweep_loop(stop: asyncio.Event) -> None:
    rounds = 0
    while not stop.is_set():
        try:
            r = sweep()
            if r["blocked"] or r["purged"]:
                print(f"[expire] blocked={r['blocked']} purged={r['purged']}", flush=True)
        except Exception as exc:
            print(f"[expire] sweep failed: {exc}", flush=True)
        rounds += 1
        if rounds % ORPHAN_EVERY == 0:
            try:
                gone = sweep_orphans()
                if gone:
                    print(f"[orphan] 清理无主目录 {gone} 个", flush=True)
                pruned = prune_events()
                if pruned:
                    print(f"[events] 清理过期日志 {pruned} 条", flush=True)
            except Exception as exc:
                print(f"[orphan] 清理失败: {exc}", flush=True)
        try:
            await asyncio.wait_for(stop.wait(), timeout=TICK_SWEEP)
        except asyncio.TimeoutError:
            continue
