"""导入 / 导出 / 备份：书签来回搬，整站打包带走。

权限：书签导入导出走 `publisher_user`（viewer 什么都不该动），
备份与恢复只给管理员——恢复会覆盖整个 data 目录。
"""
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from starlette.background import BackgroundTask

import json
import shutil
import tempfile
from pathlib import Path

from .. import backup as backup_mod, bookmarks, collections as colls
from ..db import db, log_event
from ..security import admin_user, publisher_user

router = APIRouter(prefix="/api", tags=["transfer"])

MAX_ZIP_BYTES = 2 * 1024 * 1024 * 1024  # 2GB 上限，够大但别让磁盘被撑爆


def _origin(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}".rstrip("/")


@router.post("/import/bookmarks")
async def import_bookmarks(
    request: Request,
    file: UploadFile | None = File(default=None),
    user: dict = Depends(publisher_user),
):
    """导入浏览器导出的书签 HTML（Chrome / Edge / Firefox / Safari 通用）。

    multipart 字段：
      file        书签文件（必填其一）
      text        直接贴 HTML（做预览用）
      parent_id   导入到哪个收藏夹下（留空 = 顶层）
      visibility  portal / link / private，默认 private
      tag         可选，给这批项目打一个标签
      dry_run     1 = 只预览不落库
    """
    form = await request.form()
    dry_run = str(form.get("dry_run") or "").lower() in ("1", "true", "yes", "on")
    raw = b""
    if file is not None and getattr(file, "filename", ""):
        raw = await file.read()
        if len(raw) > bookmarks.MAX_BYTES:
            raise HTTPException(status_code=413, detail="书签文件超过 8MB")
    else:
        raw = str(form.get("text") or "").encode("utf-8")
    if not raw:
        raise HTTPException(status_code=400, detail="没有收到书签文件")

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = raw.decode("gb18030")  # 老版本 Windows 导出的可能是 GBK
        except UnicodeDecodeError:
            raise HTTPException(status_code=422, detail="书签文件编码无法识别，请用 UTF-8 导出") from None

    if "<a" not in text.lower() and "<h3" not in text.lower():
        raise HTTPException(status_code=422, detail="这看起来不是浏览器的书签文件（没有 <A>/<H3>）")

    parent_id = form.get("parent_id")
    parent_id = int(parent_id) if str(parent_id or "").strip().isdigit() else None
    if parent_id:
        with db() as conn:
            crow = colls.get(conn, parent_id, user)
        if crow["owner_id"] != user["id"]:
            raise HTTPException(status_code=409, detail="该收藏夹属于其他成员")

    result = bookmarks.import_bookmarks(
        user,
        text,
        parent_id=parent_id,
        visibility=str(form.get("visibility") or "private"),
        tag=str(form.get("tag") or ""),
        dry_run=dry_run,
    )
    if not dry_run:
        log_event(
            "import",
            user["id"],
            None,
            f"导入书签 {result['created']} 条 / 收藏夹 {result['folders_created']} 个",
        )
    return {"ok": True, **result}


@router.get("/export/bookmarks")
def export_bookmarks(
    request: Request,
    collection: str = "",
    user: dict = Depends(publisher_user),
):
    """导出成 Netscape 书签 HTML，Chrome / Edge / Firefox 都能直接导入。"""
    cid = None
    if collection and collection not in ("none", "0", "all"):
        try:
            cid = int(collection)
        except ValueError:
            raise HTTPException(status_code=400, detail="collection 参数不合法") from None
        with db() as conn:
            colls.get(conn, cid, user)  # 权限
    html_text, total = bookmarks.export_html(user, _origin(request), cid)
    name = "bookmarks.html" if not cid else f"bookmarks-{cid}.html"
    resp = Response(content=html_text.encode("utf-8"), media_type="text/html; charset=utf-8")
    resp.headers["Content-Disposition"] = f'attachment; filename="{name}"'
    resp.headers["X-Bookmark-Count"] = str(total)
    return resp


@router.get("/backup")
def download_backup(user: dict = Depends(admin_user)):
    """打一个全站备份包直接下载（数据库 + 项目文件 + zip + 图标）。"""
    if not Path(backup_mod.config.DB_PATH).exists():
        raise HTTPException(status_code=409, detail="数据库还没初始化")
    zip_path = backup_mod.build_zip()
    log_event("backup", user["id"], None, f"下载备份 {zip_path.name}")
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=zip_path.name,
        background=BackgroundTask(lambda: shutil.rmtree(zip_path.parent, ignore_errors=True)),
    )


@router.post("/backup/inspect")
async def inspect_backup(file: UploadFile = File(...), user: dict = Depends(admin_user)):
    """先看包里有什么，再决定要不要恢复。"""
    data = await file.read()
    if len(data) > MAX_ZIP_BYTES:
        raise HTTPException(status_code=413, detail="备份包过大")
    tmp = Path(tempfile.mkdtemp(prefix="pvinspect-")) / "backup.zip"
    try:
        tmp.write_bytes(data)
        try:
            info = backup_mod.inspect(tmp)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - 坏 zip
            raise HTTPException(status_code=422, detail=f"读不了这个 zip：{exc}") from exc
        return {"ok": True, **info}
    finally:
        shutil.rmtree(tmp.parent, ignore_errors=True)


@router.post("/backup/restore")
async def restore_backup(file: UploadFile = File(...), user: dict = Depends(admin_user)):
    """用备份包覆盖现网数据。旧数据会留在 data/.backup-before-restore-<时间>/。"""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="没有收到文件")
    if len(data) > MAX_ZIP_BYTES:
        raise HTTPException(status_code=413, detail="备份包过大")
    tmp = Path(tempfile.mkdtemp(prefix="pvrestorezip-")) / "backup.zip"
    try:
        tmp.write_bytes(data)
        try:
            result = backup_mod.restore(tmp)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"恢复失败：{exc}") from exc
    finally:
        shutil.rmtree(tmp.parent, ignore_errors=True)
    backup_mod.cleanup_old_safety()
    try:
        # 恢复已经完成了，别让一条日志把成功的操作变成 500
        log_event("restore", user["id"], None, f"从备份恢复，{json.dumps(result.get('counts', {}))}")
    except Exception as exc:  # noqa: BLE001
        print(f"[backup] 记录恢复日志失败：{exc}", flush=True)
    return result
