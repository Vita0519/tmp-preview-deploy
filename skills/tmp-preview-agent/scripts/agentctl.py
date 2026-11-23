#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""agentctl —— 临时预览站的 Agent 侧命令行（单文件，仅标准库）。

写给「AI agent 直接调用」用，不是给人看的说明书：

  * `--json`：stdout 只输出一行 JSON（进度/提示一律走 stderr），方便管道解析
  * 写操作会回头校验：deploy 之后主动 GET 预览地址、set 之后重新读取
  * deploy 自动打印并返回预览地址，不需要自己拼
  * 网络抖动 / 5xx 自动重试 3 次；并发部署同一个站点不会互相踩

常用：
  agentctl login --url http://127.0.0.1:8000 --username alice --password xxx
  agentctl deploy ./dist --tags 前端 --ttl 24 --json
  agentctl selfcheck          # 用当前身份跑一遍增删改查，确认权限没问题
"""

# ---------------------------------------------------------------------------
# tmp-preview（临时预览站）
# Copyright (C) 2026 Vita0519<https://github.com/Vita0519/tmp-preview-deploy>
#
# 本程序以 GNU AGPL-3.0 发布（AGPL-3.0-only），全文见仓库根目录 LICENSE，
# 著作权与附加署名要求见 NOTICE。分发修改版或对外提供服务时，请保留本声明。
# ---------------------------------------------------------------------------

import argparse
import io
import json
import os
import random
import re
import shutil
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path

# ---------------- 项目名宽度规则（与后端 namerule.py 同一把尺子） ----------------
# 显示宽度：全角（中文等）算 1，半角算 0.5；上限 10 = 10 个中文字 ≈ 20 个英文字符。
# 上传 / 建外链超长会被截短（服务端与这里同规则），改名（set --title）超长直接 422。
TITLE_MAX_WIDTH = 10.0


def _char_w(ch: str) -> float:
    return 1.0 if unicodedata.east_asian_width(ch) in ("W", "F") else 0.5


def title_width(text: str) -> float:
    return sum(_char_w(c) for c in str(text or ""))


def title_too_long(text: str) -> bool:
    return title_width(text) > TITLE_MAX_WIDTH + 1e-9


def clamp_title(text: str) -> str:
    """截到上限内（不把一个字符劈成两半），去掉尾部空格与标点——与后端 namerule.clamp 一致。"""
    s = str(text or "").strip()
    if not title_too_long(s):
        return s
    out, used = [], 0.0
    for ch in s:
        w = _char_w(ch)
        if used + w > TITLE_MAX_WIDTH + 1e-9:
            break
        out.append(ch)
        used += w
    return "".join(out).rstrip(" 　-—_·,，.。:：;；|/\\")


VERSION = "3.0"
SKIP_DIRS = {
    ".git", "node_modules", ".venv", "__pycache__", ".idea", ".vscode",
    ".next", ".nuxt", ".cache", ".turbo", "coverage",
}
SKIP_FILES = {".DS_Store", "Thumbs.db", ".gitignore"}
CONF_DIR = Path(os.environ.get("APPDATA") or Path.home() / ".config") / "tmp-preview"
CONF = CONF_DIR / "config.json"
LOCAL_HOSTS = ("127.0.0.1", "localhost", "0.0.0.0", "::1")
VISIBILITY = ("portal", "link", "private")
ROLE_DOES = {
    "viewer": "只能浏览门户，不能碰项目接口",
    "publisher": "能增删改自己名下的项目",
    "admin": "能管理全部项目、成员与设置",
}


# --------------------------------------------------------------------------- #
# 基础设施
# --------------------------------------------------------------------------- #
def log(msg=""):
    """人读提示走 stderr，保持 stdout 干净。"""
    print(msg, file=sys.stderr)


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


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """不跟随 3xx：用来判断链接是否还停在原地。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _opener(url: str, redirect: bool = True):
    from urllib.parse import urlparse

    handlers = []
    if (urlparse(url).hostname or "") in LOCAL_HOSTS:
        handlers.append(urllib.request.ProxyHandler({}))
    if not redirect:
        handlers.append(_NoRedirect())
    return urllib.request.build_opener(*handlers)


def call(url, path, token="", method="GET", body=None, raw=None, ctype=None,
         timeout=600, retry=3):
    """返回 (status, dict)。网络错误与 5xx 自动重试。"""
    data = None
    headers = {"User-Agent": f"agentctl/{VERSION}"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if raw is not None:
        data = raw
        headers["Content-Type"] = ctype or "application/octet-stream"

    target = url.rstrip("/") + path
    last = None
    for attempt in range(retry):
        req = urllib.request.Request(target, data=data, method=method, headers=headers)
        try:
            with _opener(url).open(req, timeout=timeout) as r:
                payload = r.read()
                try:
                    return r.status, json.loads(payload or b"{}")
                except json.JSONDecodeError:
                    return r.status, {"raw": payload[:400].decode("utf-8", "replace")}
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", "replace")
            try:
                parsed = json.loads(text or "{}")
            except json.JSONDecodeError:
                parsed = {"detail": text[:300]}
            if e.code >= 500 and attempt < retry - 1:
                last = (e.code, parsed)
                time.sleep(0.4 * (attempt + 1) + random.random() * 0.2)
                continue
            return e.code, parsed
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = (0, {"detail": f"网络错误：{e}"})
            if attempt < retry - 1:
                time.sleep(0.5 * (attempt + 1))
                continue
            return last
    return last or (0, {"detail": "请求失败"})


def emit(args, ok, cmd, data=None, error="", human=None):
    """统一出口：--json 时 stdout 只有一行 JSON。"""
    if getattr(args, "json", False):
        payload = {"ok": bool(ok), "cmd": cmd}
        if data is not None:
            payload["data"] = data
        if error:
            payload["error"] = error
        print(json.dumps(payload, ensure_ascii=False, default=str))
    elif human:
        for line in human:
            print(line)
    elif error:
        # 人读模式也得把错误说出来，不然只有退出码 1、屏幕上什么都没有
        print(f"❌ {error}", file=sys.stderr)
    return 0 if ok else 1


def err_text(code, payload) -> str:
    """错误文案统一带上 HTTP 状态，agent 才能根据码分支处理。"""
    detail = ""
    if isinstance(payload, dict):
        detail = payload.get("detail") or payload.get("error") or ""
        if not detail:
            detail = json.dumps(payload, ensure_ascii=False)[:200]
    else:
        detail = str(payload)[:200]
    return f"HTTP {code}：{detail}"


def conn(args):
    conf = load_conf()
    url = (getattr(args, "url", None) or conf.get("url") or "").rstrip("/")
    token = getattr(args, "token", None) or conf.get("token") or ""
    if not url or not token:
        log("未登录：agentctl login --url <站点地址> --username <账号> --password <密码>")
        log("或：agentctl login --url <站点地址> --api-key pv_xxx")
        return None
    return url, token


# --------------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------------- #
def slugify(name: str) -> str:
    raw = str(name or "").strip()
    s = re.sub(r"[^a-z0-9\-_]+", "-", raw.lower()).strip("-")
    if not s:
        h = 0
        for ch in raw:
            h = (h * 31 + ord(ch)) % 0xFFFFFF
        s = "p-" + format(h, "x")
    return s[:60]


def collect(root: Path, keep_hidden=False):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        if not keep_hidden:
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            if fn in SKIP_FILES or fn.endswith((".pyc", ".log")):
                continue
            p = Path(dirpath) / fn
            out.append((p.relative_to(root).as_posix(), p))
    return out


def multipart(fields: dict, files: list):
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


def human_size(n) -> str:
    n = int(n or 0)
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.0f} KB"
    if n < 1024 ** 3:
        return f"{n / 1024 ** 2:.1f} MB"
    return f"{n / 1024 ** 3:.2f} GB"


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


def probe(url: str, redirect: bool = True) -> int:
    """匿名探活，返回 HTTP 状态；0 表示连不上。"""
    try:
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": f"agentctl/{VERSION}"})
        with _opener(url, redirect).open(req, timeout=20) as r:
            r.read(2048)
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:  # noqa: BLE001 - 探活失败不该中断主流程
        return 0


def is_gone(url: str) -> bool:
    """链接是否已经打不开了。

    失效不再表现为 404：站点会把失效链接 302 回门户首页（可能是转去登录页，
    也可能是「链接已失效」的门户），所以只有「原地仍然 200」才算还活着。
    """
    return probe(url, redirect=False) != 200


def find_agent(items, key):
    """按 id 或 username 找成员。"""
    ks = str(key)
    for a in items:
        if str(a["id"]) == ks or a["username"] == ks:
            return a
    return None


# --------------------------------------------------------------------------- #
# 命令：身份 / 健康
# --------------------------------------------------------------------------- #
def cmd_login(args):
    url = (args.url or "").rstrip("/")
    if not url:
        log("请提供 --url，例如 http://127.0.0.1:8000")
        return 1
    if args.api_key:
        conf = load_conf()
        conf.update({"url": url, "token": args.api_key, "username": args.username or ""})
        save_conf(conf)
        return emit(args, True, "login", {"url": url, "saved": str(CONF), "mode": "api_key"},
                    human=[f"✅ 已保存 API Key（{CONF}）"])
    code, d = call(url, "/api/auth/token", method="POST",
                   body={"username": args.username, "password": args.password})
    if code != 200:
        return emit(args, False, "login", error=err_text(code, d))
    conf = load_conf()
    conf.update({"url": url, "token": d["token"], "username": d["username"]})
    save_conf(conf)
    return emit(args, True, "login",
                {"url": url, "username": d["username"], "role": d.get("role"), "saved": str(CONF)},
                human=[f"✅ 已登录 {d['username']}（{d.get('role')}），凭据保存在 {CONF}"])


def cmd_whoami(args):
    c = conn(args)
    if not c:
        return 2
    url, token = c
    code, d = call(url, "/api/auth/me", token)
    if code != 200:
        return emit(args, False, "whoami", error=err_text(code, d))
    user = d["user"]
    role = user["role"]
    key = d.get("api_key") or ""
    payload = {
        "url": url,
        "username": user["username"],
        "display_name": user["display_name"],
        "role": role,
        "can_publish": role != "viewer",
        "can_admin": role == "admin",
        "key_tail": key[-6:] if key else "",
        "hint": ROLE_DOES.get(role, ""),
    }
    return emit(args, True, "whoami", payload, human=[
        f"站点：{url}",
        f"身份：{user['username']}（{user['display_name']}）· 角色 {role}",
        f"能力：{ROLE_DOES.get(role, '')}",
        f"Key ：…{payload['key_tail']}",
    ])


def cmd_health(args):
    c = conn(args)
    if not c:
        return 2
    url, token = c
    code, meta = call(url, "/api/meta")
    if code != 200:
        return emit(args, False, "health", error=err_text(code, meta))
    code2, me = call(url, "/api/auth/me", token)
    payload = {
        "url": url,
        "version": meta.get("version"),
        "site_title": meta.get("site_title"),
        "online": meta.get("online"),
        "public_portal": meta.get("public_portal"),
        "ttl_defaults": meta.get("ttl_defaults"),
        "auth": "ok" if code2 == 200 else f"fail:{code2}",
        "role": (me.get("user") or {}).get("role") if code2 == 200 else None,
    }
    return emit(args, code2 == 200, "health", payload, human=[
        f"站点：{url}  v{meta.get('version')}  在线 {meta.get('online')} 个项目",
        f"默认寿命：{meta.get('ttl_defaults')}",
        f"我的 Key：{'有效' if code2 == 200 else '无效（' + str(code2) + '）'}"
        + (f" · 角色 {payload['role']}" if code2 == 200 else ""),
    ])


# --------------------------------------------------------------------------- #
# 命令：部署 / 外链
# --------------------------------------------------------------------------- #
def resolve_collection(url, token, value):
    """把 `--collection` 的值换成分组 id。

    能吃三种：数字 id、`none`（移出分组）、分组名字（子分组写成 `办公/报表`）。
    名字找不到就返回 None（= 未归类），让命令继续跑，不因为归类失败中断部署。
    """
    v = str(value or "").strip()
    if v.lower() in ("", "none", "0", "unassigned", "-"):
        return None
    if v.isdigit():
        return int(v)
    code, tree = call(url, "/api/collections", token)
    if code != 200:
        return None
    want = v.replace(" ", "")
    for node in tree.get("items") or []:
        if node["name"].replace(" ", "") == want:
            return int(node["id"])
        for kid in node.get("children") or []:
            pair = f"{node['name']}/{kid['name']}".replace(" ", "")
            if pair == want or kid["name"].replace(" ", "") == want:
                return int(kid["id"])
    return None


def cmd_deploy(args):
    c = conn(args)
    if not c:
        return 2
    url, token = c
    root = Path(args.dir).expanduser().resolve()
    if not root.is_dir():
        return emit(args, False, "deploy", error=f"不是目录：{root}")
    items = collect(root)
    if not items:
        return emit(args, False, "deploy", error="目录为空（或全被忽略规则跳过）")

    has_index = any(rel.lower() in ("index.html", "index.htm") for rel, _ in items)
    if not has_index and not args.zip:
        log("⚠️  目录里没有 index.html，预览会 404；用 --zip 可只做下载包")

    total = sum(p.stat().st_size for _, p in items)
    title = args.title or root.name
    if title_too_long(title):
        if args.title:
            log(f"⚠️  --title 超过 10 个中文字符（约 20 个半角），已截成「{clamp_title(title)}」；下次直接起个短名")
        else:
            log(f"⚠️  未传 --title，退回目录名超过 10 个中文字符（约 20 个半角），"
                f"已截成「{clamp_title(root.name)}」；部署前主动传个短名，别让机器替你截")
        title = clamp_title(title)
    slug = args.slug or slugify(root.name)
    fields = {
        "slug": slug,
        "title": title,
        "description": args.desc or "",
        "tags": args.tags or "",
        "expire_action": args.expire_action,
        "visibility": args.visibility,
        "allow_download": "1" if args.download else "0",
    }
    if getattr(args, "collection", None):
        cid = resolve_collection(url, token, args.collection)
        fields["collection"] = "" if cid is None else str(cid)
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
        files.append(("zip", f"{slug}.zip", zbuf.getvalue()))
        log(f"  已打包 zip：{human_size(len(zbuf.getvalue()))}")

    log(f"→ {title}：{len(items)} 个文件 / {human_size(total)} → {url}")
    body, ctype = multipart(fields, files)
    code, d = call(url, "/api/projects", token, "POST", raw=body, ctype=ctype)
    if code != 200:
        hint = {401: "Key 无效或已轮换", 403: "当前角色不能发布（viewer）",
                409: "slug 已被其他成员占用", 413: "超过单项目体积上限"}.get(code, "")
        return emit(args, False, "deploy", error=f"上传失败 HTTP {code}：{d.get('detail') or ''} {hint}".strip())

    urls = d.get("urls") or {}
    saved_title = d.get("title") or title
    if saved_title != title:
        log(f"⚠️  项目名超过 10 个中文字符（约 20 个半角），已截成「{saved_title}」")
    status = 0 if args.no_verify else probe(urls.get("preview", ""))
    payload = {
        "slug": d.get("slug"),
        "title": d.get("title"),
        "url": urls.get("preview"),
        "urls": urls,
        "visibility": d.get("visibility"),
        "expires_at": d.get("expires_at"),
        "permanent": d.get("permanent"),
        "remaining": remaining(d),
        "files": d.get("file_count"),
        "bytes": d.get("size_bytes"),
        "http_status": status,
        "verified": status == 200,
    }
    lines = [
        f"✅ 部署完成：{d.get('slug')}",
        f"   预览：{payload['url']}",
        f"   原始：{urls.get('raw')}",
    ]
    if urls.get("download"):
        lines.append(f"   下载：{urls['download']}")
    lines.append(f"   可见性：{d.get('visibility')} · 时长：{payload['remaining']}")
    if status:
        lines.append(f"   校验：预览地址返回 HTTP {status}" + ("（正常）" if status == 200 else "（异常，检查是否到期或入口文件缺失）"))
    return emit(args, True, "deploy", payload, human=lines)


def cmd_link(args):
    c = conn(args)
    if not c:
        return 2
    url, token = c
    link_title = args.title or args.url_to
    if title_too_long(link_title):
        if args.title:
            log(f"⚠️  --title 超过 10 个中文字符（约 20 个半角），已截成「{clamp_title(link_title)}」")
        else:
            log(f"⚠️  未传 --title，退回用 URL 当名字太长，已截成「{clamp_title(link_title)}」；建议传个 ≤10 字的短名")
        link_title = clamp_title(link_title)
    body = {
        "link_url": args.url_to,
        "title": link_title,
        "visibility": args.visibility,
        "description": args.desc or "",
        "tags": args.tags or "",
    }
    if args.slug:
        body["slug"] = args.slug
    if getattr(args, "collection", None):
        body["collection_id"] = resolve_collection(url, token, args.collection)
    if args.forever:
        body["forever"] = True
    elif args.ttl is not None:
        body["hours"] = args.ttl
    code, d = call(url, "/api/projects/link", token, "POST", body=body)
    if code != 200:
        return emit(args, False, "link", error=f"创建失败 HTTP {code}：{d.get('detail') or ''}")
    urls = d.get("urls") or {}
    payload = {"slug": d.get("slug"), "url": urls.get("preview"), "target": args.url_to,
               "visibility": d.get("visibility"), "remaining": remaining(d)}
    return emit(args, True, "link", payload, human=[
        f"✅ 外链已登记：{d.get('slug')}",
        f"   预览：{payload['url']}（302 → {args.url_to}）",
        f"   可见性：{d.get('visibility')} · 时长：{payload['remaining']}",
    ])


# --------------------------------------------------------------------------- #
# 命令：查询 / 修改 / 删除
# --------------------------------------------------------------------------- #
def cmd_ls(args):
    c = conn(args)
    if not c:
        return 2
    url, token = c
    qs = [f"status={args.status}", f"limit={args.limit}", f"sort={args.sort}", f"order={args.order}"]
    if args.visibility:
        qs.append(f"visibility={args.visibility}")
    if args.kind:
        qs.append(f"kind={args.kind}")
    if args.q:
        qs.append("q=" + urllib.request.quote(args.q))
    if getattr(args, "collection", None):
        raw = str(args.collection).strip()
        if raw.lower() in ("none", "0", "unassigned"):
            qs.append("collection=none")
        else:
            cid = resolve_collection(url, token, raw)
            if cid is None:
                return emit(args, False, "ls", error=f"找不到分组：{raw}")
            qs.append(f"collection={cid}")
    for t in args.tag or []:
        qs.append("tag=" + urllib.request.quote(t))
    code, d = call(url, "/api/projects?" + "&".join(qs), token)
    if code != 200:
        return emit(args, False, "ls", error=f"读取失败 HTTP {code}：{d.get('detail') or ''}")
    items = d.get("items") or []
    payload = {"total": d.get("total"), "items": items,
               "slugs": [p["slug"] for p in items]}
    if not items:
        return emit(args, True, "ls", payload, human=["（没有匹配的项目）"])
    lines = [f"{'SLUG':<28}{'可见性':<9}{'访问':>6}  {'体积':>9}  {'剩余':<11}标题", "-" * 88]
    for p in items:
        lines.append(
            f"{p['slug']:<28}{p.get('visibility', ''):<9}{p.get('views', 0):>6}  "
            f"{human_size(p.get('size_bytes')):>9}  {remaining(p):<11}{p.get('title', '')}"
        )
    lines.append(f"\n共 {d.get('total')} 个（本次列出 {len(items)}）")
    return emit(args, True, "ls", payload, human=lines)


def cmd_show(args):
    c = conn(args)
    if not c:
        return 2
    url, token = c
    code, d = call(url, f"/api/projects/{args.slug}", token)
    if code != 200:
        return emit(args, False, "show", error=f"读取失败 HTTP {code}：{d.get('detail') or ''}")
    files = d.get("files") or []
    payload = {
        "slug": d.get("slug"),
        "title": d.get("title"),
        "url": (d.get("urls") or {}).get("preview"),
        "urls": d.get("urls"),
        "visibility": d.get("visibility"),
        "status": d.get("status"),
        "expired": d.get("expired"),
        "remaining": remaining(d),
        "tags": d.get("tags"),
        "files": len(files),
        "file_list": [f.get("path") or f.get("name") for f in files][:50],
        "views": d.get("views"),
        "downloads": d.get("downloads"),
    }
    return emit(args, True, "show", payload, human=[
        f"项目：{d.get('title')}（{d.get('slug')}）",
        f"地址：{payload['url']}",
        f"可见性：{d.get('visibility')} · 状态：{d.get('status')} · 剩余 {payload['remaining']}",
        f"标签：{', '.join(d.get('tags') or []) or '（空）'}",
        f"访问：{d.get('views')} 次 · 下载：{d.get('downloads')} 次 · 文件 {len(files)} 个",
    ])


def cmd_set(args):
    c = conn(args)
    if not c:
        return 2
    url, token = c
    body = {}
    if args.visibility:
        body["visibility"] = args.visibility
    if args.forever:
        body["permanent"] = True
    elif args.ttl is not None:
        body["hours"] = args.ttl
        body["revive"] = True
    if args.title:
        # 改名不会被自动截短（后端 422），先在本地把话说明白
        if title_too_long(args.title):
            return emit(args, False, "set",
                        error=f"项目名超过 10 个中文字符（约 20 个半角，当前 {args.title}），改名不会自动截短；缩短后再试")
        body["title"] = args.title
    if args.desc is not None:
        body["description"] = args.desc
    if args.tags is not None:
        body["tags"] = [t.strip() for t in args.tags.split(",") if t.strip()]
    if args.download:
        body["allow_download"] = True
    if args.no_download:
        body["allow_download"] = False
    if getattr(args, "collection", None):
        body["collection_id"] = resolve_collection(url, token, args.collection)
    if getattr(args, "no_collection", False):
        body["collection_id"] = None
    if not body:
        return emit(args, False, "set", error="没有要改的字段")
    code, d = call(url, f"/api/projects/{args.slug}", token, "PATCH", body=body)
    if code != 200:
        return emit(args, False, "set", error=f"修改失败 HTTP {code}：{d.get('detail') or ''}")
    payload = {"slug": d.get("slug"), "title": d.get("title"), "visibility": d.get("visibility"),
               "remaining": remaining(d), "tags": d.get("tags"),
               "allow_download": d.get("allow_download"), "url": (d.get("urls") or {}).get("preview")}
    return emit(args, True, "set", payload, human=[
        f"✅ 已更新 {d.get('slug')}",
        f"   可见性：{d.get('visibility')} · 剩余：{payload['remaining']}",
        f"   标签：{', '.join(d.get('tags') or []) or '（空）'}",
    ])


def cmd_extend(args):
    c = conn(args)
    if not c:
        return 2
    url, token = c
    body = {"permanent": True} if args.forever else {"hours": args.hours, "revive": True}
    code, d = call(url, f"/api/projects/{args.slug}", token, "PATCH", body=body)
    if code != 200:
        return emit(args, False, "extend", error=f"操作失败 HTTP {code}：{d.get('detail') or ''}")
    payload = {"slug": d.get("slug"), "permanent": d.get("permanent"),
               "expires_at": d.get("expires_at"), "remaining": remaining(d)}
    return emit(args, True, "extend", payload, human=[
        f"✅ {d.get('slug')} → {'永久' if d.get('permanent') else '剩余 ' + payload['remaining']}"])


def cmd_rm(args):
    c = conn(args)
    if not c:
        return 2
    url, token = c
    if not args.yes and not getattr(args, "json", False):
        return emit(args, False, "rm", error="删除不可恢复，确认请加 --yes")
    code, d = call(url, f"/api/projects/{args.slug}", token, "DELETE")
    if code != 200:
        return emit(args, False, "rm", error=f"删除失败 HTTP {code}：{d.get('detail') or ''}")
    gone = probe(f"{url}/v/{args.slug}", redirect=False)
    ok = gone != 200
    return emit(args, ok, "rm", {"slug": args.slug, "deleted": True, "after_status": gone,
                                 "gone": ok},
                error="" if ok else "删除接口返回成功，但地址仍能打开，请检查存储残留",
                human=[f"✅ 已删除 {args.slug}（访问校验：HTTP {gone}"
                       f"{'，链接已失效' if ok else '，⚠️ 仍可访问'}）"])


def cmd_bulk(args):
    c = conn(args)
    if not c:
        return 2
    url, token = c
    slugs = [s.strip() for s in (args.slugs or "").split(",") if s.strip()]
    if not slugs:
        return emit(args, False, "bulk", error="--slugs 为空")
    body = {"slugs": slugs, "action": args.action}
    if args.hours is not None:
        body["hours"] = args.hours
    if args.visibility:
        body["visibility"] = args.visibility
    if args.tags:
        body["tags"] = args.tags
    if args.action == "delete" and not args.yes and not getattr(args, "json", False):
        return emit(args, False, "bulk", error=f"将删除 {len(slugs)} 个项目，确认请加 --yes")
    code, d = call(url, "/api/projects/bulk", token, "POST", body=body)
    if code != 200:
        return emit(args, False, "bulk", error=f"批量操作失败 HTTP {code}：{d.get('detail') or ''}")
    payload = {"action": args.action, "requested": len(slugs), "done": d.get("done"),
               "skipped": d.get("skipped"), "expired": d.get("expired", 0)}
    return emit(args, True, "bulk", payload, human=[
        f"✅ {args.action}：处理 {d.get('done')} 个，跳过 {d.get('skipped')} 个"
        + (f"，其中 {d.get('expired')} 个已到期" if d.get("expired") else "")])


def cmd_stats(args):
    c = conn(args)
    if not c:
        return 2
    url, token = c
    code, d = call(url, f"/api/stats/trend?days={args.days}", token)
    if code != 200:
        return emit(args, False, "stats", error=f"读取失败 HTTP {code}：")
    items = d.get("items") or []
    payload = {"days": args.days, "items": items,
               "total": sum(i.get("count", 0) for i in items)}
    return emit(args, True, "stats", payload, human=[
        f"近 {args.days} 天访问合计 {payload['total']} 次",
        *[f"  {i['day']}  {i['count']}" for i in items[-7:]],
    ])


# --------------------------------------------------------------------------- #
# 命令：分组
# --------------------------------------------------------------------------- #
def cmd_collections(args):
    c = conn(args)
    if not c:
        return 2
    url, token = c
    act = getattr(args, "action", "ls")

    if act == "ls":
        code, d = call(url, "/api/collections", token)
        if code != 200:
            return emit(args, False, "collections.ls", error=f"读取失败 HTTP {code}：{d.get('detail') or ''}")
        lines = [f"{'ID':>5}  {'项目':>4}  {'合计':>4}  名称", "-" * 56]
        for node in d.get("items") or []:
            lines.append(f"{node['id']:>5}  {node['count']:>4}  {node['total']:>4}  {node['name']}")
            for kid in node.get("children") or []:
                lines.append(f"{kid['id']:>5}  {kid['count']:>4}  {kid['total']:>4}    └ {kid['name']}")
        lines.append(f"{'':>5}  {d.get('unassigned', 0):>4}  {'':>4}  （未归类）")
        vis = d.get("visibility") or {}
        if vis:
            # 跟控制台侧栏那三个常驻分类同源：三档之和 = 上面的合计
            lines.append("")
            lines.append(
                f"可见性：门户 {vis.get('portal', 0)} · 持链接 {vis.get('link', 0)}"
                f" · 仅自己 {vis.get('private', 0)}"
                f"（合计 {d.get('total', 0)}）"
            )
        return emit(args, True, "collections.ls", d, human=lines)

    if act == "add":
        if not args.name:
            return emit(args, False, "collections.add", error="要给个名字：collections add 办公")
        body = {"name": args.name}
        if args.parent:
            body["parent_id"] = resolve_collection(url, token, args.parent)
            if body["parent_id"] is None:
                return emit(args, False, "collections.add", error=f"找不到上级分组：{args.parent}")
        code, d = call(url, "/api/collections", token, "POST", body=body)
        if code != 200:
            return emit(args, False, "collections.add", error=f"新建失败 HTTP {code}：{d.get('detail') or ''}")
        col = d.get("collection") or {}
        return emit(args, True, "collections.add", col, human=[f"✅ 分组 {col.get('id')}：{col.get('name')}"])

    if act in ("rm", "delete"):
        cid = resolve_collection(url, token, args.target)
        if cid is None:
            return emit(args, False, "collections.rm", error=f"找不到分组：{args.target}")
        qs = "?with_projects=1" if args.with_projects else ""
        code, d = call(url, f"/api/collections/{cid}{qs}", token, "DELETE")
        if code != 200:
            return emit(args, False, "collections.rm", error=f"删除失败 HTTP {code}：{d.get('detail') or ''}")
        return emit(args, True, "collections.rm", d, human=[
            f"✅ 已删除分组「{d.get('name')}」："
            + (f"连 {d.get('deleted_projects')} 个项目一起删" if args.with_projects
               else f"{d.get('moved_to_unassigned')} 个项目退回未归类")
        ])

    return emit(args, False, "collections", error=f"不认识的动作：{act}")


# --------------------------------------------------------------------------- #
# 命令：成员（管理员）
# --------------------------------------------------------------------------- #
def cmd_members(args):
    c = conn(args)
    if not c:
        return 2
    url, token = c
    act = args.action

    if act == "list":
        code, d = call(url, "/api/agents", token)
        if code != 200:
            return emit(args, False, "members.list", error=f"读取失败 HTTP {code}：{d.get('detail') or ''}")
        items = d.get("items") or []
        return emit(args, True, "members.list", {"items": items, "total": len(items)}, human=[
            f"{'ID':<4}{'账号':<14}{'角色':<10}{'绑定 Agent':<14}{'项目':>4}{'最近用 Key'}",
            "-" * 72,
            *[f"{a['id']:<4}{a['username']:<14}{a['role']:<10}{(a.get('key_label') or ''):<14}"
              f"{a.get('projects', 0):>4}  {(a.get('key_last_used_at') and '有') or '无'}"
              for a in items],
        ])

    if act == "create":
        body = {
            "username": args.username, "display_name": args.display or args.username,
            "role": args.role, "password": args.password or "",
            "key_label": args.label or "",
        }
        code, d = call(url, "/api/agents", token, "POST", body=body)
        if code != 200:
            return emit(args, False, "members.create", error=f"创建失败 HTTP {code}：{d.get('detail') or ''}")
        return emit(args, True, "members.create", d, human=[
            f"✅ 成员已创建：{d['username']}（{args.role}）",
            f"   密码：{d.get('password')}",
            f"   Key ：{d.get('api_key')}",
            f"   绑定：{d.get('key_label')}"])

    code, d = call(url, "/api/agents", token)
    if code != 200:
        return emit(args, False, "members", error=f"读取成员失败 HTTP {code}：")
    target = find_agent(d.get("items") or [], args.target)
    if not target:
        return emit(args, False, "members", error=f"成员不存在：{args.target}")

    if act == "key":
        code, k = call(url, f"/api/agents/{target['id']}/key", token)
        if code != 200:
            return emit(args, False, "members.key", error=str(k.get("detail") or k))
        return emit(args, True, "members.key",
                    {"username": target["username"], "api_key": k.get("api_key")},
                    human=[k.get("api_key") or ""])

    if act == "set":
        body = {}
        if args.role:
            body["role"] = args.role
        if args.label is not None:
            body["key_label"] = args.label
        if args.password:
            body["password"] = args.password
        if args.enable:
            body["active"] = True
        if args.disable:
            body["active"] = False
        if args.rotate_key:
            body["rotate_key"] = True
        if not body:
            return emit(args, False, "members.set", error="没有要改的字段")
        code, r = call(url, f"/api/agents/{target['id']}", token, "PATCH", body=body)
        if code != 200:
            return emit(args, False, "members.set", error=f"修改失败 HTTP {code}：{r.get('detail') or ''}")
        return emit(args, True, "members.set",
                    {"username": target["username"], **{k: v for k, v in r.items() if k != "ok"}},
                    human=[f"✅ {target['username']} 已更新" + (f"，新 Key：{r['api_key']}" if r.get("api_key") else "")])

    if act == "rm":
        code, r = call(url, f"/api/agents/{target['id']}", token, "DELETE")
        if code != 200:
            return emit(args, False, "members.rm", error=f"删除失败 HTTP {code}：{r.get('detail') or ''}")
        return emit(args, True, "members.rm", r,
                    human=[f"✅ 已删除 {target['username']}（连带 {r.get('removed_projects')} 个项目）"])

    return emit(args, False, "members", error=f"未知动作：{act}")


# --------------------------------------------------------------------------- #
# 命令：自检（证明「真的能增删改」）
# --------------------------------------------------------------------------- #
def cmd_selfcheck(args):
    c = conn(args)
    if not c:
        return 2
    url, token = c
    steps = []
    slug = f"selfcheck-{int(time.time())}"
    tmp = Path(tempfile.mkdtemp(prefix="pvcheck-"))

    def step(name, ok, detail=""):
        steps.append({"step": name, "ok": bool(ok), "detail": detail})
        log(f"  {'✓' if ok else '✗'} {name}" + (f"  → {detail}" if detail and not ok else ""))
        return ok

    log(f"自检：{url} / {slug}")
    try:
        code, me = call(url, "/api/auth/me", token)
        role = (me.get("user") or {}).get("role") if code == 200 else None
        step("读取身份", code == 200, f"{code} {me.get('detail') or ''}")
        if role == "viewer":
            log("  角色是 viewer，只能读，跳过写操作检查")
            return emit(args, True, "selfcheck",
                        {"role": role, "steps": steps, "note": "viewer 无写权限，属预期"},
                        human=[f"自检结论：viewer 只能读，不能增删改（符合设计）"])

        (tmp / "index.html").write_text(
            "<!doctype html><meta charset=utf-8><title>selfcheck</title><h1>ok</h1>", "utf-8")
        (tmp / "sub").mkdir()
        (tmp / "sub" / "a.txt").write_text("hello", "utf-8")

        body, ctype = multipart(
            {"slug": slug, "title": "自检项目", "visibility": "link", "hours": "1",
             "tags": "selfcheck"},
            [("files", rel, p.read_bytes()) for rel, p in collect(tmp)],
        )
        code, created = call(url, "/api/projects", token, "POST", raw=body, ctype=ctype)
        step("创建（部署）", code == 200, f"{code} {created.get('detail') or ''}")
        if code != 200:
            raise RuntimeError("创建失败，后续无法继续")

        pv = (created.get("urls") or {}).get("preview", "")
        step("返回预览地址", bool(pv), pv)
        step("持链接可见：匿名可打开", probe(pv) == 200, f"HTTP {probe(pv)}")

        code, upd = call(url, f"/api/projects/{slug}", token, "PATCH", body={"visibility": "private"})
        step("改为仅自己可见", code == 200 and upd.get("visibility") == "private", f"{code}")
        step("仅自己可见：匿名看不到", is_gone(pv), f"HTTP {probe(pv, redirect=False)}")

        code, upd = call(url, f"/api/projects/{slug}", token, "PATCH", body={"visibility": "link"})
        step("改回持链接", code == 200 and upd.get("visibility") == "link", f"{code}")
        step("改回后匿名又能打开", probe(pv) == 200, f"HTTP {probe(pv)}")

        code, got = call(url, f"/api/projects/{slug}", token)
        step("读取详情", code == 200 and got.get("slug") == slug, f"{code}")

        code, listed = call(url, "/api/projects?status=all&limit=200&q=" + slug, token)
        step("列表可检索", code == 200 and any(
            p["slug"] == slug for p in (listed.get("items") or [])), f"{code}")

        before = (created.get("expires_at") or 0)
        code, ext = call(url, f"/api/projects/{slug}", token, "PATCH", body={"hours": 5})
        step("续期到 5 小时", code == 200 and (ext.get("expires_at") or 0) > before, f"{code}")

        code, _ = call(url, f"/api/projects/{slug}", token, "DELETE")
        step("删除", code == 200, f"{code}")
        step("删除后链接失效（跳门户）", is_gone(pv), f"HTTP {probe(pv, redirect=False)}")

        ok = all(s["ok"] for s in steps)
        return emit(args, ok, "selfcheck",
                    {"role": role, "slug": slug, "steps": steps, "all_ok": ok},
                    human=[f"\n自检结论：{'全部通过 ✅' if ok else '存在失败项 ❌'}（角色 {role}）"])
    except Exception as exc:  # noqa: BLE001
        return emit(args, False, "selfcheck", {"steps": steps}, error=str(exc))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #
def build_parser():
    # 子命令用 SUPPRESS：不然子解析器的同名默认值会把主解析器已经吃到的
    # --url/--token 覆盖成 None，命令就会去读上一次登录保存的旧地址。
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="输出单行 JSON")
    common.add_argument("--url", default=argparse.SUPPRESS,
                        help="站点地址（默认取上次登录的）")
    common.add_argument("--token", default=argparse.SUPPRESS,
                        help="API Key（默认取上次登录的）")

    ap = argparse.ArgumentParser(
        prog="agentctl",
        description=f"临时预览站 Agent 命令行 v{VERSION}（单文件、仅标准库）",
    )
    ap.add_argument("--json", action="store_true", help="输出单行 JSON")
    ap.add_argument("--url", help="站点地址（默认取上次登录的）")
    ap.add_argument("--token", help="API Key（默认取上次登录的）")
    ap.add_argument("--version", action="version", version=f"agentctl {VERSION}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("login", parents=[common], help="登录并保存凭据")
    p.add_argument("--username")
    p.add_argument("--password")
    p.add_argument("--api-key")
    p.set_defaults(func=cmd_login)

    sub.add_parser("whoami", parents=[common], help="当前身份与能力").set_defaults(func=cmd_whoami)
    sub.add_parser("health", parents=[common], help="站点与 Key 健康检查").set_defaults(func=cmd_health)

    p = sub.add_parser("deploy", parents=[common], help="上传目录并返回预览地址")
    p.add_argument("dir", nargs="?", default=".")
    p.add_argument("--slug")
    p.add_argument("--title", help="项目名：≤10 个中文字符（≈20 个半角）；不传退回目录名，超长截短")
    p.add_argument("--desc")
    p.add_argument("--tags", default="")
    p.add_argument("--ttl", type=float, help="存活小时数")
    p.add_argument("--forever", action="store_true")
    p.add_argument("--download", action="store_true", help="开放 zip 下载")
    p.add_argument("--zip", action="store_true", help="额外生成整站 zip")
    p.add_argument("--visibility", default="link", choices=list(VISIBILITY))
    p.add_argument("--expire-action", default="block", choices=["block", "delete"])
    p.add_argument("--no-verify", action="store_true", help="跳过部署后的地址探活")
    p.add_argument("--collection", help="归到哪个分组：id 或名字（子分组写 办公/报表）")
    p.set_defaults(func=cmd_deploy)

    p = sub.add_parser("link", parents=[common], help="登记一个外链项目")
    p.add_argument("url_to", metavar="target_url")
    p.add_argument("--title", help="项目名：≤10 个中文字符（≈20 个半角）；不传用 URL，超长截短")
    p.add_argument("--slug")
    p.add_argument("--desc")
    p.add_argument("--tags", default="")
    p.add_argument("--ttl", type=float)
    p.add_argument("--forever", action="store_true")
    p.add_argument("--visibility", default="link", choices=list(VISIBILITY))
    p.add_argument("--collection", help="归到哪个分组：id 或名字")
    p.set_defaults(func=cmd_link)

    p = sub.add_parser("ls", parents=[common], help="列出项目")
    p.add_argument("--status", default="all",
                   choices=["all", "online", "expired", "permanent", "deleted"])
    p.add_argument("--visibility", choices=list(VISIBILITY))
    p.add_argument("--kind", choices=["static", "zip", "link"])
    p.add_argument("--q")
    p.add_argument("--tag", action="append")
    p.add_argument("--sort", default="updated_at",
                   choices=["updated_at", "created_at", "expires_at", "views",
                            "downloads", "size_bytes", "title"])
    p.add_argument("--order", default="desc", choices=["asc", "desc"])
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--collection", help="只看某个分组：id / 名字 / none（未归类）")
    p.set_defaults(func=cmd_ls)

    p = sub.add_parser("show", parents=[common], help="项目详情")
    p.add_argument("slug")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("set", parents=[common], help="改可见性 / 到期 / 标题 / 标签 / 下载")
    p.add_argument("slug")
    p.add_argument("--visibility", choices=list(VISIBILITY))
    p.add_argument("--ttl", type=float)
    p.add_argument("--forever", action="store_true")
    p.add_argument("--title", help="改名：≤10 个中文字符（≈20 个半角），超长直接拒绝")
    p.add_argument("--desc")
    p.add_argument("--tags")
    p.add_argument("--download", action="store_true")
    p.add_argument("--no-download", action="store_true")
    p.add_argument("--collection", help="挪到某个分组：id 或名字")
    p.add_argument("--no-collection", action="store_true", help="移出分组（回到未归类）")
    p.set_defaults(func=cmd_set)

    p = sub.add_parser("extend", parents=[common], help="延长存活时间")
    p.add_argument("slug")
    p.add_argument("hours", nargs="?", type=float, default=24)
    p.add_argument("--forever", action="store_true")
    p.set_defaults(func=cmd_extend)

    p = sub.add_parser("rm", parents=[common], help="删除项目")
    p.add_argument("slug")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_rm)

    p = sub.add_parser("bulk", parents=[common], help="批量操作")
    p.add_argument("--action", required=True,
                   choices=["visibility", "extend", "permanent", "block", "expire",
                            "allow_download", "deny_download", "tag_add", "delete"])
    p.add_argument("--slugs", required=True, help="逗号分隔的 slug 列表")
    p.add_argument("--hours", type=float)
    p.add_argument("--visibility", choices=list(VISIBILITY))
    p.add_argument("--tags")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_bulk)

    p = sub.add_parser("stats", parents=[common], help="访问趋势")
    p.add_argument("--days", type=int, default=14)
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("members", parents=[common], help="成员管理（仅管理员）")
    p.add_argument("action", choices=["list", "create", "set", "rm", "key"])
    p.add_argument("target", nargs="?", help="成员 id 或 username")
    p.add_argument("--username")
    p.add_argument("--display")
    p.add_argument("--role", choices=["viewer", "publisher", "admin"])
    p.add_argument("--password")
    p.add_argument("--label", help="绑定给哪个 agent")
    p.add_argument("--enable", action="store_true")
    p.add_argument("--disable", action="store_true")
    p.add_argument("--rotate-key", action="store_true")
    p.set_defaults(func=cmd_members)

    p = sub.add_parser("collections", parents=[common], help="分组：列表 / 新建 / 删除")
    p.add_argument("action", nargs="?", default="ls", choices=["ls", "add", "rm", "delete"])
    p.add_argument("target", nargs="?", help="要删的分组（id 或名字）")
    p.add_argument("--name", help="add 时用：分组名字")
    p.add_argument("--parent", help="add 时用：挂在哪一级下面（id 或名字）")
    p.add_argument("--with-projects", action="store_true", help="删除时连项目一起删")
    p.set_defaults(func=cmd_collections)

    sub.add_parser("selfcheck", parents=[common],
                   help="用当前身份跑一遍增删改查").set_defaults(func=cmd_selfcheck)
    return ap


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
