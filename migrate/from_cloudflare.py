#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 Cloudflare Workers + KV 上已发布的项目，整体搬到本地 SQLite + 磁盘。

用法:
  docker compose stop                    # 先停服务，避免与后台任务抢写
  export CF_API_TOKEN=xxx
  export CF_ACCOUNT_ID=xxx
  export CF_KV_NAMESPACE_ID=xxx
  python migrate/from_cloudflare.py --agent admin
  python migrate/from_cloudflare.py --dry-run            # 只列清单
  python migrate/from_cloudflare.py --only landing-v2    # 只迁一个

KV 键布局（与旧 Worker 一致）:
  meta:<slug>              → 项目元数据
  file:<slug>:<ph(path)>   → 文件记录 {path,size,type,chunks,etag}
  chunk:<slug>:<ph(path)>:<i> → base64 分片
  views:<slug> / pv:d:<slug>  → 已落库访问数 / 待落库增量
"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.cloudflare.com/client/v4"


def http_get(url: str, token: str, proxy: str = "", retries: int = 3) -> bytes:
    last = ""
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "tmp-preview-migrate/2.0",
        })
        handlers = []
        if proxy:
            handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
        opener = urllib.request.build_opener(*handlers)
        try:
            with opener.open(req, timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:300]
            if e.code in (429, 500, 502, 503):
                last = f"HTTP {e.code} {body}"
                time.sleep(1.5 * (attempt + 1))
                continue
            raise SystemExit(f"Cloudflare HTTP {e.code}: {body}")
        except Exception as e:
            last = str(e)
            time.sleep(1.2 * (attempt + 1))
    raise SystemExit(f"Cloudflare 请求失败（已重试 {retries} 次）: {last}")


def cf_result(url: str, token: str, proxy: str = ""):
    payload = json.loads(http_get(url, token, proxy) or b"{}")
    if not payload.get("success", False):
        raise SystemExit(f"Cloudflare 返回错误: {payload.get('errors')}")
    return payload


def list_keys(account: str, ns: str, token: str, prefix: str, proxy: str = "") -> list[str]:
    """KV 列表接口带游标分页。"""
    out: list[str] = []
    cursor = None
    while True:
        q = {"limit": "1000", "prefix": prefix}
        if cursor:
            q["cursor"] = cursor
        url = f"{API}/accounts/{account}/storage/kv/namespaces/{ns}/keys?" + urllib.parse.urlencode(q)
        payload = cf_result(url, token, proxy)
        out.extend(k["name"] for k in payload.get("result") or [])
        cursor = (payload.get("result_info") or {}).get("cursor")
        if not cursor:
            break
    return out


def get_value(account: str, ns: str, token: str, key: str, proxy: str = "") -> str | None:
    enc = urllib.parse.quote(key, safe="")
    url = f"{API}/accounts/{account}/storage/kv/namespaces/{ns}/values/{enc}"
    try:
        return http_get(url, token, proxy).decode("utf-8", "replace")
    except SystemExit:
        return None


def get_json_key(account, ns, token, key, proxy=""):
    raw = get_value(account, ns, token, key, proxy)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def path_hash(p: str) -> str:
    """与旧 Worker pathHash 完全一致：按 UTF-16 码元做 FNV-1a 32 位。"""
    h = 0x811C9DC5
    units = p.encode("utf-16-le")
    for i in range(0, len(units), 2):
        code = units[i] | (units[i + 1] << 8)
        h ^= code
        h = (h * 0x01000193) & 0xFFFFFFFF
    return f"{h:08x}-{len(units)//2:x}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", default=os.environ.get("CF_ACCOUNT_ID", ""))
    ap.add_argument("--namespace", default=os.environ.get("CF_KV_NAMESPACE_ID", ""))
    ap.add_argument("--token", default=os.environ.get("CF_API_TOKEN", ""))
    ap.add_argument("--agent", default="admin", help="迁移后项目的归属成员账号")
    ap.add_argument("--data-dir", default=os.environ.get("DATA_DIR", str(ROOT / "data")))
    ap.add_argument("--proxy", default=os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or "")
    ap.add_argument("--only", action="append", default=[], help="只迁移指定 slug，可重复")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not (args.account and args.namespace and args.token):
        print("缺少 CF_ACCOUNT_ID / CF_KV_NAMESPACE_ID / CF_API_TOKEN", file=sys.stderr)
        return 2

    os.environ["DATA_DIR"] = str(Path(args.data_dir).resolve())
    sys.path.insert(0, str(ROOT / "backend"))
    from app import storage  # noqa: E402
    from app.config import DATA_DIR  # noqa: E402
    from app.db import db, init_db, tx  # noqa: E402
    from app.security import now_ms  # noqa: E402

    init_db()
    print(f"→ 数据目录: {DATA_DIR}")

    with db() as conn:
        owner = conn.execute("SELECT id FROM users WHERE username=?", (args.agent,)).fetchone()
    if not owner:
        print(f"成员 {args.agent} 不存在。先启动一次服务创建账号，再执行迁移。", file=sys.stderr)
        return 2

    print("→ 读取 KV 清单…")
    slugs = []
    for k in list_keys(args.account, args.namespace, args.token, "meta:", args.proxy):
        if k == "meta:__index__":
            continue
        slug = k.split(":", 1)[1]
        if args.only and slug not in args.only:
            continue
        slugs.append(slug)
    print(f"  发现 {len(slugs)} 个项目")

    ok, skipped, failed = 0, 0, 0
    for slug in slugs:
        meta = get_json_key(args.account, args.namespace, args.token, f"meta:{slug}", args.proxy)
        if not meta:
            print(f"  ! {slug}: 读不到 meta，跳过")
            skipped += 1
            continue
        recs = []
        for fk in list_keys(args.account, args.namespace, args.token, f"file:{slug}:", args.proxy):
            rec = get_json_key(args.account, args.namespace, args.token, fk, args.proxy)
            if rec:
                recs.append(rec)
        size_hint = int(meta.get("size") or 0)
        print(f"  · {slug}: {len(recs)} 个文件，{size_hint/1048576:.1f} MB")
        if args.dry_run:
            ok += 1
            continue

        try:
            storage.remove_project_files(slug)
            storage.project_dir(slug).mkdir(parents=True, exist_ok=True)
            total = 0
            for rec in recs:
                rel = rec.get("path") or ""
                buf = bytearray()
                for i in range(int(rec.get("chunks") or 1)):
                    b64 = get_value(
                        args.account, args.namespace, args.token,
                        f"chunk:{slug}:{path_hash(rel)}:{i}", args.proxy,
                    )
                    if b64 is None:
                        raise RuntimeError(f"缺少分片 {i} / {rel}")
                    buf.extend(base64.b64decode(b64))
                if rel == "__zip__":
                    z = storage.zip_path(slug)
                    z.parent.mkdir(parents=True, exist_ok=True)
                    z.write_bytes(bytes(buf))
                    continue
                dest = storage.resolve_in_project(slug, rel)
                if dest is None:
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(bytes(buf))
                total += len(buf)

            views = 0
            for key in (f"views:{slug}", f"pv:d:{slug}"):
                try:
                    views += int(get_value(args.account, args.namespace, args.token, key, args.proxy) or 0)
                except (TypeError, ValueError):
                    pass

            entry_file = storage.project_dir(slug) / "index.html"
            kind = "link" if meta.get("link") else ("static" if recs else "zip")
            expire_at = int(meta.get("expireAt") or 0)
            t = now_ms()
            with tx() as conn:
                conn.execute("DELETE FROM projects WHERE slug=?", (slug,))
                conn.execute(
                    "INSERT INTO projects(slug, title, description, owner_id, kind, entry, file_count, "
                    "size_bytes, has_zip, zip_name, link_url, visibility, allow_download, expire_action, "
                    "expires_at, status, views, created_at, updated_at, legacy_source) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        slug,
                        meta.get("name") or slug,
                        meta.get("desc") or "",
                        owner["id"],
                        kind,
                        "index.html" if entry_file.is_file() else None,
                        int(meta.get("files") or len(recs)),
                        size_hint or total,
                        1 if meta.get("zipName") else 0,
                        meta.get("zipName"),
                        meta.get("link"),
                        "link",
                        1 if meta.get("allowDownload") else 0,
                        "delete" if meta.get("expireAction") == "delete" else "block",
                        None if expire_at == 0 else expire_at,
                        "active",
                        views,
                        int(meta.get("createdAt") or t),
                        int(meta.get("updatedAt") or t),
                        "cloudflare-kv",
                    ),
                )
            print(f"    ✓ 导入完成（{total} B，{views} 次访问）")
            ok += 1
        except Exception as exc:
            failed += 1
            print(f"    ✗ 失败: {exc}")

    print(f"\n完成：成功 {ok}，跳过 {skipped}，失败 {failed}")
    if not args.dry_run and ok:
        print("重启服务生效 → docker compose start")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
