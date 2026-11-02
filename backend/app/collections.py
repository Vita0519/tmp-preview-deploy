"""收藏夹：把项目归到「一级收藏夹 → 二级子收藏夹」。

设计取舍：
* 表里只有 `parent_id`，没有写死 `level` —— 现在限制两层是交互决定，不是数据限制，
  以后要放开深度不用迁表。
* 归属跟项目一致：管理员能看全部，其他人只看自己的。
* 删除收藏夹默认**只删壳**：里面的项目退回「未归类」，不连坐。要连项目一起删得显式要求。
"""
from __future__ import annotations

import time

from fastapi import HTTPException

MAX_DEPTH = 2          # 目前只做两层
MAX_NAME = 20          # 收藏夹名长度上限（字符数，不按宽度算，中文 20 个字够长了）


def now_ms() -> int:
    return int(time.time() * 1000)


def norm_name(name: str) -> str:
    s = str(name or "").strip()
    if not s:
        raise HTTPException(status_code=422, detail="收藏夹名称不能为空")
    if len(s) > MAX_NAME:
        raise HTTPException(status_code=422, detail=f"收藏夹名称最多 {MAX_NAME} 个字")
    return s


def depth_of(conn, parent_id) -> int:
    """父级的深度；parent_id 为空算 0。"""
    if not parent_id:
        return 0
    row = conn.execute("SELECT id, parent_id FROM collections WHERE id=?", (parent_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="上级收藏夹不存在")
    return 2 if row["parent_id"] else 1


def ensure_parent(conn, parent_id, owner_id: int) -> None:
    """父级必须是本人的（或管理员指定的那个人的）一级收藏夹。"""
    if not parent_id:
        return
    row = conn.execute("SELECT * FROM collections WHERE id=?", (parent_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="上级收藏夹不存在")
    if row["owner_id"] != owner_id:
        raise HTTPException(status_code=409, detail="上级收藏夹属于其他成员")
    if row["parent_id"]:
        raise HTTPException(status_code=422, detail="只支持两级收藏夹，不能挂在子收藏夹下面")


def visible_rows(conn, user: dict) -> list:
    if user["role"] == "admin":
        return conn.execute("SELECT * FROM collections ORDER BY sort, id").fetchall()
    return conn.execute(
        "SELECT * FROM collections WHERE owner_id=? ORDER BY sort, id", (user["id"],)
    ).fetchall()


def get(conn, cid: int, user: dict):
    row = conn.execute("SELECT * FROM collections WHERE id=?", (cid,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="收藏夹不存在")
    if user["role"] != "admin" and row["owner_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="这不是你的收藏夹")
    return row


def child_ids(conn, cid: int) -> list[int]:
    rows = conn.execute("SELECT id FROM collections WHERE parent_id=?", (cid,)).fetchall()
    return [r["id"] for r in rows]


def subtree_ids(conn, cid: int) -> list[int]:
    return [cid] + child_ids(conn, cid)


def counts(conn, user: dict) -> dict:
    """每个收藏夹下**直属**项目数（父级的合计由前端把子级加上去）。

    计数口径跟项目列表一致：管理员算全站，其他成员只算自己名下的——
    否则侧栏的「未归类」会带出别人的项目数，看着像能看见别人的东西。
    """
    where = "status='active'"
    args: list = []
    if user["role"] != "admin":
        where += " AND owner_id=?"
        args.append(user["id"])
    rows = conn.execute(
        f"SELECT collection_id AS cid, COUNT(*) AS n FROM projects "
        f"WHERE {where} AND collection_id IS NOT NULL GROUP BY collection_id", args
    ).fetchall()
    out = {r["cid"]: r["n"] for r in rows}
    unassigned = conn.execute(
        f"SELECT COUNT(*) AS n FROM projects WHERE {where} AND collection_id IS NULL", args
    ).fetchone()
    out[0] = unassigned["n"] if unassigned else 0
    return out


def visibility_counts(conn, user: dict) -> dict:
    """三档可见性各有多少项目——侧栏把它们做成常驻的「智能收藏夹」。"""
    where = "status='active'"
    args: list = []
    if user["role"] != "admin":
        where += " AND owner_id=?"
        args.append(user["id"])
    rows = conn.execute(
        f"SELECT visibility, COUNT(*) AS n FROM projects WHERE {where} GROUP BY visibility", args
    ).fetchall()
    out = {"portal": 0, "link": 0, "private": 0}
    for r in rows:
        if r["visibility"] in out:
            out[r["visibility"]] = r["n"]
    return out


def tree(conn, user: dict) -> dict:
    """返回 {items: 树, unassigned: N, total: N}。"""
    rows = visible_rows(conn, user)
    cnt = counts(conn, user)
    nodes = {}
    roots: list[dict] = []
    for r in rows:
        nodes[r["id"]] = {
            "id": r["id"],
            "name": r["name"],
            "parent_id": r["parent_id"],
            "icon": r["icon"] or "",
            "sort": r["sort"],
            "count": cnt.get(r["id"], 0),
            "total": cnt.get(r["id"], 0),
            "children": [],
        }
    for r in rows:
        node = nodes[r["id"]]
        if r["parent_id"] and r["parent_id"] in nodes:
            nodes[r["parent_id"]]["children"].append(node)
            nodes[r["parent_id"]]["total"] += node["count"]
        else:
            roots.append(node)
    loose = cnt.get(0, 0)
    return {
        "items": roots,
        "unassigned": loose,
        # 「全部项目」= 各收藏夹合计 + 未归类，跟列表页的总数对得上
        "total": sum(n["total"] for n in roots) + loose,
        # 三档可见性的数量：侧栏把它们当常驻分类，所以工具栏里的可见性下拉可以省掉
        "visibility": visibility_counts(conn, user),
        "max_depth": MAX_DEPTH,
    }


def create(conn, owner_id: int, name: str, parent_id=None, icon: str = "") -> int:
    name = norm_name(name)
    ensure_parent(conn, parent_id, owner_id)
    dup = conn.execute(
        "SELECT id FROM collections WHERE owner_id=? AND ifnull(parent_id,0)=? "
        "AND lower(trim(name))=lower(?)",
        (owner_id, parent_id or 0, name),
    ).fetchone()
    if dup:
        raise HTTPException(status_code=409, detail=f"已经有同名收藏夹「{name}」")
    t = now_ms()
    cur = conn.execute(
        "INSERT INTO collections(name, parent_id, owner_id, icon, sort, created_at, updated_at) "
        "VALUES(?,?,?,?,?,?,?)",
        (name, parent_id or None, owner_id, icon or "", t, t, t),
    )
    return int(cur.lastrowid)


def update(conn, cid: int, user: dict, body: dict) -> None:
    row = get(conn, cid, user)
    sets, args = [], []
    if "name" in body:
        sets.append("name=?")
        args.append(norm_name(body["name"]))
    if "icon" in body:
        sets.append("icon=?")
        args.append(str(body["icon"] or "")[:16])
    if "sort" in body:
        sets.append("sort=?")
        args.append(int(body["sort"]))
    if "parent_id" in body:
        new_parent = body["parent_id"] or None
        if new_parent == cid:
            raise HTTPException(status_code=422, detail="不能把自己设为自己的上级")
        if new_parent:
            ensure_parent(conn, new_parent, row["owner_id"])
            # 移动的是别人时，父级也得是同一个人的
            if row["parent_id"] and child_ids(conn, cid):
                raise HTTPException(status_code=422, detail="带子收藏夹的收藏夹不能再变成子级")
        sets.append("parent_id=?")
        args.append(new_parent)
    if not sets:
        return
    # 同层重名检查（改名/移动后）
    name = None
    parent = row["parent_id"]
    if "name" in body:
        name = norm_name(body["name"])
    if "parent_id" in body:
        parent = body["parent_id"] or None
    if name is not None or "parent_id" in body:
        name = name or row["name"]
        dup = conn.execute(
            "SELECT id FROM collections WHERE owner_id=? AND ifnull(parent_id,0)=? "
            "AND lower(trim(name))=lower(?) AND id<>?",
            (row["owner_id"], parent or 0, name, cid),
        ).fetchone()
        if dup:
            raise HTTPException(status_code=409, detail=f"同一层已经有「{name}」了")
    sets.append("updated_at=?")
    args.append(now_ms())
    args.append(cid)
    conn.execute(f"UPDATE collections SET {', '.join(sets)} WHERE id=?", args)


def project_rows(conn, ids: list[int]) -> list:
    """收藏夹（含子夹）里的项目，删壳时用来决定谁退回未归类、谁连文件一起删。"""
    if not ids:
        return []
    marks = ",".join("?" * len(ids))
    return conn.execute(
        f"SELECT id, slug, title FROM projects WHERE collection_id IN ({marks})", ids
    ).fetchall()


def delete(conn, cid: int, user: dict, with_projects: bool = False) -> dict:
    """删收藏夹。默认只删壳：项目退回未归类；with_projects=True 时连项目记录一起删。

    项目文件不在这里删——router 会先按 slug 清盘（storage 有重试与兜底），
    这里只负责数据库，避免这个模块反向依赖 storage。
    """
    row = get(conn, cid, user)
    ids = subtree_ids(conn, cid)
    marks = ",".join("?" * len(ids))
    n = len(project_rows(conn, ids))
    if with_projects:
        conn.execute(f"DELETE FROM projects WHERE collection_id IN ({marks})", ids)
    else:
        conn.execute(f"UPDATE projects SET collection_id=NULL WHERE collection_id IN ({marks})", ids)
    conn.execute(f"DELETE FROM collections WHERE id IN ({marks})", ids)
    return {
        "removed": len(ids),
        "moved_to_unassigned": 0 if with_projects else n,
        "deleted_projects": n if with_projects else 0,
        "name": row["name"],
    }
