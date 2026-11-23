"""分组 API：两级树、增删改、以及删分组时项目的去向。"""
from fastapi import APIRouter, Depends, HTTPException, Request

from .. import collections as colls, storage, views
from ..db import db, log_event, tx
from ..security import current_user, publisher_user

router = APIRouter(
    prefix="/api", tags=["collections"], dependencies=[Depends(publisher_user)]
)


@router.get("/collections")
def list_collections(user: dict = Depends(current_user)):
    """两级树 + 每个分组的直属项目数 + 未归类数量。"""
    with db() as conn:
        return colls.tree(conn, user)


@router.post("/collections")
async def create_collection(request: Request, user: dict = Depends(current_user)):
    body = await request.json()
    with tx() as conn:
        cid = colls.create(
            conn,
            user["id"],
            body.get("name"),
            body.get("parent_id") or None,
            str(body.get("icon") or ""),
        )
        row = conn.execute("SELECT * FROM collections WHERE id=?", (cid,)).fetchone()
    log_event("collection", user["id"], None, f"新建分组 {row['name']}")
    return {"ok": True, "collection": dict(row)}


@router.patch("/collections/{cid}")
async def patch_collection(cid: int, request: Request, user: dict = Depends(current_user)):
    body = await request.json()
    with tx() as conn:
        colls.update(conn, cid, user, body)
        row = conn.execute("SELECT * FROM collections WHERE id=?", (cid,)).fetchone()
    log_event("collection", user["id"], None, f"修改分组 {row['name']}")
    return {"ok": True, "collection": dict(row)}


@router.delete("/collections/{cid}")
def delete_collection(
    cid: int,
    with_projects: int = 0,
    user: dict = Depends(current_user),
):
    """删分组。默认把里面的项目退回「未归类」，`with_projects=1` 才连项目一起删。"""
    with db() as conn:
        colls.get(conn, cid, user)  # 权限与存在性
        ids = colls.subtree_ids(conn, cid)
        rows = colls.project_rows(conn, ids)

    # 先删文件再删记录：文件占用/权限问题不该让记录变成孤儿
    if with_projects:
        for r in rows:
            try:
                storage.remove_project_files(r["slug"])
            except OSError as exc:
                print(f"[collections] 清文件失败 {r['slug']}: {exc}", flush=True)
            views.reset(r["id"])

    with tx() as conn:
        result = colls.delete(conn, cid, user, with_projects=bool(with_projects))
    log_event(
        "collection",
        user["id"],
        None,
        f"删除分组 {result['name']}（项目 {result['deleted_projects'] or result['moved_to_unassigned']} 个）",
    )
    return {"ok": True, **result}
