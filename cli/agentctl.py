#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""agentctl —— 成员（Agent）侧的上传/管理命令行，只用标准库。

  # 1) 登录一次，保存 API Key
  agentctl login --url http://127.0.0.1:8080 --username alice --password xxx

  # 2) 部署一个目录（默认 24 小时）
  agentctl deploy ./dist --title "落地页 v3" --tags "前端,v3" --ttl 24

  # 3) 日常操作
  agentctl ls                     # 只看自己的项目
  agentctl extend landing-v3 48   # 再续 48 小时
  agentctl extend landing-v3 --forever
  agentctl tags landing-v3 前端,v3,已验收
  agentctl rm landing-v3
"""
import argparse
import io
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", ".idea", ".vscode", "dist/.cache", ".next"}
SKIP_FILES = {".DS_Store", "Thumbs.db", ".gitignore"}
CONF_DIR = Path(os.environ.get("APPDATA") or Path.home() / ".config") / "tmp-preview"
CONF = CONF_DIR / "config.json"
LOCAL_HOSTS = ("127.0.0.1", "localhost", "0.0.0.0")


def load_conf() -> dict:
    try:
        return json.loads(CONF.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_conf(data: dict) -> None:
    CONF_DIR.mkdir(parents=True, exist_ok=True)
    CONF.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
    try:
        os.chmod(CONF, 0o600)
    except OSError:
        pass


def client(url: str):
    from urllib.parse import urlparse
    host = urlparse(url).hostname or ""
    handlers = []
    if host in LOCAL_HOSTS:
        handlers.append(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener(*handlers)


def call(url: str, path: str, token: str = "", method: str = "GET", body=None, raw=None, ctype=None):
    data = None
    headers = {"User-Agent": "agentctl/2.0"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if raw is not None:
        data = raw
        headers["Content-Type"] = ctype or "application/octet-stream"
    req = urllib.request.Request(url.rstrip("/") + path, data=data, method=method, headers=headers)
    try:
        with client(url).open(req, timeout=600) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        payload = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(payload or "{}")
        except json.JSONDecodeError:
            return e.code, {"detail": payload[:300]}


def slugify(name: str) -> str:
    import re
    raw = str(name or "").strip()
    s = re.sub(r"[^a-z0-9\-_]+", "-", raw.lower()).strip("-")
    if not s:
        h = 0
        for ch in raw:
            h = (h * 31 + ord(ch)) % 0xFFFFFF
        s = "p-" + format(h, "x")
    return s[:60]


def collect(root: Path):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            if fn in SKIP_FILES or fn.endswith((".pyc", ".log")):
                continue
            p = Path(dirpath) / fn
            out.append((p.relative_to(root).as_posix(), p))
    return out


def multipart(fields: dict, files: list[tuple[str, str, bytes]], zip_name: str | None = None):
    boundary = "----agentctl" + uuid.uuid4().hex
    buf = io.BytesIO()
    for k, v in fields.items():
        buf.write(f"--{boundary}\r\n".encode())
        buf.write(f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode())
        buf.write(str(v).encode("utf-8"))
        buf.write(b"\r\n")
    for field, name, data in files:
        buf.write(f"--{boundary}\r\n".encode())
        buf.write(f'Content-Disposition: form-data; name="{field}"; filename="{name}"\r\n'.encode("utf-8"))
        buf.write(b"Content-Type: application/octet-stream\r\n\r\n")
        buf.write(data)
        buf.write(b"\r\n")
    buf.write(f"--{boundary}--\r\n".encode())
    return buf.getvalue(), f"multipart/form-data; boundary={boundary}"


def human(n: int) -> str:
    n = int(n or 0)
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n/1024:.0f} KB"
    if n < 1024 ** 3:
        return f"{n/1024**2:.1f} MB"
    return f"{n/1024**3:.2f} GB"


def remaining(p: dict) -> str:
    if p.get("permanent"):
        return "永久"
    if p.get("expired"):
        return "已到期"
    ms = p.get("remaining_ms") or 0
    d, h, m = ms // 86400000, ms % 86400000 // 3600000, ms % 3600000 // 60000
    if d:
        return f"{d}天{h}小时"
    if h:
        return f"{h}小时{m}分"
    return f"{m}分"


def cmd_login(args):
    url = (args.url or "").rstrip("/")
    if not url:
        return print_err("请提供 --url，例如 http://127.0.0.1:8080")
    if args.api_key:
        conf = load_conf()
        conf.update({"url": url, "token": args.api_key, "username": args.username or ""})
        save_conf(conf)
        print(f"✅ 已保存 API Key（{CONF}）")
        return 0
    code, d = call(url, "/api/auth/token", method="POST", body={
        "username": args.username, "password": args.password})
    if code != 200:
        return print_err(f"登录失败：{d.get('detail') or d}")
    conf = load_conf()
    conf.update({"url": url, "token": d["token"], "username": d["username"]})
    save_conf(conf)
    print(f"✅ 已登录 {d['username']}（{d['role']}），凭据保存在 {CONF}")
    return 0


def _conn(args):
    conf = load_conf()
    url = (args.url or conf.get("url") or "").rstrip("/")
    token = args.token or conf.get("token") or ""
    if not url or not token:
        print_err("未登录：先执行 agentctl login --url <地址> --username <账号> --password <密码>")
        return None
    return url, token


def cmd_deploy(args):
    conn = _conn(args)
    if not conn:
        return 2
    url, token = conn
    root = Path(args.dir).expanduser().resolve()
    if not root.is_dir():
        return print_err(f"不是目录: {root}")
    items = collect(root)
    if not items:
        return print_err("目录为空")
    if not any(rel.lower() in ("index.html", "index.htm") for rel, _ in items) and not args.zip:
        print("⚠️  没有 index.html，预览会 404（用 --zip 可只做下载包）", file=sys.stderr)

    total = sum(p.stat().st_size for _, p in items)
    title = args.title or root.name
    fields = {
        "slug": args.slug or slugify(root.name),
        "title": title,
        "description": args.desc or "",
        "tags": args.tags or "",
        "expire_action": args.expire_action,
        "visibility": args.visibility,
        "allow_download": "1" if args.download else "0",
    }
    if args.forever:
        fields["forever"] = "1"
    elif args.ttl is not None:
        fields["hours"] = args.ttl

    files = [("files", rel, p.read_bytes()) for rel, p in items]
    if args.zip:
        zbuf = io.BytesIO()
        with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
            for rel, p in items:
                z.write(p, rel)
        files.append(("zip", f"{args.slug or root.name}.zip", zbuf.getvalue()))
        print(f"  已打包 zip：{human(len(zbuf.getvalue()))}")

    print(f"→ {title}：{len(items)} 个文件 / {human(total)} → {url}")
    body, ctype = multipart(fields, files)
    code, d = call(url, "/api/projects", token, "POST", raw=body, ctype=ctype)
    if code != 200:
        return print_err(f"上传失败（{code}）：{d.get('detail') or d}")
    print("✅ 部署完成")
    print(f"   预览：{d['urls']['preview']}")
    print(f"   原始：{d['urls']['raw']}")
    if d.get("urls", {}).get("download"):
        print(f"   下载：{d['urls']['download']}")
    print(f"   时长：{'永久' if d.get('permanent') else f'剩余 {remaining(d)}'}")
    return 0


def cmd_ls(args):
    conn = _conn(args)
    if not conn:
        return 2
    url, token = conn
    code, d = call(url, f"/api/projects?status={args.status}&limit=200&sort=updated_at", token)
    if code != 200:
        return print_err(f"读取失败：{d.get('detail') or d}")
    if not d["items"]:
        print("（没有项目）")
        return 0
    print(f"{'SLUG':<26}{'访问':>6}  {'体积':>9}  {'剩余':<12}{'标题'}")
    print("-" * 78)
    for p in d["items"]:
        print(f"{p['slug']:<26}{p['views']:>6}  {human(p['size_bytes']):>9}  {remaining(p):<12}{p['title']}")
    print(f"\n共 {d['total']} 个")
    return 0


def cmd_rm(args):
    conn = _conn(args)
    if not conn:
        return 2
    url, token = conn
    code, d = call(url, f"/api/projects/{args.slug}", token, "DELETE")
    if code != 200:
        return print_err(f"删除失败：{d.get('detail') or d}")
    print(f"✅ 已删除 {args.slug}")
    return 0


def cmd_extend(args):
    conn = _conn(args)
    if not conn:
        return 2
    url, token = conn
    body = {"permanent": True} if args.forever else {"hours": args.hours, "revive": True}
    code, d = call(url, f"/api/projects/{args.slug}", token, "PATCH", body=body)
    if code != 200:
        return print_err(f"操作失败：{d.get('detail') or d}")
    print(f"✅ {args.slug} → {'永久' if d.get('permanent') else '剩余 ' + remaining(d)}")
    return 0


def cmd_tags(args):
    conn = _conn(args)
    if not conn:
        return 2
    url, token = conn
    tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]
    code, d = call(url, f"/api/projects/{args.slug}", token, "PATCH", body={"tags": tags})
    if code != 200:
        return print_err(f"失败：{d.get('detail') or d}")
    print(f"✅ 标签已更新：{', '.join(d.get('tags') or []) or '（空）'}")
    return 0


def cmd_open(args):
    conn = _conn(args)
    if not conn:
        return 2
    url, token = conn
    code, d = call(url, f"/api/projects/{args.slug}", token)
    if code != 200:
        return print_err(f"找不到项目：{d.get('detail') or d}")
    print(d["urls"]["preview"])
    return 0


def print_err(msg: str) -> int:
    print(msg, file=sys.stderr)
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(prog="agentctl", description="临时预览站的成员侧命令行")
    ap.add_argument("--url", help="站点地址，默认用上次登录保存的")
    ap.add_argument("--token", help="API Key，默认用上次登录保存的")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("login", help="登录并保存凭据")
    p.add_argument("--url")
    p.add_argument("--username")
    p.add_argument("--password")
    p.add_argument("--api-key", help="已有 Key 时直接保存，跳过账号密码")
    p.set_defaults(func=cmd_login)

    p = sub.add_parser("deploy", help="上传目录 / 打包部署")
    p.add_argument("dir", nargs="?", default=".")
    p.add_argument("--slug")
    p.add_argument("--title")
    p.add_argument("--desc", default="")
    p.add_argument("--tags", default="")
    p.add_argument("--ttl", type=float, help="存活小时数，默认服务端配置")
    p.add_argument("--forever", action="store_true")
    p.add_argument("--download", action="store_true", help="开放 zip 下载")
    p.add_argument("--zip", action="store_true", help="额外打包整站 zip")
    p.add_argument("--visibility", default="link", choices=["link", "portal", "private"])
    p.add_argument("--expire-action", default="block", choices=["block", "delete"])
    p.set_defaults(func=cmd_deploy)

    p = sub.add_parser("ls", help="列出项目")
    p.add_argument("--status", default="all", choices=["all", "online", "expired", "permanent"])
    p.set_defaults(func=cmd_ls)

    p = sub.add_parser("rm", help="删除项目")
    p.add_argument("slug")
    p.set_defaults(func=cmd_rm)

    p = sub.add_parser("extend", help="延长存活时间")
    p.add_argument("slug")
    p.add_argument("hours", nargs="?", type=float, default=24)
    p.add_argument("--forever", action="store_true")
    p.set_defaults(func=cmd_extend)

    p = sub.add_parser("tags", help="覆盖设置标签")
    p.add_argument("slug")
    p.add_argument("tags")
    p.set_defaults(func=cmd_tags)

    p = sub.add_parser("open", help="打印预览地址")
    p.add_argument("slug")
    p.set_defaults(func=cmd_open)

    args = ap.parse_args()
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
