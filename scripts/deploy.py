#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tmp-preview deploy —— 一键把本地目录上传成临时预览站

用法:
  python3 deploy.py <目录> [--slug name] [--name 显示名] [--desc 描述]
                    [--ttl 24] [--zip] [--no-index]

  --ttl 单位小时，支持小数（0.5 = 30 分钟）。省略则用服务端默认值。
  --zip 额外打包一份 zip 供下载（大文件建议开，用户点一下拿整包）。

配置读取顺序:
  1) 命令行 --url / --token
  2) 环境变量 TMP_PREVIEW_URL / TMP_PREVIEW_TOKEN
  3) 同目录 preview.json / ~/.openclaw/credentials/tmp-preview.json
     格式: {"url": "https://test.aitell.vip", "token": "xxxx"}
"""
import argparse
import io
import json
import os
import sys
import urllib.request
import urllib.error
import zipfile
from pathlib import Path

SKIP_DIRS = {'.git', 'node_modules', '.venv', '__pycache__', '.idea', '.vscode', 'dist/.cache'}
SKIP_FILES = {'.DS_Store', 'Thumbs.db'}
MAX_SINGLE = 90 * 1024 * 1024

# 默认代理（国内出网），可用 --proxy 或 NO_PROXY 覆盖
DEFAULT_PROXY = os.environ.get('TMP_PREVIEW_PROXY') or os.environ.get('HTTPS_PROXY') or ''


def build_opener(proxy):
    handlers = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({'http': proxy, 'https': proxy}))
    return urllib.request.build_opener(*handlers)

# Cloudflare 默认阻挡非浏览器 UA（error 1010），统一伪装
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'


def find_config():
    here = Path(__file__).resolve().parent
    for p in (here / 'preview.json', Path.home() / '.openclaw/credentials/tmp-preview.json'):
        if p.is_file():
            try:
                return json.loads(p.read_text('utf-8'))
            except Exception:
                pass
    return {}


def slugify(name):
    import re
    raw = str(name).strip()
    s = re.sub(r'[^a-z0-9\-_]+', '-', raw.lower()).strip('-')
    if not s:
        h = 0
        for ch in raw:
            h = (h * 31 + ord(ch)) % 0xFFFFFF
        s = 'p-' + format(h, 'x')
    return s[:60]


def collect(root: Path):
    """返回 [(相对路径, Path)]，跳过垃圾目录"""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith('.')]
        for fn in filenames:
            if fn in SKIP_FILES:
                continue
            p = Path(dirpath) / fn
            rel = p.relative_to(root).as_posix()
            out.append((rel, p))
    return out


def multipart(fields, files):
    """files: list[(fieldname, filename, bytes)]"""
    boundary = '----tmpPreview' + os.urandom(12).hex()
    buf = io.BytesIO()
    for k, v in fields.items():
        buf.write(('--%s\r\n' % boundary).encode())
        buf.write(('Content-Disposition: form-data; name="%s"\r\n\r\n' % k).encode())
        buf.write(str(v).encode('utf-8'))
        buf.write(b'\r\n')
    for field, fname, data in files:
        buf.write(('--%s\r\n' % boundary).encode())
        buf.write(('Content-Disposition: form-data; name="%s"; filename="%s"\r\n' % (field, fname)).encode('utf-8'))
        buf.write(b'Content-Type: application/octet-stream\r\n\r\n')
        buf.write(data)
        buf.write(b'\r\n')
    buf.write(('--%s--\r\n' % boundary).encode())
    return boundary, buf.getvalue()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('dir', nargs='?', default=None)
    ap.add_argument('--link', help='外部链接模式：只登记一个 URL（无需目录与文件）')
    ap.add_argument('--slug')
    ap.add_argument('--name')
    ap.add_argument('--desc', default='')
    ap.add_argument('--ttl', type=float, default=None,
                    help='存活小时数；0 或配合 --forever 表示永久（默认 24）')
    ap.add_argument('--forever', action='store_true', help='永久保存（不自动到期）')
    ap.add_argument('--expire-action', choices=['block', 'delete'], default='block',
                    help='到期后行为：block=停止访问保留文件（默认），delete=删除项目')
    ap.add_argument('--zip', action='store_true')
    ap.add_argument('--allow-download', action='store_true',
                    help='开放 zip 下载（默认关闭，需管理员显式开启）')
    ap.add_argument('--no-index', action='store_true')
    ap.add_argument('--url')
    ap.add_argument('--token')
    ap.add_argument('--proxy', default=DEFAULT_PROXY)
    args = ap.parse_args()

    cfg = find_config()
    base = (args.url or os.environ.get('TMP_PREVIEW_URL') or cfg.get('url') or '').rstrip('/')
    token = args.token or os.environ.get('TMP_PREVIEW_TOKEN') or cfg.get('token') or ''
    if not args.proxy:
        args.proxy = cfg.get('proxy') or ''
    if not base or not token:
        print('缺少 url/token。请设置 preview.json 或 --url/--token', file=sys.stderr)
        sys.exit(2)

    root = Path(args.dir).expanduser().resolve() if args.dir else None

    # 外链模式：不碰文件系统，直接建一张“外部链接卡片”
    if args.link:
        slug = args.slug or slugify(args.name or args.link)
        name = args.name or args.link
        fields = {'slug': slug, 'name': name, 'desc': args.desc, 'link': args.link}
        fields['expireAction'] = args.expire_action
        if args.forever or args.ttl == 0:
            fields['ttl'] = 'forever'
        elif args.ttl is not None:
            fields['ttl'] = args.ttl
        boundary, body = multipart(fields, [])
        req = urllib.request.Request(
            base + '/upload',
            data=body,
            method='POST',
            headers={
                'content-type': 'multipart/form-data; boundary=' + boundary,
                'x-admin-token': token,
                'user-agent': UA,
            },
        )
        try:
            with build_opener(args.proxy).open(req, timeout=60) as resp:
                out = json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            print('创建外链失败 HTTP %s: %s' % (e.code, e.read().decode('utf-8', 'replace')), file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print('创建外链失败：%s' % e, file=sys.stderr)
            sys.exit(1)
        if not out.get('ok'):
            print('服务端拒绝：%s' % out, file=sys.stderr)
            sys.exit(1)
        print('✅ 外链已创建：%s → %s' % (out.get('slug'), out.get('link')))
        print('   门户：%s/' % base)
        return

    if not root or not root.is_dir():
        print('不是目录：%s' % root, file=sys.stderr)
        sys.exit(2)

    slug = args.slug or slugify(root.name)
    name = args.name or root.name

    items = collect(root)
    if not items:
        print('目录是空的', file=sys.stderr)
        sys.exit(2)

    if not args.no_index and not any(r.lower() in ('index.html', 'index.htm') for r, _ in items):
        print('⚠️  没有 index.html，预览可能 404。用 --no-index 可强制忽略。', file=sys.stderr)
        sys.exit(3)

    big = [(r, p) for r, p in items if p.stat().st_size > MAX_SINGLE]
    if big:
        print('⚠️  以下文件超过 90MB，建议排除：', file=sys.stderr)
        for r, p in big:
            print('   %s (%.1f MB)' % (r, p.stat().st_size / 1048576), file=sys.stderr)

    total = sum(p.stat().st_size for _, p in items)
    print('→ 项目 %s（%d 文件，%.1f MB）→ %s' % (name, len(items), total / 1048576, base))

    files = [('files', rel, p.read_bytes()) for rel, p in items]

    if args.zip:
        zbuf = io.BytesIO()
        with zipfile.ZipFile(zbuf, 'w', zipfile.ZIP_DEFLATED) as z:
            for rel, p in items:
                z.write(p, rel)
        files.append(('zip', '%s.zip' % slug, zbuf.getvalue()))
        print('  已打包 zip：%.1f MB' % (len(zbuf.getvalue()) / 1048576))

    fields = {'slug': slug, 'name': name, 'desc': args.desc}
    fields['allowDownload'] = '1' if args.allow_download else '0'
    fields['expireAction'] = args.expire_action
    if args.forever or args.ttl == 0:
        fields['ttl'] = 'forever'
    elif args.ttl is not None:
        fields['ttl'] = args.ttl

    boundary, body = multipart(fields, files)
    req = urllib.request.Request(
        base + '/upload',
        data=body,
        method='POST',
        headers={
            'content-type': 'multipart/form-data; boundary=' + boundary,
            'x-admin-token': token,
            'user-agent': UA,
        },
    )
    try:
        opener = build_opener(args.proxy)
        with opener.open(req, timeout=600) as resp:
            out = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        print('上传失败 HTTP %s: %s' % (e.code, e.read().decode('utf-8', 'replace')), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print('上传失败：%s' % e, file=sys.stderr)
        sys.exit(1)

    if not out.get('ok'):
        print('服务端拒绝：%s' % out, file=sys.stderr)
        sys.exit(1)

    print('✅ 完成')
    print('   预览：%s%s' % (base, out['url']))
    if out.get('download'):
        print('   下载：%s%s' % (base, out['download']))
    print('   门户：%s/' % base)
    if out.get('permanent'):
        print('   时长：永久（不自动到期）')
    elif out.get('expireAt'):
        import datetime
        print('   到期：%s' % datetime.datetime.fromtimestamp(out['expireAt'] / 1000).strftime('%Y-%m-%d %H:%M:%S'))
    if out.get('expireAction') == 'delete':
        print('   到期后：停止访问并删除项目')
    else:
        print('   到期后：停止访问（保留文件）')


if __name__ == '__main__':
    main()
