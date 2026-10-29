#!/usr/bin/env python3
"""通过 GitHub Git Data API 推送本地 HEAD（绕开被墙的 git-upload-pack）。

用法：
    python tools/push_api.py [--repo owner/name] [--branch main] [--message msg]

原理：本机 git push 走 https://github.com 被代理拦断，但 api.github.com 可通，
因此用 REST API 把 HEAD 的完整文件树重建为远端 tree（不带 base_tree，天然完成增删），
再创建一个以远端当前 head 为父的 commit，最后 PATCH ref 指向它。

依赖：标准库；token 从 git credential（GCM 已存凭据）或 $GITHUB_TOKEN 读取。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import ssl
import subprocess
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"

# 某些环境（公司代理 / 精简版 Python）没有可用 CA，先正常校验，失败再降级重试一次。
_VERIFY = not os.environ.get("PV_INSECURE")


def _open(req, timeout=60):
    global _VERIFY
    ctx = ssl.create_default_context() if _VERIFY else ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return r.read()
    except urllib.error.URLError as e:
        if _VERIFY and "CERTIFICATE_VERIFY_FAILED" in str(e):
            print("! 证书校验失败，改用不校验模式重试（仅本次进程）", file=sys.stderr)
            _VERIFY = False
            return _open(req, timeout)
        raise


def token() -> str:
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        return tok.strip()
    p = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        text=True, capture_output=True, check=True,
    )
    for line in p.stdout.splitlines():
        if line.startswith("password="):
            return line[len("password="):].strip()
    raise SystemExit("未取到 GitHub 凭据")


def call(method: str, path: str, tok: str, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(API + path, data=data, method=method)
    req.add_header("Authorization", f"Bearer {tok}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        return json.loads(_open(req).decode() or "{}")
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise SystemExit(f"{method} {path} -> {e.code}\n{body[:800]}")


def ls_tree(rev: str):
    out = subprocess.run(
        ["git", "ls-tree", "-r", "-z", rev], capture_output=True, check=True
    ).stdout.decode()
    rows = []
    for rec in out.split("\0"):
        if not rec:
            continue
        meta, path = rec.split("\t", 1)
        mode, typ, sha = meta.split()
        rows.append((mode, typ, sha, path))
    return rows


def blob(mode: str, sha: str, path: str) -> bytes:
    if mode == "160000":  # submodule
        return b""
    return subprocess.run(
        ["git", "cat-file", "blob", sha], capture_output=True, check=True
    ).stdout


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="Vita0519/tmp-preview-deploy")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--rev", default="HEAD")
    ap.add_argument("--message")
    args = ap.parse_args()

    tok = token()
    head = subprocess.run(
        ["git", "rev-parse", args.rev], capture_output=True, text=True, check=True
    ).stdout.strip()
    msg = args.message or subprocess.run(
        ["git", "log", "-1", "--pretty=%B", head], capture_output=True, text=True, check=True
    ).stdout.strip()

    ref = call("GET", f"/repos/{args.repo}/git/ref/heads/{args.branch}", tok)
    parent = ref["object"]["sha"]
    print(f"remote {args.branch} = {parent[:7]}  local {args.rev} = {head[:7]}")

    entries, total = [], 0
    for mode, typ, sha, path in ls_tree(head):
        if typ != "blob":
            print(f"  skip {typ} {path}")
            continue
        raw = blob(mode, sha, path)
        total += len(raw)
        b = call("POST", f"/repos/{args.repo}/git/blobs", tok, {
            "content": base64.b64encode(raw).decode(),
            "encoding": "base64",
        })
        entries.append({
            "path": path,
            "mode": mode,
            "type": "blob",
            "sha": b["sha"],
        })
        print(f"  blob {path} ({len(raw)} B)")
    print(f"{len(entries)} blobs, {total/1024:.0f} KiB")

    tree = call("POST", f"/repos/{args.repo}/git/trees", tok, {"tree": entries})
    commit = call("POST", f"/repos/{args.repo}/git/commits", tok, {
        "message": msg,
        "tree": tree["sha"],
        "parents": [parent],
    })
    call("PATCH", f"/repos/{args.repo}/git/refs/heads/{args.branch}", tok, {
        "sha": commit["sha"],
        "force": False,
    })
    print(f"pushed -> {commit['sha'][:7]}  https://github.com/{args.repo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
