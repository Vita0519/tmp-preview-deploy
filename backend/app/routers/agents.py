"""成员（Agent）管理：每个 agent 有自己的 API Key，只能看到自己的项目。"""
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request

from ..db import db, log_event, tx
from ..security import (
    ROLES,
    admin_user,
    hash_password,
    new_api_key,
    norm_role,
    now_ms,
    user_by_id,
)
from ..storage import remove_project_files

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("")
def list_agents(limit: int = 0, offset: int = 0, user: dict = Depends(admin_user)):
    """成员列表。limit=0 表示不分页，返回全部（CLI 和老调用方要的就是全量）。"""
    sql = (
        "SELECT u.*, "
        "(SELECT COUNT(*) FROM projects p WHERE p.owner_id=u.id AND p.status<>'deleted') projects, "
        "(SELECT COUNT(*) FROM projects p WHERE p.owner_id=u.id AND p.status='active' "
        " AND (p.expires_at IS NULL OR p.expires_at>?)) online, "
        "(SELECT COALESCE(SUM(p.views),0) FROM projects p WHERE p.owner_id=u.id) views "
        "FROM users u "
        # 末尾补 u.id：同一毫秒建的两个账号光按 created_at 排是不稳定的，翻页会重复或漏人
        "ORDER BY u.role='admin' DESC, u.created_at, u.id"
    )
    skip = max(0, offset)
    with db() as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        args: list = [now_ms()]
        if limit > 0:
            sql += " LIMIT ? OFFSET ?"
            args += [limit, skip]
        rows = conn.execute(sql, args).fetchall()
    return {
        "total": total,
        "limit": limit,
        "offset": skip,
        "items": [
            {
                "id": r["id"],
                "username": r["username"],
                "display_name": r["display_name"] or r["username"],
                "role": r["role"],
                "active": bool(r["active"]),
                "created_at": r["created_at"],
                "last_login_at": r["last_login_at"],
                "projects": r["projects"],
                "online": r["online"],
                "views": r["views"],
                "api_key_tail": (r["api_key"] or "")[-6:],
                "key_label": r["key_label"] or r["username"],
                "key_created_at": r["key_created_at"],
                "key_last_used_at": r["key_last_used_at"],
                "key_uses": r["key_uses"] or 0,
            }
            for r in rows
        ]
    }


@router.post("")
async def create_agent(request: Request, user: dict = Depends(admin_user)):
    body = await request.json()
    username = str(body.get("username") or "").strip().lower()
    if not re.match(r"^[a-z0-9_.-]{2,32}$", username):
        raise HTTPException(status_code=400, detail="账号需为 2-32 位小写字母/数字/._-")
    password = str(body.get("password") or "").strip() or secrets.token_urlsafe(8)
    display = str(body.get("display_name") or username).strip()[:40]
    role = body.get("role") if body.get("role") in ROLES else "publisher"
    # 一个账号只绑一个 agent：这把 key 的用途写清楚，方便以后审计
    key_label = str(body.get("key_label") or display).strip()[:40]
    key = new_api_key()
    with tx() as conn:
        if conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            raise HTTPException(status_code=409, detail="账号已存在")
        cur = conn.execute(
            "INSERT INTO users(username, display_name, role, password_hash, api_key, "
            "key_label, key_created_at, key_uses, active, created_at) "
            "VALUES(?,?,?,?,?,?,?,0,1,?)",
            (username, display, role, hash_password(password), key, key_label, now_ms(), now_ms()),
        )
        uid = cur.lastrowid
    log_event("agent_create", user["id"], None, f"{username} key={key_label}")
    return {"id": uid, "username": username, "password": password, "api_key": key, "key_label": key_label}


@router.patch("/{agent_id}")
async def patch_agent(agent_id: int, request: Request, user: dict = Depends(admin_user)):
    body = await request.json()
    sets: list[str] = []
    args: list = []
    out: dict = {}
    if "display_name" in body:
        sets.append("display_name=?")
        args.append(str(body["display_name"]).strip()[:40])
    if "active" in body:
        sets.append("active=?")
        args.append(1 if body["active"] else 0)
    if body.get("password"):
        pw = str(body["password"])
        if len(pw) < 6:
            raise HTTPException(status_code=400, detail="密码至少 6 位")
        sets.append("password_hash=?")
        args.append(hash_password(pw))
        out["password"] = pw
    if "key_label" in body:
        label = str(body["key_label"] or "").strip()[:40]
        sets.append("key_label=?")
        args.append(label)
    if body.get("rotate_key"):
        key = new_api_key()
        sets += ["api_key=?", "key_created_at=?", "key_last_used_at=NULL", "key_uses=0"]
        args += [key, now_ms()]
        out["api_key"] = key
    if "role" in body:
        role = body["role"]
        if role not in ROLES:
            raise HTTPException(status_code=400, detail="角色不合法")
        if agent_id == user["id"]:
            raise HTTPException(status_code=400, detail="不能修改自己的角色")
        if role != "admin":
            with db() as conn:
                row = conn.execute("SELECT role FROM users WHERE id=?", (agent_id,)).fetchone()
                admins = conn.execute(
                    "SELECT COUNT(*) c FROM users WHERE role='admin' AND active=1"
                ).fetchone()["c"]
            if row and norm_role(row["role"]) == "admin" and admins <= 1:
                raise HTTPException(status_code=400, detail="至少要保留一个管理员")
        sets.append("role=?")
        args.append(role)
    if not sets:
        raise HTTPException(status_code=400, detail="没有要更新的内容")
    args.append(agent_id)
    with db() as conn:
        conn.execute(f"UPDATE users SET {', '.join(sets)} WHERE id=?", args)
    log_event("agent_patch", user["id"], None, str(agent_id))
    out["ok"] = True
    return out


@router.delete("/{agent_id}")
def delete_agent(agent_id: int, user: dict = Depends(admin_user)):
    if agent_id == user["id"]:
        raise HTTPException(status_code=400, detail="不能删除自己")
    with db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (agent_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="成员不存在")
        projects = conn.execute("SELECT slug FROM projects WHERE owner_id=?", (agent_id,)).fetchall()
    leftover = 0
    for p in projects:
        if not remove_project_files(p["slug"]):
            leftover += 1  # 文件被占用时记录先删，残留目录交给孤儿清理
    with db() as conn:
        # 文件都删了，记录也不能留：owner_id 是 ON DELETE SET NULL，
        # 光删用户会把项目变成「无主孤儿」，门户上挂着一条谁都认不出的记录。
        # project_tags / daily_views 都是 ON DELETE CASCADE，跟着走。
        conn.execute("DELETE FROM projects WHERE owner_id=?", (agent_id,))
        conn.execute("DELETE FROM users WHERE id=?", (agent_id,))
    log_event("agent_delete", user["id"], None, row["username"])
    return {"ok": True, "removed_projects": len(projects), "leftover_dirs": leftover}


@router.get("/{agent_id}/key")
def reveal_key(agent_id: int, user: dict = Depends(admin_user)):
    with db() as conn:
        row = conn.execute("SELECT api_key FROM users WHERE id=?", (agent_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="成员不存在")
    return {"api_key": row["api_key"]}
