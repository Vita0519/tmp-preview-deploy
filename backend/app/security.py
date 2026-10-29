"""认证：密码 PBKDF2 + 服务端会话 Cookie；机器调用走 per-user API Key。"""
import hashlib
import hmac
import secrets
import time

from fastapi import Depends, HTTPException, Request

from . import config
from .db import db, tx

PBKDF2_ROUNDS = 120_000


def now_ms() -> int:
    return int(time.time() * 1000)


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ROUNDS)
    return f"pbkdf2${PBKDF2_ROUNDS}${salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, rounds, salt, digest = stored.split("$")
        if algo != "pbkdf2":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds))
        return hmac.compare_digest(dk.hex(), digest)
    except (ValueError, AttributeError):
        return False


def new_api_key() -> str:
    return "pv_" + secrets.token_urlsafe(32)


def _user_dict(row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"] or row["username"],
        "role": row["role"],
        "active": bool(row["active"]),
        "created_at": row["created_at"],
        "last_login_at": row["last_login_at"],
    }


def user_by_id(user_id: int) -> dict | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return _user_dict(row) if row else None


def create_session(user_id: int, ua: str = "") -> str:
    token = secrets.token_urlsafe(32)
    t = now_ms()
    with db() as conn:
        conn.execute(
            "INSERT INTO sessions(token, user_id, created_at, expires_at, ua) VALUES(?,?,?,?,?)",
            (token, user_id, t, t + config.SESSION_DAYS * 86400_000, ua[:200]),
        )
        conn.execute("UPDATE users SET last_login_at=? WHERE id=?", (t, user_id))
    return token


def drop_session(token: str) -> None:
    if not token:
        return
    with db() as conn:
        conn.execute("DELETE FROM sessions WHERE token=?", (token,))


def _by_api_key(key: str) -> dict | None:
    if not key:
        return None
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE api_key=? AND active=1", (key,)
        ).fetchone()
    return _user_dict(row) if row else None


def _by_session(token: str) -> dict | None:
    if not token:
        return None
    with db() as conn:
        row = conn.execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id "
            "WHERE s.token=? AND s.expires_at>? AND u.active=1",
            (token, now_ms()),
        ).fetchone()
    return _user_dict(row) if row else None


def resolve_user(request: Request) -> dict | None:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        user = _by_api_key(auth[7:].strip())
        if user:
            return user
    token = request.cookies.get(config.COOKIE_NAME) or ""
    if token:
        return _by_session(token)
    # 兼容 x-api-key
    return _by_api_key(request.headers.get("x-api-key") or "")


def current_user(request: Request) -> dict:
    user = resolve_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return user


def admin_user(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def optional_user(request: Request) -> dict | None:
    return resolve_user(request)


def bootstrap_admin() -> None:
    """首次启动创建管理员；已存在则不动。"""
    with db() as conn:
        n = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    if n:
        return
    password = config.ADMIN_PASSWORD or secrets.token_urlsafe(9)
    t = now_ms()
    with tx() as conn:
        conn.execute(
            "INSERT INTO users(username, display_name, role, password_hash, api_key, active, created_at) "
            "VALUES(?,?,?,?,?,1,?)",
            (
                config.ADMIN_USERNAME,
                config.ADMIN_DISPLAY_NAME,
                "admin",
                hash_password(password),
                new_api_key(),
                t,
            ),
        )
    if config.ADMIN_PASSWORD:
        print(f"[init] 管理员 {config.ADMIN_USERNAME} 已创建（密码来自 ADMIN_PASSWORD）", flush=True)
    else:
        print(
            f"[init] 管理员 {config.ADMIN_USERNAME} 已创建，初始密码: {password}  "
            f"（请立即登录修改，或在 .env 里设置 ADMIN_PASSWORD 重建）",
            flush=True,
        )
