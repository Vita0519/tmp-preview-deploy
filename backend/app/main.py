"""FastAPI 入口：API + 访客页 + 构建后的 SPA 同端口托管。

Copyright (C) 2026 vita0519 · AGPL-3.0-only（见仓库根目录 LICENSE / NOTICE）
"""
import asyncio
import mimetypes
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import cleanup, config, storage, tagspec, views
from .db import init_db
from .routers import agents, auth, collections, projects, public, settings, transfer
from .security import bootstrap_admin

# 图标与清单文件的 MIME：Python 的 mimetypes 还不认识 webmanifest
mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("image/x-icon", ".ico")
mimetypes.add_type("image/png", ".png")

STOP = asyncio.Event()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    bootstrap_admin()
    stale = storage.cleanup_stale_tmp()
    if stale:
        print(f"[boot] 清理上次残留的临时目录 {stale} 个", flush=True)
    stop = asyncio.Event()
    tasks = [
        asyncio.create_task(cleanup.flush_loop(stop)),
        asyncio.create_task(cleanup.sweep_loop(stop)),
    ]
    print(f"[boot] data={config.DATA_DIR} static={config.DIST_DIR}", flush=True)
    try:
        yield
    finally:
        stop.set()
        for t in tasks:
            t.cancel()
        try:
            views.flush()
        except Exception as exc:
            print(f"[shutdown] flush failed: {exc}", flush=True)


app = FastAPI(title="tmp-preview", version=config.VERSION, lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(GZipMiddleware, minimum_size=1024)

app.include_router(auth.router)
app.include_router(collections.router)
app.include_router(projects.router)
app.include_router(agents.router)
app.include_router(settings.router)
app.include_router(transfer.router)
app.include_router(public.router)


@app.get("/api/health")
async def health():
    return {"ok": True, "service": "tmp-preview", "version": config.VERSION}


@app.exception_handler(tagspec.TagError)
async def tag_error_handler(request: Request, exc: tagspec.TagError):
    """标签不合规一律 422，detail 是给人看的一句中文，前端直接 toast。"""
    return JSONResponse(status_code=422, content={"detail": str(exc)})


_assets = config.DIST_DIR / "assets"
if _assets.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_assets)), name="assets")
_fav = config.DIST_DIR / "favicon.svg"
if _fav.is_file():
    @app.get("/favicon.svg")
    async def favicon():
        return FileResponse(_fav)


@app.get("/{full_path:path}")
async def spa(full_path: str, request: Request):
    """非 API 路径一律交给前端路由；构建产物不存在时给出提示。"""
    index = config.DIST_DIR / "index.html"
    if not index.is_file():
        return HTMLResponse(
            "<h1 style='font-family:system-ui;padding:40px'>前端尚未构建</h1>"
            "<p style='font-family:system-ui;padding:0 40px;color:#8b93a3'>"
            "本地开发：<code>cd frontend &amp;&amp; npm run dev</code><br>"
            "生产：<code>docker compose up -d --build</code></p>",
            status_code=503,
        )
    if full_path:
        candidate = (config.DIST_DIR / full_path).resolve()
        if config.DIST_DIR in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
    return FileResponse(index, headers={"Cache-Control": "no-cache"})
