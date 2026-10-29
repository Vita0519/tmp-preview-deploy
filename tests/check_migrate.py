#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""老库迁移回归测试：users.role 从 admin/agent 两档升到 viewer/publisher/admin 三档。

只碰临时目录里的库，不依赖第三方库。

用法:
  python tests/check_migrate.py
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PASS, FAIL = [], []


def check(name: str, cond: bool, extra: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"  {'✓' if cond else '✗'} {name}{('  → ' + extra) if extra and not cond else ''}")


# 老版本的 users 建表语句（role 只有 admin/agent）
OLD_USERS = """CREATE TABLE IF NOT EXISTS users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  username      TEXT NOT NULL UNIQUE,
  display_name  TEXT NOT NULL DEFAULT '',
  role          TEXT NOT NULL DEFAULT 'agent' CHECK (role IN ('admin','agent')),
  password_hash TEXT NOT NULL,
  api_key       TEXT UNIQUE,
  active        INTEGER NOT NULL DEFAULT 1,
  created_at    INTEGER NOT NULL,
  last_login_at INTEGER
);
"""


def old_schema() -> str:
    """拿当前 SCHEMA，只把 users 那段换回老版本 —— 其余表跟着代码走，不用手工同步。"""
    sys.path.insert(0, str(ROOT / "backend"))
    from app.db import SCHEMA

    i = SCHEMA.index("CREATE TABLE IF NOT EXISTS users (")
    j = SCHEMA.index(");", i) + 2
    return SCHEMA[:i] + OLD_USERS + SCHEMA[j:]


def build_old_db(db: Path) -> None:
    conn = sqlite3.connect(str(db), isolation_level=None)
    conn.executescript(old_schema())
    conn.execute(
        "INSERT INTO users(id, username, display_name, role, password_hash, created_at) "
        "VALUES(1,'admin','管理员','admin','x',1)"
    )
    conn.execute(
        "INSERT INTO users(id, username, display_name, role, password_hash, created_at) "
        "VALUES(2,'alice','Alice','agent','x',2)"
    )
    conn.execute(
        "INSERT INTO projects(slug, title, owner_id, created_at, updated_at) "
        "VALUES('demo','Demo',2,1,1)"
    )
    conn.close()


def run_init(data_dir: Path) -> str:
    """在子进程里跑 init_db()，DATA_DIR 指到临时目录。"""
    env = dict(os.environ, DATA_DIR=str(data_dir))
    code = (
        "import sys; sys.path.insert(0, %r);"
        "from app.db import init_db; init_db()" % str(ROOT / "backend")
    )
    p = subprocess.run(
        [sys.executable, "-c", code], cwd=str(ROOT), env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if p.returncode != 0:
        raise RuntimeError((p.stdout or "") + (p.stderr or ""))
    return (p.stdout or "") + (p.stderr or "")


def schema_of(conn, table: str) -> str:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return (row[0] or "") if row else ""


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="pv-migrate-"))
    try:
        db = tmp / "db.sqlite3"
        build_old_db(db)

        print("[1] 老库 → 新库")
        out = run_init(tmp)
        conn = sqlite3.connect(str(db), isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")

        users_sql = schema_of(conn, "users")
        check("users 表已带三档 CHECK", "viewer" in users_sql and "publisher" in users_sql, users_sql)
        check("默认值改为 publisher", "DEFAULT 'publisher'" in users_sql, users_sql)

        roles = {r["username"]: r["role"] for r in conn.execute("SELECT username, role FROM users")}
        check("agent → publisher", roles.get("alice") == "publisher", str(roles))
        check("admin 保持不变", roles.get("admin") == "admin", str(roles))

        check("旧表 users_old 已清理",
              not conn.execute("SELECT 1 FROM sqlite_master WHERE name='users_old'").fetchone(), "")

        projects_sql = schema_of(conn, "projects")
        check("projects 外键仍指向 users", '"users_old"' not in projects_sql and "users" in projects_sql, projects_sql)
        fk = conn.execute("PRAGMA foreign_key_list(projects)").fetchall()
        check("外键目标表 = users", all(r["table"] == "users" for r in fk), str([r["table"] for r in fk]))
        check("foreign_key_check 干净", conn.execute("PRAGMA foreign_key_check").fetchall() == [], "")

        # 真正的问题点：迁移后还能不能插项目
        try:
            conn.execute(
                "INSERT INTO projects(slug, title, owner_id, created_at, updated_at) "
                "VALUES('after','After',2,2,2)"
            )
            ok, err = True, ""
        except sqlite3.Error as e:
            ok, err = False, str(e)
        check("迁移后能插入带 owner 的项目", ok, err)

        # 新角色能不能写进去
        try:
            conn.execute(
                "INSERT INTO users(username, role, password_hash, created_at) "
                "VALUES('v1','viewer','x',3)"
            )
            ok, err = True, ""
        except sqlite3.Error as e:
            ok, err = False, str(e)
        check("可以写入 viewer 角色", ok, err)

        try:
            conn.execute(
                "INSERT INTO users(username, role, password_hash, created_at) "
                "VALUES('bad','root','x',4)"
            )
            ok = True
        except sqlite3.Error:
            ok = False
        check("非法角色被 CHECK 拦住", not ok, "root 居然插进去了")

        # 自增序列要跟着搬走，不能从 1 重新发号
        new_id = conn.execute(
            "INSERT INTO users(username, role, password_hash, created_at) "
            "VALUES('seq','publisher','x',5)"
        ).lastrowid
        check("自增 ID 接着老数据往后发", new_id > 2, f"new_id={new_id}")

        check("会员数据没丢", conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 2, "")
        conn.close()

        print("[2] 重复执行幂等")
        out2 = run_init(tmp)
        check("第二次不再重建表", "[migrate] 重建" not in out2, out2.strip())
        conn = sqlite3.connect(str(db))
        check("数据仍在", conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 4, "")
        conn.close()

        print("[3] 修早期版本留下的悬空外键")
        db2 = tmp / "broken" / "db.sqlite3"
        db2.parent.mkdir(parents=True, exist_ok=True)
        build_old_db(db2)
        # 人为造出「已经按错误顺序迁过」的样子：users 已是新表，但 projects 指向 users_old
        conn = sqlite3.connect(str(db2), isolation_level=None)
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("ALTER TABLE users RENAME TO users_old")
        conn.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE,"
            " display_name TEXT NOT NULL DEFAULT '', role TEXT NOT NULL DEFAULT 'publisher'"
            " CHECK (role IN ('viewer','publisher','admin')), password_hash TEXT NOT NULL,"
            " api_key TEXT UNIQUE, active INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL,"
            " last_login_at INTEGER)"
        )
        conn.execute(
            "INSERT INTO users(id, username, display_name, role, password_hash, created_at) "
            "SELECT id, username, display_name, CASE role WHEN 'agent' THEN 'publisher' ELSE role END,"
            " password_hash, created_at FROM users_old"
        )
        conn.execute("DROP TABLE users_old")
        broken_sql = schema_of(conn, "projects")
        conn.close()
        check("构造出悬空外键", "users_old" in broken_sql, broken_sql)

        out3 = run_init(db2.parent)
        check("启动时自动修好", "修正悬空外键" in out3, out3.strip())
        conn = sqlite3.connect(str(db2), isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        check("projects 已指向 users", "users_old" not in schema_of(conn, "projects"), schema_of(conn, "projects"))
        try:
            conn.execute(
                "INSERT INTO projects(slug, title, owner_id, created_at, updated_at) "
                "VALUES('fixed','Fixed',2,3,3)"
            )
            ok, err = True, ""
        except sqlite3.Error as e:
            ok, err = False, str(e)
        check("修好之后能插项目", ok, err)
        conn.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    total = len(PASS) + len(FAIL)
    print(f"\n{len(PASS)}/{total} 通过")
    if FAIL:
        print("失败：" + json.dumps(FAIL, ensure_ascii=False, indent=2))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
