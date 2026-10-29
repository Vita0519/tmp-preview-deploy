"""成员（Agent）管理：每个 agent 有自己的 API Key，只能看到自己的项目。"""
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request

from ..db import db, log_event, tx
from ..security import admin_user, hash_password, new_api_key, now_ms, user_by_id
from ..storage import remove_project_files

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("")
def list_agents(user: dict = Depends(admin_user)):
    with db() as conn:
        rows = conn.execute(
            "SELECT u.*, "
            "(SELECT COUNT(*) FROM projects p WHERE p.owner_id=u.id AND p.status<>'deleted') projects, "
            "(SELECT COUNT(*) FROM projects p WHERE p.owner_id=u.id AND p.status='active' "
            " AND (p.expires_at IS NULL OR p.expires_at>?)) online, "
            "(SELECT COALESCE(SUM(p.views),0) FROM projects p WHERE p.owner_id=u.id) views "
            "FROM users u ORDER BY u.role='admin' DESC, u.created_at",
            (now_ms(),),
        ).fetchall()
    return {
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
    role = "admin" if body.get("role") == "admin" else "agent"
    key = new_api_key()
    with tx() as conn:
        if conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            raise HTTPException(status_code=409, detail="账号已存在")
        cur = conn.execute(
            "INSERT INTO users(username, display_name, role, password_hash, api_key, active, created_at) "
            "VALUES(?,?,?,?,?,1,?)",
            (username, display, role, hash_password(password), key, now_ms()),
        )
        uid = cur.lastrowid
    log_event("agent_create", user["id"], None, username)
    return {"id": uid, "username": username, "password": password, "api_key": key}


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
    if body.get("rotate_key"):
        key = new_api_key()
        sets.append("api_key=?")
        args.append(key)
        out["api_key"] = key
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
    for p in projects:
        remove_project_files(p["slug"])
    with db() as conn:
        conn.execute("DELETE FROM users WHERE id=?", (agent_id,))
    log_event("agent_delete", user["id"], None, row["username"])
    return {"ok": True, "removed_projects": len(projects)}


@router.get("/{agent_id}/key")
def reveal_key(agent_id: int, user: dict = Depends(admin_user)):
    with db() as conn:
        row = conn.execute("SELECT api_key FROM users WHERE id=?", (agent_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="成员不存在")
    return {"api_key": row["api_key"]}
