"""登录 / 退出 / 身份 / API Key 换取。"""
import secrets
import threading
import time

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

# ---- 登录限速：15 分钟窗口内连错 10 次就锁 15 分钟 ----
# 同时按 IP 和用户名计数：IP 防扫号，用户名防换 IP 爆破同一个账号。
# 只在内存里，重启清零；单进程部署足够。登录成功会清掉这个 IP 和账号的记录。
FAIL_MAX = 10
FAIL_WINDOW = 15 * 60
LOCK_SECS = 15 * 60
_fails: dict[str, list[float]] = {}
_locked: dict[str, float] = {}
_flock = threading.Lock()


def _client_ip(request: Request) -> str:
    # 反代后面取第一跳；直连就用 socket 地址
    fwd = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    return fwd or request.headers.get("x-real-ip") or (request.client.host if request.client else "?")


def _keys(request: Request, username: str) -> list[str]:
    return [f"ip:{_client_ip(request)}", f"u:{username.lower()}"]


def _check_locked(keys: list[str]) -> None:
    now = time.time()
    with _flock:
        left = max((_locked.get(k, 0) - now for k in keys), default=0)
    if left > 0:
        raise HTTPException(status_code=429, detail=f"失败次数过多，请 {int(left // 60) + 1} 分钟后再试")


def _record_fail(keys: list[str]) -> None:
    now = time.time()
    with _flock:
        for k in keys:
            arr = [t for t in _fails.get(k, []) if now - t < FAIL_WINDOW]
            arr.append(now)
            _fails[k] = arr
            if len(arr) >= FAIL_MAX:
                _locked[k] = now + LOCK_SECS
                _fails.pop(k, None)
        if len(_fails) > 5000:  # 防内存被刷爆：清掉过期的
            for k in [k for k, v in _fails.items() if now - v[-1] > FAIL_WINDOW]:
                _fails.pop(k, None)
            for k in [k for k, v in _locked.items() if v < now]:
                _locked.pop(k, None)


def _clear(keys: list[str]) -> None:
    with _flock:
        for k in keys:
            _fails.pop(k, None)
            _locked.pop(k, None)


def _verify_login(request: Request, username: str, password: str):
    """统一的账号密码校验（网页登录和 CLI 换 Key 共用同一套限速）。"""
    keys = _keys(request, username)
    _check_locked(keys)
    with db() as conn:
        row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if not row or not row["active"] or not verify_password(password, row["password_hash"]):
        _record_fail(keys)
        raise HTTPException(status_code=401, detail="用户名或密码不正确")
    _clear(keys)
    return row


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
    row = _verify_login(request, username, password)
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
    # 只有本来就拿着 Key 来调的（CLI / Agent）才回显 Key；浏览器会话一律不给。
    # 否则任何在本站同源打开的项目页，都能借登录 Cookie fetch 这里把长期 Key 拿走。
    # 注意：不能只看「带没带 Key 头」——恶意页面可以随手塞个假头再靠 Cookie 通过认证，
    # 必须是请求里带的那个 Key 本身就是这个用户的，才算「本来就知道」。
    auth = request.headers.get("authorization") or ""
    sent = auth[7:].strip() if auth.lower().startswith("bearer ") else (request.headers.get("x-api-key") or "").strip()
    if sent:
        with db() as conn:
            api_key = conn.execute("SELECT api_key FROM users WHERE id=?", (user["id"],)).fetchone()["api_key"]
        if api_key and secrets.compare_digest(sent, api_key):
            return {"user": user, "api_key": api_key}
    return {"user": user}


@router.post("/token")
async def exchange_token(request: Request):
    """CLI 用：账号密码换长期 API Key。"""
    body = await request.json()
    username = str(body.get("username") or "").strip()
    password = str(body.get("password") or "")
    row = _verify_login(request, username, password)
    with db() as conn:
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
