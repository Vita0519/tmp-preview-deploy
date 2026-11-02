"""数据库行 → API 结构（带倒计时等派生字段）。"""
import time


def now_ms() -> int:
    return int(time.time() * 1000)


def _tags(conn, project_id: int) -> list[str]:
    rows = conn.execute(
        "SELECT t.name FROM project_tags pt JOIN tags t ON t.id=pt.tag_id "
        "WHERE pt.project_id=? ORDER BY t.name",
        (project_id,),
    ).fetchall()
    return [r["name"] for r in rows]


def project_dict(row, origin: str = "", tags: list[str] | None = None) -> dict:
    now = now_ms()
    expires_at = row["expires_at"]
    permanent = not expires_at
    expired = (not permanent and expires_at <= now) or row["status"] == "expired"
    remaining = None if permanent else max(0, expires_at - now)
    slug = row["slug"]
    keys = row.keys()
    owner = None
    if "owner_username" in keys and row["owner_username"]:
        owner = {
            "id": row["owner_id"],
            "username": row["owner_username"],
            "display_name": row["owner_display_name"] or row["owner_username"],
        }
    collection = None
    if "collection_name" in keys and row["collection_id"]:
        collection = {"id": row["collection_id"], "name": row["collection_name"] or "未命名"}
    return {
        "id": row["id"],
        "slug": slug,
        "title": row["title"],
        "description": row["description"],
        "owner": owner,
        "kind": row["kind"],
        "entry": row["entry"],
        "file_count": row["file_count"],
        "size_bytes": row["size_bytes"],
        "has_zip": bool(row["has_zip"]),
        "zip_name": row["zip_name"],
        "link_url": row["link_url"],
        "visibility": row["visibility"],
        "allow_download": bool(row["allow_download"]),
        "expire_action": row["expire_action"],
        "expires_at": expires_at,
        "permanent": permanent,
        "status": row["status"],
        "expired": expired,
        "remaining_ms": remaining,
        "views": row["views"],
        "downloads": row["downloads"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_viewed_at": row["last_viewed_at"],
        "tags": tags or [],
        "collection": collection,
        "urls": {
            "preview": f"{origin}/v/{slug}",
            "raw": f"{origin}/p/{slug}/",
            "download": f"{origin}/download/{slug}" if row["allow_download"] else None,
        },
    }


PROJECT_SELECT = """
SELECT p.*, u.username AS owner_username, u.display_name AS owner_display_name,
       c.name AS collection_name
FROM projects p
LEFT JOIN users u ON u.id = p.owner_id
LEFT JOIN collections c ON c.id = p.collection_id
"""
