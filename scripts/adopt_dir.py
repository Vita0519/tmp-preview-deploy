"""把手动拷进 data/projects 的目录登记成项目。

适用场景：安装包 / 站点包太大，浏览器传不上去，先 rsync/scp 到 NAS 的
`/data/projects/<slug>/`，再用这个脚本补一条数据库记录 —— 控制台和门户就能看到它。

    python scripts/adopt_dir.py                     # 只列没入库的目录（不动数据）
    python scripts/adopt_dir.py --all               # 全部导入
    python scripts/adopt_dir.py --slug my-site      # 只导入这一个
    python scripts/adopt_dir.py --all --visibility portal --owner vita0519

目录名就是 slug。入口规则跟网页上传一致：单文件直接用它；多文件要求根目录有
index.html，否则不算「站点」，会被跳过（那种情况应该走 zip 上传）。
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import FILES_DIR  # noqa: E402
from app.db import db, log_event  # noqa: E402
from app.storage import decide_entry  # noqa: E402

SKIP_PREFIX = (".tmp-", ".old-")


def measure(path: Path) -> tuple[int, int, list[str]]:
    """返回 (文件数, 总字节, 相对路径列表)。软链按文件统计，不跟进目录。"""
    count = 0
    total = 0
    rels: list[str] = []
    for f in path.rglob("*"):
        try:
            if not f.is_file():
                continue
            count += 1
            total += f.stat().st_size
            rels.append(f.relative_to(path).as_posix())
        except OSError:
            continue
    return count, total, rels


def fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def pick_owner(conn, username: str | None) -> int | None:
    if username:
        row = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if not row:
            sys.exit(f"找不到用户 {username}")
        return row["id"]
    row = conn.execute("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()
    return row["id"] if row else None


def main() -> int:
    ap = argparse.ArgumentParser(description="把 data/projects 下手动拷入的目录登记成项目")
    ap.add_argument("--slug", action="append", help="只处理指定目录（可重复）")
    ap.add_argument("--all", action="store_true", help="处理全部未入库目录")
    ap.add_argument("--owner", help="归属账号，默认第一个管理员")
    ap.add_argument("--visibility", default="link", choices=["link", "portal", "private"],
                    help="可见性，默认 link（持链接可看，不上门户）")
    ap.add_argument("--title", help="标题，默认用目录名")
    ap.add_argument("--dry-run", action="store_true", help="只列出，不写库")
    args = ap.parse_args()

    if not FILES_DIR.exists():
        sys.exit(f"项目目录不存在：{FILES_DIR}")

    with db() as conn:
        known = {r["slug"] for r in conn.execute("SELECT slug FROM projects")}
        owner_id = pick_owner(conn, args.owner)

        rows = []
        for p in sorted(FILES_DIR.iterdir()):
            if not p.is_dir() or p.name.startswith(SKIP_PREFIX):
                continue
            if p.name in known:
                continue
            if args.slug and p.name not in args.slug:
                continue
            count, total, rels = measure(p)
            if count == 0:
                rows.append((p.name, 0, 0, None, "空目录，跳过"))
                continue
            entry, err = decide_entry(rels)
            if not entry:
                rows.append((p.name, count, total, None, err or "没有可用入口"))
                continue
            rows.append((p.name, count, total, entry, "可导入"))

        if not rows:
            print("没有待导入的目录 —— data/projects 下的目录都已经在库里了")
            return 0

        print(f"{'目录':32} {'文件':>6} {'大小':>10}  状态")
        print("-" * 78)
        for name, count, total, entry, note in rows:
            print(f"{name:32} {count:>6} {fmt_bytes(total):>10}  {note}")

        ready = [r for r in rows if r[3]]
        if not ready:
            print("\n没有可导入的目录（上面标了原因）。")
            return 1
        if args.dry_run or not (args.all or args.slug):
            print(f"\n共 {len(ready)} 个可导入。确认无误后加 --all 或 --slug <目录名> 执行。")
            return 0

        now = int(time.time() * 1000)
        done = 0
        for name, count, total, entry, _ in ready:
            title = (args.title or name.replace("-", " ").replace("_", " ")).strip() or name
            cur = conn.execute(
                "INSERT INTO projects(slug, title, description, owner_id, kind, entry, "
                "file_count, size_bytes, has_zip, zip_name, visibility, allow_download, "
                "expire_action, expires_at, status, created_at, updated_at) "
                "VALUES(?,?,'',?,'static',?,?,?,0,NULL,?,0,'block',NULL,'active',?,?)",
                (name, title, owner_id, entry, count, total, args.visibility, now, now),
            )
            log_event("adopt", owner_id, cur.lastrowid,
                      f"手动拷贝目录入库：{count} 个文件 / {fmt_bytes(total)}",
                      slug=name, title=title)
            done += 1
            print(f"  ✓ {name} → {entry}（{count} 个文件，{fmt_bytes(total)}）")

        print(f"\n已导入 {done} 个。打开控制台就能看到，访问路径 /p/<目录名>/")
        return 0


if __name__ == "__main__":
    sys.exit(main())
