"""SQLite 访问层：WAL + 短事务，够轻够快（万级项目无压力）。"""
import sqlite3
import time
from contextlib import contextmanager

from .config import DB_PATH, FILES_DIR, ZIPS_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
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
        for k, v in DEFAULT_SETTINGS.items():
            conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)", (k, v))


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
    clean = []
    for n in names:
        n = (n or "").strip()[:24]
        if n and n not in clean:
            clean.append(n)
    conn.execute("DELETE FROM project_tags WHERE project_id=?", (project_id,))
    for n in clean:
        conn.execute("INSERT OR IGNORE INTO tags(name) VALUES(?)", (n,))
        row = conn.execute("SELECT id FROM tags WHERE name=?", (n,)).fetchone()
        if row:
            conn.execute(
                "INSERT OR IGNORE INTO project_tags(project_id, tag_id) VALUES(?,?)",
                (project_id, row["id"]),
            )
