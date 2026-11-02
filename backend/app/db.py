"""SQLite 访问层：WAL + 短事务，够轻够快（万级项目无压力）。"""
import sqlite3
import time
from contextlib import contextmanager

from . import tagspec
from .config import DB_PATH, FILES_DIR, ZIPS_DIR

SCHEMA = """
-- 收藏夹（两层：parent_id 为空是一级，否则挂在某个一级下面）
-- 靠 parent_id 存而不是写死两列，是为了以后放开深度不用改表
CREATE TABLE IF NOT EXISTS collections (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  name       TEXT NOT NULL,
  parent_id  INTEGER REFERENCES collections(id) ON DELETE CASCADE,
  owner_id   INTEGER REFERENCES users(id) ON DELETE CASCADE,
  icon       TEXT NOT NULL DEFAULT '',
  sort       INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_collections_owner  ON collections(owner_id);
CREATE INDEX IF NOT EXISTS idx_collections_parent ON collections(parent_id);
-- 同一层里不许重名（忽略大小写与首尾空格）
CREATE UNIQUE INDEX IF NOT EXISTS idx_collections_uniq
  ON collections(owner_id, ifnull(parent_id, 0), lower(trim(name)));

CREATE TABLE IF NOT EXISTS users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  username      TEXT NOT NULL UNIQUE,
  display_name  TEXT NOT NULL DEFAULT '',
  role          TEXT NOT NULL DEFAULT 'publisher'
                CHECK (role IN ('viewer','publisher','admin')),
  password_hash TEXT NOT NULL,
  api_key       TEXT UNIQUE,
  key_label     TEXT,
  key_created_at INTEGER,
  key_last_used_at INTEGER,
  key_uses      INTEGER NOT NULL DEFAULT 0,
  active        INTEGER NOT NULL DEFAULT 1,
  created_at    INTEGER NOT NULL,
  last_login_at INTEGER
);

CREATE TABLE IF NOT EXISTS sessions (
  token      TEXT PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  ua         TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

CREATE TABLE IF NOT EXISTS projects (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  slug          TEXT NOT NULL UNIQUE,
  title         TEXT NOT NULL,
  description   TEXT NOT NULL DEFAULT '',
  owner_id      INTEGER REFERENCES users(id) ON DELETE SET NULL,
  kind          TEXT NOT NULL DEFAULT 'static' CHECK (kind IN ('static','zip','link')),
  entry         TEXT,
  file_count    INTEGER NOT NULL DEFAULT 0,
  size_bytes    INTEGER NOT NULL DEFAULT 0,
  has_zip       INTEGER NOT NULL DEFAULT 0,
  zip_name      TEXT,
  link_url      TEXT,
  visibility    TEXT NOT NULL DEFAULT 'link' CHECK (visibility IN ('portal','link','private')),
  collection_id INTEGER REFERENCES collections(id) ON DELETE SET NULL,
  allow_download INTEGER NOT NULL DEFAULT 0,
  expire_action TEXT NOT NULL DEFAULT 'block' CHECK (expire_action IN ('block','delete')),
  expires_at    INTEGER,
  status        TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','expired','deleted')),
  views         INTEGER NOT NULL DEFAULT 0,
  downloads     INTEGER NOT NULL DEFAULT 0,
  created_at    INTEGER NOT NULL,
  updated_at    INTEGER NOT NULL,
  last_viewed_at INTEGER,
  legacy_source TEXT
);
CREATE INDEX IF NOT EXISTS idx_projects_owner  ON projects(owner_id);
CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);
CREATE INDEX IF NOT EXISTS idx_projects_expire ON projects(expires_at);
CREATE INDEX IF NOT EXISTS idx_projects_views  ON projects(views);
CREATE INDEX IF NOT EXISTS idx_projects_update ON projects(updated_at);
-- 同一成员重名检测走表达式索引（大小写与首尾空格不敏感）
CREATE INDEX IF NOT EXISTS idx_projects_owner_title ON projects(owner_id, lower(trim(title)));

CREATE TABLE IF NOT EXISTS tags (
  id   INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS project_tags (
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  tag_id     INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
  PRIMARY KEY (project_id, tag_id)
);
CREATE INDEX IF NOT EXISTS idx_pt_tag ON project_tags(tag_id);

CREATE TABLE IF NOT EXISTS daily_views (
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  day        TEXT NOT NULL,
  count      INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (project_id, day)
);

CREATE TABLE IF NOT EXISTS events (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  at         INTEGER NOT NULL,
  user_id    INTEGER,
  action     TEXT NOT NULL,
  project_id INTEGER,
  detail     TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_at ON events(at);

CREATE TABLE IF NOT EXISTS settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""

DEFAULT_SETTINGS = {
    "site_title": "",
    "default_ttl_hours": "24",
    "default_ttl_portal": "",
    "default_ttl_link": "",
    "default_ttl_private": "",
    "public_portal": "0",
    "default_expire_action": "block",
    # 配色系列：classic / tech / macaron / morandi / ink / minimal
    "theme_series": "classic",
}


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=8000")
    return conn


@contextmanager
def db():
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def tx():
    """显式事务，异常回滚。"""
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.execute("COMMIT")
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


def init_db() -> None:
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    ZIPS_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.executescript(SCHEMA)
        _migrate_roles(conn)
        _add_user_key_cols(conn)
        _add_project_cols(conn)
        for k, v in DEFAULT_SETTINGS.items():
            conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)", (k, v))
        _migrate_tags(conn)
        _migrate_owner(conn)


def _migrate_owner(conn) -> None:
    """把「无主项目」收归到最早的管理员。

    项目的归属人只应该是「谁建的/谁挂的」；但外键是 ON DELETE SET NULL，
    历史上删成员时又只删了文件没删记录，owner_id 被置空，门户卡片就露出一条「—」。
    这里给存量擦一次屁股，以后再出现由 delete_agent 负责连记录一起删。
    """
    key = "owner_backfill_v1"
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    if row and row["value"] == "1":
        return
    admin = conn.execute(
        "SELECT id FROM users WHERE role='admin' AND active=1 ORDER BY id LIMIT 1"
    ).fetchone() or conn.execute(
        "SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1"
    ).fetchone()
    if admin:
        n = conn.execute(
            "UPDATE projects SET owner_id=? WHERE owner_id IS NULL", (admin["id"],)
        ).rowcount
        if n:
            print(f"[migrate] {n} 个无主项目收归管理员 #{admin['id']}", flush=True)
    conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES(?, '1')", (key,))
    conn.execute("UPDATE settings SET value='1' WHERE key=?", (key,))


def _migrate_tags(conn) -> None:
    """存量标签按新规则规范化一次（归一化 / 合并重名 / 每项目截到上限 / 删孤儿）。

    用设置里的开关位守着，只跑一次；以后再改规则要换 key，别偷偷重排别人数据。
    """
    key = "tags_spec_v1"
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    if row and row["value"] == "1":
        return
    try:
        tagspec.normalize_rows(conn)
        tagspec.prune_orphans(conn)
    except sqlite3.Error as exc:  # 老库结构异常时别把启动卡死
        print(f"[migrate] 标签规范化跳过：{exc}", flush=True)
    conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES(?, '1')", (key,))
    conn.execute("UPDATE settings SET value='1' WHERE key=?", (key,))


def _add_project_cols(conn) -> None:
    """给老库的 projects 补上收藏夹归属（collections 表本身由 SCHEMA 建好）。"""
    have = {r["name"] for r in conn.execute("PRAGMA table_info(projects)").fetchall()}
    if "collection_id" not in have:
        try:
            conn.execute(
                "ALTER TABLE projects ADD COLUMN collection_id INTEGER "
                "REFERENCES collections(id) ON DELETE SET NULL"
            )
        except sqlite3.OperationalError as exc:
            print(f"[migrate] 跳过 projects.collection_id：{exc}", flush=True)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_coll ON projects(collection_id)")
    except sqlite3.OperationalError as exc:
        print(f"[migrate] 跳过 idx_projects_coll：{exc}", flush=True)


def _add_user_key_cols(conn) -> None:
    """给 users 补上 API Key 的绑定信息（一个账号只绑一个 agent，得看得见绑给了谁）。

    key_label      这把 key 绑给哪个 agent / 机器（管理员填，默认同账号名）
    key_created_at 这把 key 的签发时间（轮换会刷新）
    key_last_used_at 最近一次用这把 key 调接口的时间（按 60s 粒度回写）
    key_uses       累计调用次数，用来发现「一把 key 被多个 agent 共用」
    """
    have = {r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
    for col, ddl in (
        ("key_label", "ALTER TABLE users ADD COLUMN key_label TEXT"),
        ("key_created_at", "ALTER TABLE users ADD COLUMN key_created_at INTEGER"),
        ("key_last_used_at", "ALTER TABLE users ADD COLUMN key_last_used_at INTEGER"),
        ("key_uses", "ALTER TABLE users ADD COLUMN key_uses INTEGER NOT NULL DEFAULT 0"),
    ):
        if col in have:
            continue
        try:
            conn.execute(ddl)
        except sqlite3.OperationalError as exc:
            print(f"[migrate] 跳过 users.{col}：{exc}", flush=True)
    # 老库的 key 没有签发时间，用账号创建时间兜底，避免前端显示「—」
    conn.execute(
        "UPDATE users SET key_created_at=created_at "
        "WHERE api_key IS NOT NULL AND key_created_at IS NULL"
    )
    conn.execute(
        "UPDATE users SET key_label=username WHERE key_label IS NULL OR key_label=''"
    )


def _migrate_roles(conn) -> None:
    """老库的 users.role 只有 admin/agent 且带 CHECK 约束，加不了 viewer。

    SQLite 改不了 CHECK，只能重建表：agent → publisher，其余原样搬过去。
    """
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()
    sql = (row["sql"] or "") if row else ""
    if "publisher" in sql:
        _repair_dangling_refs(conn)
        return
    print("[migrate] 重建 users 表：agent → publisher，放开 viewer 角色", flush=True)
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        conn.execute("BEGIN IMMEDIATE")
        # 顺序很重要：先建新表 → 搬数据 → 删旧表 → 最后把新表改名回 users。
        # 反过来先 ALTER TABLE users RENAME TO users_old 的话，SQLite 会把 projects
        # 等表里的 REFERENCES users(id) 一起改写成 REFERENCES users_old(id)，
        # 旧表一删，插项目就报 no such table: main.users_old。
        conn.execute(
            """
            CREATE TABLE users_new (
              id            INTEGER PRIMARY KEY AUTOINCREMENT,
              username      TEXT NOT NULL UNIQUE,
              display_name  TEXT NOT NULL DEFAULT '',
              role          TEXT NOT NULL DEFAULT 'publisher'
                            CHECK (role IN ('viewer','publisher','admin')),
              password_hash TEXT NOT NULL,
              api_key       TEXT UNIQUE,
              active        INTEGER NOT NULL DEFAULT 1,
              created_at    INTEGER NOT NULL,
              last_login_at INTEGER
            )
            """
        )
        conn.execute(
            "INSERT INTO users_new(id, username, display_name, role, password_hash, api_key, active, created_at, last_login_at) "
            "SELECT id, username, display_name, "
            "CASE role WHEN 'agent' THEN 'publisher' WHEN 'admin' THEN 'admin' ELSE 'publisher' END, "
            "password_hash, api_key, active, created_at, last_login_at FROM users"
        )
        conn.execute("DROP TABLE users")
        conn.execute("ALTER TABLE users_new RENAME TO users")
        conn.execute("COMMIT")
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.execute("PRAGMA foreign_keys=ON")


def _repair_dangling_refs(conn) -> None:
    """修掉早期版本留下的 REFERENCES "users_old"（那张表已经不在了）。

    只改 sqlite_master 里的建表语句文本，不动数据；改完把 schema_version 加一，
    让同库的其它连接重新解析 schema。
    """
    rows = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table' AND sql LIKE '%users_old%'"
    ).fetchall()
    if not rows:
        return
    print(f"[migrate] 修正悬空外键 users_old → users：{[r['name'] for r in rows]}", flush=True)
    conn.execute("PRAGMA writable_schema=ON")
    try:
        for r in rows:
            fixed = (r["sql"] or "").replace("users_old", "users")
            conn.execute(
                "UPDATE sqlite_master SET sql=? WHERE type='table' AND name=?", (fixed, r["name"])
            )
        ver = conn.execute("PRAGMA schema_version").fetchone()[0]
        conn.execute(f"PRAGMA schema_version={int(ver) + 1}")
    finally:
        conn.execute("PRAGMA writable_schema=OFF")
    conn.execute("PRAGMA writable_schema=RESET")


def get_setting(key: str, default: str = "") -> str:
    with db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def all_settings() -> dict:
    with db() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    out = dict(DEFAULT_SETTINGS)
    out.update({r["key"]: r["value"] for r in rows})
    return out


def log_event(action: str, user_id: int | None = None, project_id: int | None = None, detail: str = "") -> None:
    try:
        with db() as conn:
            conn.execute(
                "INSERT INTO events(at, user_id, action, project_id, detail) VALUES(?,?,?,?,?)",
                (int(time.time() * 1000), user_id, action, project_id, detail[:500]),
            )
    except sqlite3.Error:
        pass


def set_tags(conn: sqlite3.Connection, project_id: int, names: list[str]) -> None:
    """写项目的标签。规则在 tagspec 里（数量/长度/字符/归一化），这里只落库。

    池子上限也在这里把：调用方可能已经校验过单项目规则，但「全站不能无限长」必须
    看着库里的现状才好判断，放在唯一的写入口最省心。
    """
    clean = tagspec.clean(names)
    existing = {r["name"] for r in conn.execute("SELECT name FROM tags").fetchall()}
    fresh = [n for n in clean if n not in existing]
    if len(existing) + len(fresh) > tagspec.POOL_MAX:
        raise tagspec.TagError(
            f"全站标签已达 {tagspec.POOL_MAX} 个上限，请改用已有标签"
            "（或在设置页清理没人用的标签）"
        )
    conn.execute("DELETE FROM project_tags WHERE project_id=?", (project_id,))
    for n in clean:
        conn.execute("INSERT OR IGNORE INTO tags(name) VALUES(?)", (n,))
        row = conn.execute("SELECT id FROM tags WHERE name=?", (n,)).fetchone()
        if row:
            conn.execute(
                "INSERT OR IGNORE INTO project_tags(project_id, tag_id) VALUES(?,?)",
                (project_id, row["id"]),
            )
    # 改标签后原来那个标签可能没人用了，顺手回收，池子不会越攒越脏
    tagspec.prune_orphans(conn)
