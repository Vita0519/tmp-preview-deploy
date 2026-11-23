"""浏览器书签的导入 / 导出（Netscape Bookmark 格式）。

Chrome、Edge、Firefox、Safari、Opera 导出的书签文件都是同一套 `<!DOCTYPE NETSCAPE-Bookmark-file-1>`
HTML，所以只要按它解析，就能一次吃下所有主流浏览器：

    <DL><p>
      <DT><H3>书签栏</H3>
      <DL><p>
        <DT><A HREF="https://a.example">A</A>
        <DT><H3>子文件夹</H3>
        <DL><p><DT><A HREF="https://b.example">B</A></DL><p>
      </DL><p>
    </DL><p>

映射规则（跟产品约定一致：两级分组）：
* 路径第一段 → 一级分组；第二段 → 子分组；更深的层级压到第二段里，不丢书签；
* 书签 → 外链项目（kind=link），默认**私有**、永久有效 —— 导入是私事，公开与否自己挑；
* 同一个 URL 在自己名下已存在就跳过（重复导入同一个文件是幂等的）；
* 标题撞车时加 `(2)`、`(3)`，并且始终服从项目名 10 个中文字符的上限。
"""
from __future__ import annotations

import html
import re
import time
from html.parser import HTMLParser

from . import collections as colls, namerule, storage, tagspec
from .db import db, set_tags, tx

MAX_BYTES = 8 * 1024 * 1024   # 8MB，够放几万个书签了
MAX_ITEMS = 2000              # 单次导入上限，防止一个文件把库灌满
SKIP_SCHEMES = ("javascript:", "place:", "data:", "chrome:", "about:", "file:")


def now_ms() -> int:
    return int(time.time() * 1000)


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.pending: str | None = None
        self.folders: list[list[str]] = []
        self.items: list[dict] = []
        self._in_h3 = False
        self._h3: list[str] = []
        self._in_a = False
        self._a: list[str] = []
        self._href = ""

    # ---- 解析 ----
    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "h3":
            self._h3 = []
            self._in_h3 = True
        elif tag == "dl":
            if self.pending is not None:
                self.stack.append(self.pending)
                self.pending = None
            else:
                # 根 DL，或者上一个文件夹没开 DL —— 用空串占位保持层级对齐
                self.stack.append("")
        elif tag == "a":
            self._a = []
            self._in_a = True
            for k, v in attrs:
                if k.lower() == "href":
                    self._href = (v or "").strip()
                    break
        elif tag == "dt" and self.pending is not None:
            # <H3> 后面没跟 <DL>（空文件夹），别让文件分组名污染下一个 DL
            self.pending = None

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "h3" and self._in_h3:
            self._in_h3 = False
            name = "".join(self._h3).strip()
            if name:
                self.pending = name
                self.folders.append([p for p in self.stack if p] + [name])
            else:
                self.pending = None
        elif tag == "dl":
            if self.stack:
                self.stack.pop()
        elif tag == "a" and self._in_a:
            self._in_a = False
            title = "".join(self._a).strip()
            if self._href:
                self.items.append({
                    "title": title,
                    "url": self._href,
                    "path": [p for p in self.stack if p],
                })
            self._href = ""

    def handle_data(self, data):
        if self._in_h3:
            self._h3.append(data)
        elif self._in_a:
            self._a.append(data)


def parse(text: str) -> dict:
    """把书签 HTML 解析成 {folders:[[名...]], items:[{title,url,path}]}。"""
    p = _Parser()
    p.feed(text or "")
    p.close()
    # 去重但不打乱顺序
    seen, folders = set(), []
    for f in p.folders:
        key = tuple(f)
        if key not in seen:
            seen.add(key)
            folders.append(f)
    return {"folders": folders, "items": p.items}


def _valid_url(url: str) -> bool:
    u = (url or "").strip()
    if not u or u.lower().startswith(SKIP_SCHEMES):
        return False
    return bool(re.match(r"^https?://[^\s]+$", u, re.I))


def _clean_folder(name: str) -> str:
    s = re.sub(r"\s+", " ", str(name or "")).strip()
    return s[: colls.MAX_NAME]


def _map_path(path: list[str]) -> tuple[str, str]:
    """书签路径 → (一级名, 二级名)。更深的层级折到二级里。"""
    clean = [_clean_folder(x) for x in path if _clean_folder(x)]
    if not clean:
        return "", ""
    if len(clean) == 1:
        return clean[0], ""
    return clean[0], clean[1]


def _unique_slug(conn, base: str) -> str:
    slug = storage.slugify(base) or "bookmark"
    slug = slug[:60]
    if not conn.execute("SELECT 1 FROM projects WHERE slug=?", (slug,)).fetchone():
        return slug
    for i in range(2, 1000):
        cand = f"{slug}-{i}"
        if not conn.execute("SELECT 1 FROM projects WHERE slug=?", (cand,)).fetchone():
            return cand
    return f"{slug}-{int(time.time())}"


def _mk_title(conn, owner_id: int, raw: str, url: str) -> str:
    """给书签挑一个不重名、不超长的项目名。"""
    fallback = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
    base = namerule.clamp(str(raw or "").strip() or fallback)
    if not base:
        base = "书签"

    def taken(t: str) -> bool:
        return bool(conn.execute(
            "SELECT 1 FROM projects WHERE owner_id=? AND lower(trim(title))=lower(?)",
            (owner_id, t),
        ).fetchone())

    if not taken(base):
        return base
    for i in range(2, 100):
        suffix = f"({i})"
        stem = namerule.clamp(base, namerule.MAX_WIDTH - namerule.width(suffix))
        cand = f"{stem}{suffix}"
        if not taken(cand):
            return cand
    return namerule.clamp(f"{base}{int(time.time()) % 1000}")


def import_bookmarks(
    user: dict,
    text: str,
    parent_id=None,
    visibility: str = "private",
    tag: str = "",
    dry_run: bool = False,
) -> dict:
    """执行导入。dry_run=True 只解析、不落库，用来给用户看预览。"""
    data = parse(text)
    items = data["items"]
    if len(items) > MAX_ITEMS:
        items = items[:MAX_ITEMS]

    owner_id = user["id"]
    plan_folders: list[tuple[str, str]] = []   # [(一级, 二级)]
    seen_folders = set()
    for f in data["folders"]:
        root, sub = _map_path(f)
        if not root:
            continue
        # 已经指定了目标分组时，目标自己就是一级，只能再往下放一层：
        # 书签里的一级文件夹变子分组，更深的层折进去（不然会做出第三层，筛选时又漏掉）。
        keys = [(root, "")] if parent_id else [(root, ""), (root, sub)]
        for key in keys:
            if key[1] == "" and key in seen_folders:
                continue
            if key not in seen_folders:
                seen_folders.add(key)
                plan_folders.append(key)

    plan = []
    seen_url = set()
    if not dry_run:
        with db() as conn:
            seen_url = {
                r["link_url"]
                for r in conn.execute(
                    "SELECT link_url FROM projects WHERE owner_id=? AND link_url IS NOT NULL",
                    (owner_id,),
                ).fetchall()
            }

    skipped_dup = skipped_bad = 0
    for it in items:
        url = it["url"].strip()
        if not _valid_url(url):
            skipped_bad += 1
            continue
        if url in seen_url:
            skipped_dup += 1
            continue
        seen_url.add(url)
        plan.append({**it, "url": url, "folder": _map_path(it["path"])})

    if dry_run:
        return {
            "dry_run": True,
            "folders": plan_folders,
            "items": [{**p, "folder": list(p["folder"])} for p in plan[:200]],
            "parsed": len(data["items"]),
            "will_create": len(plan),
            "folders_total": len(plan_folders),
            "skipped_duplicate": skipped_dup,
            "skipped_invalid": skipped_bad,
            "truncated": max(0, len(data["items"]) - MAX_ITEMS),
        }

    vis = visibility if visibility in ("portal", "link", "private") else "private"
    tag_list = tagspec.clean(tag)[:1] if tag else []
    created = 0
    folder_ids: dict[tuple[str, str], int] = {}
    t = now_ms()

    with tx() as conn:
        # 1) 分组：先一级，再二级
        for root, sub in plan_folders:
            if (root, "") not in folder_ids:
                folder_ids[(root, "")] = _ensure_folder(conn, owner_id, root, parent_id)
            if sub:
                folder_ids[(root, sub)] = _ensure_folder(
                    conn, owner_id, sub, folder_ids[(root, "")] )
        # 2) 书签 → 外链项目
        for p in plan:
            root, sub = p["folder"]
            if root:
                cid = folder_ids.get((root, sub)) or folder_ids.get((root, ""))
            else:
                cid = parent_id
            title = _mk_title(conn, owner_id, p["title"], p["url"])
            slug = _unique_slug(conn, title)
            cur = conn.execute(
                "INSERT INTO projects(slug, title, description, owner_id, kind, link_url, visibility, "
                "collection_id, allow_download, expire_action, expires_at, status, created_at, updated_at) "
                "VALUES(?,?,?,?,'link',?,?,?,0,'block',NULL,'active',?,?)",
                (slug, title, "", owner_id, p["url"], vis, cid, t, t),
            )
            if tag_list:
                set_tags(conn, cur.lastrowid, tag_list)
            created += 1

    return {
        "dry_run": False,
        "created": created,
        "folders_created": len(folder_ids),
        "parsed": len(data["items"]),
        "skipped_duplicate": skipped_dup,
        "skipped_invalid": skipped_bad,
        "truncated": max(0, len(data["items"]) - MAX_ITEMS),
        "visibility": vis,
    }


def _ensure_folder(conn, owner_id: int, name: str, parent_id) -> int:
    """按名字找分组，没有就建。重复导入同一个文件时不会长出一堆同名分组。"""
    row = conn.execute(
        "SELECT id FROM collections WHERE owner_id=? AND ifnull(parent_id,0)=? "
        "AND lower(trim(name))=lower(?)",
        (owner_id, parent_id or 0, name),
    ).fetchone()
    if row:
        return int(row["id"])
    t = now_ms()
    cur = conn.execute(
        "INSERT INTO collections(name, parent_id, owner_id, icon, sort, created_at, updated_at) "
        "VALUES(?,?,?,'',?,?,?)",
        (name, parent_id or None, owner_id, t, t, t),
    )
    return int(cur.lastrowid)


# ---------------------------------------------------------------- 导出

def _esc(s: str) -> str:
    return html.escape(str(s or ""), quote=True)


def export_html(user: dict, origin: str = "", collection_id=None) -> tuple[str, int]:
    """按分组层级导出成 Netscape 书签 HTML，浏览器可直接导入。返回 (html, 条数)。"""
    with db() as conn:
        if user["role"] == "admin":
            where, args = "p.status='active'", []
        else:
            where, args = "p.status='active' AND p.owner_id=?", [user["id"]]
        if collection_id:
            ids = colls.subtree_ids(conn, int(collection_id))
            marks = ",".join("?" * len(ids))
            where += f" AND p.collection_id IN ({marks})"
            args += ids
        rows = conn.execute(
            "SELECT p.slug, p.title, p.kind, p.link_url, p.collection_id, p.created_at "
            f"FROM projects p WHERE {where} ORDER BY p.created_at",
            args,
        ).fetchall()
        coll_rows = colls.visible_rows(conn, user)

    by_id = {c["id"]: c for c in coll_rows}
    roots: list[dict] = []
    children: dict[int, list] = {}
    for c in coll_rows:
        if c["parent_id"] and c["parent_id"] in by_id:
            children.setdefault(c["parent_id"], []).append(c)
        else:
            roots.append(c)

    grouped: dict[int, list] = {}
    loose: list = []
    for r in rows:
        cid = r["collection_id"] if r["collection_id"] in by_id else 0
        (grouped.setdefault(cid, []) if cid else loose).append(r)

    def item_html(r, indent: str) -> str:
        url = r["link_url"] or f"{origin}/v/{r['slug']}"
        ts = int((r["created_at"] or 0) / 1000)
        return f'{indent}<DT><A HREF="{_esc(url)}" ADD_DATE="{ts}">{_esc(r["title"])}</A>'

    def folder_open(name: str, ts: int, indent: str) -> list[str]:
        return [
            f'{indent}<DT><H3 ADD_DATE="{int((ts or 0) / 1000)}">{_esc(name)}</H3>',
            f"{indent}<DL><p>",
        ]

    out = [
        "<!DOCTYPE NETSCAPE-Bookmark-file-1>",
        "<!-- This is an automatically generated file. It can be imported by Chrome / Edge / Firefox. -->",
        '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
        "<TITLE>Bookmarks</TITLE>",
        "<H1>Bookmarks</H1>",
        "<DL><p>",
    ]
    total = 0
    for root in roots:
        out += folder_open(root["name"], root["created_at"], "    ")
        for r in grouped.get(root["id"], []):
            out.append(item_html(r, "        "))
            total += 1
        for sub in children.get(root["id"], []):
            out += folder_open(sub["name"], sub["created_at"], "        ")
            for r in grouped.get(sub["id"], []):
                out.append(item_html(r, "            "))
                total += 1
            out.append("        </DL><p>")
        out.append("    </DL><p>")
    if loose and not collection_id:
        out += folder_open("未归类", 0, "    ")
        for r in loose:
            out.append(item_html(r, "        "))
            total += 1
        out.append("    </DL><p>")
    out.append("</DL><p>")
    return "\n".join(out) + "\n", total
