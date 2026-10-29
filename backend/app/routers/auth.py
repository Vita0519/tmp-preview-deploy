"""登录 / 退出 / 身份 / API Key 换取。"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from .. import config
from ..db import db
from ..security import (
    create_session,
    current_user,
    drop_session,
    hash_password,
    now_ms,
    resolve_user,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_cookie(resp: Response, token: str) -> None:
    resp.set_cookie(
        config.COOKIE_NAME,
        token,
        max_age=config.SESSION_DAYS * 86400,
        httponly=True,
        samesite="lax",
        secure=config.COOKIE_SECURE,
        path="/",
    )


@router.post("/login")
async def login(request: Request, response: Response):
    body = await request.json()
    username = str(body.get("username") or "").strip()
    password = str(body.get("password") or "")
    with db() as conn:
        row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if not row or not row["active"] or not verify_password(password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码不正确")
    token = create_session(row["id"], request.headers.get("user-agent") or "")
    _set_cookie(response, token)
    return {
        "ok": True,
        "user": {
            "id": row["id"],
            "username": row["username"],
            "display_name": row["display_name"] or row["username"],
            "role": row["role"],
        },
    }


@router.post("/logout")
async def logout(request: Request, response: Response):
    drop_session(request.cookies.get(config.COOKIE_NAME) or "")
    response.delete_cookie(config.COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
async def me(request: Request):
    user = resolve_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    with db() as conn:
        api_key = conn.execute("SELECT api_key FROM users WHERE id=?", (user["id"],)).fetchone()["api_key"]
    return {"user": user, "api_key": api_key}


@router.post("/token")
async def exchange_token(request: Request):
    """CLI 用：账号密码换长期 API Key。"""
    body = await request.json()
    username = str(body.get("username") or "").strip()
    password = str(body.get("password") or "")
    with db() as conn:
        row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if not row or not row["active"] or not verify_password(password, row["password_hash"]):
            raise HTTPException(status_code=401, detail="用户名或密码不正确")
        key = row["api_key"]
        if not key:
            raise HTTPException(status_code=409, detail="该账号未分配 API Key，请管理员重置")
        conn.execute("UPDATE users SET last_login_at=? WHERE id=?", (now_ms(), row["id"]))
    return {"token": key, "username": row["username"], "role": row["role"]}


@router.post("/password")
async def change_password(request: Request, user: dict = Depends(current_user)):
    body = await request.json()
    old = str(body.get("old_password") or "")
    new = str(body.get("new_password") or "")
    if len(new) < 6:
        raise HTTPException(status_code=400, detail="新密码至少 6 位")
    with db() as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE id=?", (user["id"],)).fetchone()
    if not row or not verify_password(old, row["password_hash"]):
        raise HTTPException(status_code=403, detail="原密码不正确")
    with db() as conn:
        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(new), user["id"]))
    return {"ok": True}
