"""认证：密码 PBKDF2 + 服务端会话 Cookie；机器调用走 per-user API Key。"""
import hashlib
import hmac
import secrets
import sqlite3
import time

from fastapi import Depends, HTTPException, Request

from . import config
from .db import db, tx

PBKDF2_ROUNDS = 120_000

# 三种角色：只能看门户 / 能发布自己的项目 / 管理员
ROLES = ("viewer", "publisher", "admin")
ROLE_LABELS = {"viewer": "仅门户访客", "publisher": "可发布项目", "admin": "管理员"}


def norm_role(raw: str | None) -> str:
    """兼容老库里的 'agent'（等同于 publisher）。"""
    if raw == "agent":
        return "publisher"
    return raw if raw in ROLES else "viewer"


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
        "role": norm_role(row["role"]),
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
    if not row:
        return None
    _touch_key(key, row["id"])
    return _user_dict(row)


# 一把 key 只该被一个 agent 用，所以记下「谁在用、用了几次」。
# 每个请求都写库太浪费，同一把 key 60 秒内只回写一次。
_KEY_TOUCH: dict[str, int] = {}


def _touch_key(key: str, user_id: int) -> None:
    t = now_ms()
    if _KEY_TOUCH.get(key, 0) > t - 60_000:
        return
    _KEY_TOUCH[key] = t
    if len(_KEY_TOUCH) > 512:
        _KEY_TOUCH.clear()
        _KEY_TOUCH[key] = t
    try:
        with db() as conn:
            conn.execute(
                "UPDATE users SET key_last_used_at=?, key_uses=COALESCE(key_uses,0)+1 "
                "WHERE id=? AND api_key=?",
                (t, user_id, key),
            )
    except sqlite3.Error:
        pass


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


def publisher_user(user: dict = Depends(current_user)) -> dict:
    """能发布/管理项目的人（publisher 及以上）。viewer 只能看门户。"""
    if user["role"] == "viewer":
        raise HTTPException(status_code=403, detail="当前账号只能浏览访客门户")
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
