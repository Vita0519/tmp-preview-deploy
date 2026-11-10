"""向后兼容：上一个版本留下的东西，新版本还得认得。

四件事最容易在新版本里悄悄坏掉，这里各钉一组：

  [A] 老备份包能恢复——而且是**恢复完立刻能用**（迁移当场跑，不用等重启）
  [B] 太老的包被明确拒绝——宁可不动现网，也别换上去之后处处 500
  [C] 老式书签 HTML（Safari / Firefox / Chrome 各自的写法）能导入
  [D] 老字段没被改名（旧客户端 / 旧脚本还在读 count、total、children 这些）
  [E] 老 CLI 写法还能跑（`--collection 名字`、`set --visibility`）

测试会临时覆盖数据，跑完（含中途失败）自动把测试前的备份恢复回去。
"""
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from http.cookiejar import CookieJar
from pathlib import Path

BASE = os.environ.get("PV_BASE", "http://127.0.0.1:8000")
ROOT = Path(__file__).resolve().parents[1]
USER = os.environ.get("PV_USER", "admin")
PASSWORD = os.environ.get("PV_PASS", "admin123")

ok = fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  [ok] {name}")
    else:
        fail += 1
        print(f"  [!!] {name}  {extra}")


class Resp:
    def __init__(self, code, body):
        self.status_code = code
        self._body = body

    def json(self):
        return json.loads(self._body or b"{}")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}: {self._body[:200]!r}")


class Sess:
    def __init__(self):
        self.op = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(CookieJar()),
        )

    def _do(self, method, path, body=None, raw=False):
        data, headers = None, {}
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
        try:
            with self.op.open(req, timeout=180) as r:
                return Resp(r.status, r.read())
        except urllib.error.HTTPError as e:
            return Resp(e.code, e.read())

    def get(self, path, raw=False):
        return self._do("GET", path, raw=raw)

    def post(self, path, body=None):
        return self._do("POST", path, body or {})

    def delete(self, path):
        return self._do("DELETE", path)

    def upload(self, path, filename, content, **fields):
        boundary = "----pvcompat"
        buf = io.BytesIO()
        for k, v in fields.items():
            buf.write(f"--{boundary}\r\n".encode())
            buf.write(f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode())
            buf.write(f"{v}\r\n".encode())
        buf.write(f"--{boundary}\r\n".encode())
        buf.write(
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode()
        )
        buf.write(b"Content-Type: application/octet-stream\r\n\r\n")
        buf.write(content)
        buf.write(f"\r\n--{boundary}--\r\n".encode())
        req = urllib.request.Request(
            BASE + path,
            data=buf.getvalue(),
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        try:
            with self.op.open(req, timeout=180) as r:
                return Resp(r.status, r.read())
        except urllib.error.HTTPError as e:
            return Resp(e.code, e.read())


admin = Sess()
admin.post("/api/auth/login", {"username": USER, "password": PASSWORD}).raise_for_status()


def projects_total(sess):
    return sess.get("/api/projects?limit=0&status=all").json()["total"]


def zip_counts(zip_path: Path) -> tuple[int, int]:
    """备份包里的库自己数一遍：活着的项目数、全部项目数。"""
    tmp = Path(tempfile.mkdtemp(prefix="pvcompat-count-"))
    try:
        with zipfile.ZipFile(zip_path) as z:
            z.extract("db.sqlite3", tmp)
        conn = sqlite3.connect(str(tmp / "db.sqlite3"))
        try:
            active = conn.execute("SELECT COUNT(*) FROM projects WHERE status='active'").fetchone()[0]
            every = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        finally:
            conn.close()
        return int(active), int(every)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ===================== 造一个「上一个版本」的备份包 =====================
def make_old_backup(src_zip: Path, dest: Path, drop_kind: bool = False) -> tuple[Path, str | None]:
    work = Path(tempfile.mkdtemp(prefix="pvcompat-old-"))
    with zipfile.ZipFile(src_zip) as z:
        z.extractall(work)
    db = work / "db.sqlite3"
    conn = sqlite3.connect(str(db))
    row = conn.execute("SELECT slug FROM projects WHERE status='active' ORDER BY id LIMIT 1").fetchone()
    loose = row[0] if row else None
    if loose:
        # 无主项目：验证「收归管理员」那条老迁移在新版本里还生效
        conn.execute("UPDATE projects SET owner_id=NULL WHERE slug=?", (loose,))
    if drop_kind:
        # 比上个版本还老的库：连 kind 都没有
        conn.execute("ALTER TABLE projects RENAME COLUMN kind TO kind_legacy")
    else:
        conn.execute("DROP INDEX IF EXISTS idx_projects_coll")
        conn.execute("ALTER TABLE projects DROP COLUMN collection_id")
        conn.execute("DROP TABLE IF EXISTS collections")
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute(
            "CREATE TABLE users_old ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " username TEXT NOT NULL UNIQUE,"
            " display_name TEXT NOT NULL DEFAULT '',"
            " role TEXT NOT NULL DEFAULT 'agent' CHECK (role IN ('admin','agent')),"
            " password_hash TEXT NOT NULL,"
            " api_key TEXT UNIQUE,"
            " active INTEGER NOT NULL DEFAULT 1,"
            " created_at INTEGER NOT NULL,"
            " last_login_at INTEGER)"
        )
        conn.execute(
            "INSERT INTO users_old(id,username,display_name,role,password_hash,api_key,active,created_at,last_login_at) "
            "SELECT id,username,display_name,"
            " CASE role WHEN 'publisher' THEN 'agent' WHEN 'viewer' THEN 'agent' ELSE role END,"
            " password_hash,api_key,active,created_at,last_login_at FROM users"
        )
        conn.execute("DROP TABLE users")
        conn.execute("ALTER TABLE users_old RENAME TO users")
        # 老库没有这些迁移开关位，迁移应该重跑一遍
        conn.execute("DELETE FROM settings WHERE key IN ('owner_backfill_v1','tags_spec_v1')")
    conn.commit()
    conn.close()
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for p in work.rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(work).as_posix())
    shutil.rmtree(work, ignore_errors=True)
    return dest, loose


BOOKMARKS = {
    # Safari：不写 doctype，直接从 <DT> 开始；文件夹没有 ADD_DATE
    "safari": """<DL><p>
<DT><H3>阅读列表</H3>
<DL><p>
    <DT><A HREF="https://safari.example/a">Safari 收藏一</A>
</DL><p>
<DT><H3>工作</H3>
<DL><p>
    <DT><A HREF="https://safari.example/b">Safari 收藏二</A>
</DL><p>
</DL><p>""",
    # Firefox：带 PERSONAL_TOOLBAR_FOLDER 与 <DD> 描述
    "firefox": """<!DOCTYPE NETSCAPE-Bookmark-file-1>
<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">
<TITLE>Bookmarks</TITLE>
<H1>Bookmarks Menu</H1>
<DL><p>
    <DT><H3 ADD_DATE="1500000000" LAST_MODIFIED="1600000000" PERSONAL_TOOLBAR_FOLDER="true">Firefox 工具栏</H3>
    <DD>Add bookmarks to this folder
    <DL><p>
        <DT><A HREF="https://firefox.example/a" ADD_DATE="1500000000">Firefox 书签一</A>
        <DD>一条说明
    </DL><p>
</DL><p>""",
    # Chrome：带 ICON（data URI）与 LAST_MODIFIED
    "chrome": """<!DOCTYPE NETSCAPE-Bookmark-file-1>
<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">
<TITLE>Bookmarks</TITLE>
<H1>Bookmarks</H1>
<DL><p>
    <DT><H3 ADD_DATE="1700000000" LAST_MODIFIED="1700000001" PERSONAL_TOOLBAR_FOLDER="true">Chrome 书签栏</H3>
    <DL><p>
        <DT><A HREF="https://chrome.example/a" ADD_DATE="1700000000" ICON="data:image/png;base64,iVBORw0KGgo=">Chrome 书签一</A>
    </DL><p>
</DL><p>""",
}


def run_cli(*args, token=""):
    cmd = [sys.executable, str(ROOT / "cli" / "agentctl.py"), "--url", BASE, "--token", token, *args]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, encoding="utf-8")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def main() -> None:
    global _ORIG_ZIP, _ORIG_TOTAL

    print("== [A] 老备份恢复 + 自动迁移 ==")
    backup = admin.get("/api/backup", raw=True)
    check("能拿到测试前的备份", backup.status_code == 200 and backup._body[:2] == b"PK", backup.status_code)
    tmpdir = Path(tempfile.mkdtemp(prefix="pvcompat-"))
    original_zip = tmpdir / "orig.zip"
    original_zip.write_bytes(backup._body)
    # 备份里的库才是「恢复后应该长什么样」的唯一标准：
    # 接口上的 total 受 status 过滤影响（all 会带上已过期/软删的），拿它比会差十几条
    orig_active, orig_all = zip_counts(original_zip)
    orig_total = orig_all
    _ORIG_ZIP, _ORIG_TOTAL = original_zip, orig_all

    old_zip, loose = make_old_backup(original_zip, tmpdir / "old-backup.zip")
    print(f"  旧结构备份已就绪：无主项目 {loose}，活项目 {orig_active} / 全部 {orig_all}")

    r = admin.upload("/api/backup/restore", "old-backup.zip", old_zip.read_bytes())
    d = r.json()
    print("  恢复返回:", r.status_code, str(d)[:150])
    check("旧备份包能恢复（200）", r.status_code == 200, r.status_code)
    check("结果里标明已迁移", d.get("migrated") is True, d.get("migrate_error"))
    check("活着的项目数跟备份里一致", d.get("counts", {}).get("projects") == orig_active, d.get("counts"))

    # ——关键：不重启服务，立刻访问所有依赖新结构的接口——
    c1 = admin.get("/api/collections")
    check("恢复后立刻能读收藏夹树（迁移当场跑了）", c1.status_code == 200, c1.status_code)
    tree = c1.json()
    check("老库里没有收藏夹 → items 为空", tree.get("items") == [], tree.get("items"))
    check("老项目全部算「未归类」", tree.get("unassigned") == orig_active, tree.get("unassigned"))

    c2 = admin.get("/api/projects?limit=1&status=all")
    check("恢复后立刻能读项目列表", c2.status_code == 200, c2.status_code)
    check("项目还在（一个没丢）", c2.json().get("total") == orig_all, f"{c2.json().get('total')} vs {orig_all}")

    c3 = admin.get("/api/agents?limit=0")
    check("恢复后立刻能读成员列表（key_* 列已补）", c3.status_code == 200, c3.status_code)
    agents = c3.json()["items"]
    roles = {a["role"] for a in agents}
    check("老角色 agent 已迁移成 publisher", "agent" not in roles, roles)
    check("角色都在合法集合里", roles <= {"admin", "publisher", "viewer"}, roles)
    check(
        "key_label 已用账号名兜底（不是空）",
        all((a.get("key_label") or "") != "" for a in agents),
        [a.get("key_label") for a in agents[:3]],
    )

    if loose:
        p = admin.get(f"/api/projects/{loose}")
        check("无主项目被收归管理员", p.status_code == 200 and bool(p.json().get("owner")), p.status_code)

    check("恢复后 meta 正常", admin.get("/api/meta").status_code == 200)
    col = admin.post("/api/collections", {"name": "兼容探针"}).json()["collection"]
    check("能在恢复后的老库上新建收藏夹", bool(col.get("id")), col)
    admin.delete(f"/api/collections/{col['id']}")

    print("\n== [B] 更老的包被拒绝 ==")
    bad_zip, _ = make_old_backup(original_zip, tmpdir / "too-old.zip", drop_kind=True)
    before = projects_total(admin)
    r = admin.upload("/api/backup/restore", "too-old.zip", bad_zip.read_bytes())
    print("  拒绝返回:", r.status_code, str(r.json())[:160])
    check("更老的包被 422 拒绝", r.status_code == 422, r.status_code)
    check("拒绝理由点名缺的字段", "kind" in str(r.json()), r.json())
    check("拒绝时现网数据没动", projects_total(admin) == before, f"{before} → {projects_total(admin)}")

    print("\n== [C] 老式书签导入 ==")
    for kind, html in BOOKMARKS.items():
        dry = admin.upload(
            "/api/import/bookmarks", f"{kind}.html", html.encode(), dry_run="1"
        )
        check(f"{kind} 预览成功", dry.status_code == 200, f"{dry.status_code} {str(dry.json())[:120]}")
        if dry.status_code == 200:
            dj = dry.json()
            check(f"{kind} 认出了书签", (dj.get("will_create") or 0) >= 1, dj)
            check(f"{kind} 认出了文件夹", (dj.get("folders_total") or 0) >= 1, dj)
        real = admin.upload("/api/import/bookmarks", f"{kind}.html", html.encode())
        check(f"{kind} 真导入成功", real.status_code == 200, f"{real.status_code} {str(real.json())[:120]}")
        if real.status_code == 200:
            rj = real.json()
            check(f"{kind} 建了项目", (rj.get("created") or 0) >= 1, rj)
            check(f"{kind} 建了收藏夹", (rj.get("folders_created") or 0) >= 1, rj)
        again = admin.upload("/api/import/bookmarks", f"{kind}.html", html.encode())
        if again.status_code == 200:
            check(f"{kind} 再导一次全部跳过", again.json().get("created") == 0, again.json())

    ff = admin.get("/api/projects?limit=0&status=all&q=Firefox").json()
    check("Firefox 的 <DD> 说明没被当成条目", ff.get("total") == 1, ff.get("total"))
    nodes = admin.get("/api/collections").json()["items"]
    names = {n["name"] for n in nodes}
    check("Safari 的两个文件夹都建了", {"阅读列表", "工作"} <= names, sorted(names))
    check("Chrome 的个人工具栏变成一个夹", "Chrome 书签栏" in names, sorted(names))

    print("\n== [D] 老字段仍在 ==")
    t = admin.get("/api/collections").json()
    check(
        "收藏夹树的老顶层字段都在",
        {"items", "unassigned", "total", "visibility", "max_depth"} <= set(t),
        sorted(set(t)),
    )
    check("三档可见性还是三个键", {"portal", "link", "private"} <= set(t["visibility"]), t["visibility"])
    probe = admin.post("/api/collections", {"name": "字段探针"}).json()["collection"]
    node = next((n for n in admin.get("/api/collections").json()["items"] if n["id"] == probe["id"]), {})
    check(
        "收藏夹节点的老字段都在",
        {"id", "name", "parent_id", "icon", "sort", "count", "total", "children"} <= set(node),
        sorted(node),
    )

    p = admin.get("/api/projects?limit=1&status=all").json()["items"]
    check("项目列表有数据", bool(p), "空库没法验")
    if p:
        need = {
            "slug", "title", "description", "kind", "visibility", "owner", "collection",
            "allow_download", "expire_action", "expires_at", "status", "views",
            "downloads", "created_at", "updated_at", "tags", "urls",
        }
        check("项目条目的老字段都在", need <= set(p[0]), sorted(need - set(p[0])))

    a = admin.get("/api/agents?limit=1").json()["items"]
    if a:
        need = {"id", "username", "display_name", "role", "active", "projects", "created_at"}
        check("成员条目的老字段都在", need <= set(a[0]), sorted(need - set(a[0])))

    meta = admin.get("/api/meta").json()
    need = {"site_title", "subtitle", "version", "online", "public_portal", "ttl_defaults",
            "default_expire_action", "theme", "site_icon", "tags", "title_rule", "rss"}
    check("meta 的老字段都在（新增的 project 只是叠加）", need <= set(meta), sorted(need - set(meta)))

    print("\n== [E] 老 CLI 写法 ==")
    token = admin.get("/api/auth/me").json().get("api_key") or ""
    rc, out = run_cli("whoami", "--json", token=token)
    check("whoami 老写法能用", rc == 0, out[:160])
    rc, out = run_cli("collections", "--json", token=token)
    check("collections 老写法能用", rc == 0, out[:160])
    rc, out = run_cli("ls", "--collection", "字段探针", "--json", token=token)
    check("ls --collection <名字> 老写法能用", rc == 0, out[:160])

    seed = admin.post(
        "/api/projects/link", {"link_url": "https://cli.example/x", "title": "CLI 兼容探针"}
    ).json()
    rc, out = run_cli("set", seed["slug"], "--visibility", "private", "--json", token=token)
    check("set --visibility 老写法能用", rc == 0, out[:160])
    rc, out = run_cli("show", seed["slug"], "--json", token=token)
    check("show 能读到改后的可见性", rc == 0 and "private" in out, out[:160])
    run_cli("rm", seed["slug"], "--json", token=token)
    admin.delete(f"/api/collections/{probe['id']}")


_ORIG_ZIP: Path | None = None
_ORIG_TOTAL = 0

try:
    main()
finally:
    # 不管中途红在哪，都把测试前的数据放回去
    if _ORIG_ZIP and _ORIG_ZIP.exists():
        print("\n== 收尾：恢复测试前的备份 ==")
        r = admin.upload("/api/backup/restore", "orig.zip", _ORIG_ZIP.read_bytes())
        check("把测试前的备份恢复回去", r.status_code == 200, r.status_code)
        check("项目数回到测试前", projects_total(admin) == _ORIG_TOTAL, f"{projects_total(admin)} vs {_ORIG_TOTAL}")

print(f"\n{ok} 通过 / {fail} 失败")
