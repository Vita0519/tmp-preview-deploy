#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tmp-preview admin —— 管理已部署的临时项目

用法:
  python3 admin.py list
  python3 admin.py ttl <slug> <小时>
  python3 admin.py ttl-all <小时>
  python3 admin.py delete <slug>
  python3 admin.py open [slug]        # 打印预览链接

配置同 deploy.py（preview.json / --url / --token）。
"""
import argparse
import datetime
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_PROXY = os.environ.get('TMP_PREVIEW_PROXY') or os.environ.get('HTTPS_PROXY') or ''


def build_opener(proxy):
    handlers = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({'http': proxy, 'https': proxy}))
    return urllib.request.build_opener(*handlers)


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


def call(base, token, path, body=None, proxy=None):
    req = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode() if body else None,
        method='POST' if body else 'GET',
        headers={'content-type': 'application/json', 'x-admin-token': token, 'user-agent': UA},
    )
    try:
        with build_opener(proxy).open(req, timeout=60) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return {'ok': False, 'error': 'HTTP %s %s' % (e.code, e.read().decode('utf-8', 'replace'))}


def fmt(ms):
    if ms is None or ms == 0:
        return '永久'
    if ms <= 0:
        return '已到期'
    d, h = ms // 86400000, ms % 86400000 // 3600000
    m, s = ms % 3600000 // 60000, ms % 60000 // 1000
    if d > 0:
        return '%d天%d小时' % (d, h)
    if h > 0:
        return '%dh%02dm%02ds' % (h, m, s)
    return '%dm%02ds' % (m, s)


def fmt_time(ms):
    if not ms:
        return '—'
    import datetime
    return datetime.datetime.fromtimestamp(ms / 1000).strftime('%Y-%m-%d %H:%M')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['list', 'ttl', 'ttl-all', 'delete', 'open', 'download', 'action', 'views', 'flush-views'])
    ap.add_argument('a', nargs='?')
    ap.add_argument('b', nargs='?')
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
        print('缺少 url/token', file=sys.stderr)
        sys.exit(2)

    if args.cmd == 'open':
        print(base + ('/' + args.a + '/' if args.a else '/'))
        return

    if args.cmd == 'list':
        d = call(base, token, '/api/admin/list', proxy=args.proxy)
        if not d.get('ok'):
            print('读取失败：%s' % d.get('error'), file=sys.stderr)
            sys.exit(1)
        now = d['serverNow']
        if not d['projects']:
            print('（无项目）')
            return
        for p in d['projects']:
            ns = p['expireAt'] - now if p.get('expireAt') else 0
            act = '删除' if p.get('expireAction') == 'delete' else '停访保留'
            ctime = fmt_time(p.get('createdAt'))
            print('%-22s %-16s 👁%-5s 建 %-16s %3d 文件  %-8s %-8s %-8s 剩余 %s' % (
                p['slug'], ('/' + p['slug'] + '/'), p.get('views', 0), ctime, p.get('files', 0),
                '有zip' if p.get('zipName') else '无',
                '下载开' if p.get('allowDownload') else '下载关',
                act, fmt(ns if p.get('expireAt') else None)))
        return

    if args.cmd == 'views':
        # views <slug> | views <slug> <n>  → 查看或设为 n（0 = 清零）
        if not args.a:
            print('用法: admin.py views <slug> [次数]', file=sys.stderr)
            sys.exit(2)
        if args.b is None:
            d = call(base, token, '/api/admin/list', proxy=args.proxy)
            p = next((x for x in d.get('projects', []) if x['slug'] == args.a), None)
            if not p:
                print('找不到项目 %s' % args.a, file=sys.stderr)
                sys.exit(1)
            print('%s 访问次数：%s' % (args.a, p.get('views', 0)))
        else:
            d = call(base, token, '/api/admin/views', {'slug': args.a, 'views': int(args.b)}, proxy=args.proxy)
            print('✅ %s 访问次数已设为 %s' % (args.a, d.get('views')) if d.get('ok') else '失败：%s' % d.get('error'))
        return

    if args.cmd == 'flush-views':
        # 把各项目「待写入」的访问计数合并落库（与 cron 同一逻辑，带锁互斥）
        d = call(base, token, '/api/admin/flush-views', {}, proxy=args.proxy)
        if d.get('ok'):
            print('跳过（正在被其它 flush 占用）' if d.get('skipped') else '✅ 已落库项目数：%s' % d.get('flushed', 0))
        else:
            print('失败：%s' % d.get('error'), file=sys.stderr)
            sys.exit(1)
        return

    if args.cmd == 'action':
        # action <slug> block|delete
        if not args.a or (args.b or '').lower() not in ('block', 'delete'):
            print('用法: admin.py action <slug> block|delete', file=sys.stderr)
            sys.exit(2)
        act = args.b.lower()
        # 保留当前时长：永久传 0，否则传剩余小时
        d0 = call(base, token, '/api/admin/list', proxy=args.proxy)
        p0 = next((x for x in d0.get('projects', []) if x['slug'] == args.a), None)
        if not p0:
            print('找不到项目 %s' % args.a, file=sys.stderr)
            sys.exit(1)
        hrs = 0 if p0.get('permanent') else max(0.01, (p0['expireAt'] - d0['serverNow']) / 3600e3)
        d = call(base, token, '/api/admin/ttl', {'slug': args.a, 'hours': hrs, 'action': act}, proxy=args.proxy)
        if d.get('ok'):
            print('✅ %s 到期后：%s' % (args.a, '删除项目' if act == 'delete' else '停止访问（保留文件）'))
        else:
            print('失败：%s' % d.get('error'), file=sys.stderr)
            sys.exit(1)
        return

    if args.cmd == 'download':
        # download <slug> on|off
        if not args.a or (args.b or '').lower() not in ('on', 'off', '1', '0', 'true', 'false'):
            print('用法: admin.py download <slug> on|off', file=sys.stderr)
            sys.exit(2)
        allow = (args.b or '').lower() in ('on', '1', 'true')
        d = call(base, token, '/api/admin/download', {'slug': args.a, 'allow': allow}, proxy=args.proxy)
        if d.get('ok'):
            print('✅ %s 下载已%s' % (args.a, '开放' if allow else '关闭'))
        else:
            print('失败：%s' % d.get('error'), file=sys.stderr)
            sys.exit(1)
        return

    if args.cmd == 'ttl':
        if not args.a or args.b is None:
            print('用法: admin.py ttl <slug> <小时>（0=永久）', file=sys.stderr)
            sys.exit(2)
        d = call(base, token, '/api/admin/ttl', {'slug': args.a, 'hours': float(args.b)}, proxy=args.proxy)
        if d.get('ok'):
            if d['project'].get('permanent'):
                print('✅ %s 已设为永久' % args.a)
            else:
                print('✅ %s 到期时间已更新' % args.a)
        else:
            print('失败：%s' % d.get('error'), file=sys.stderr)
            sys.exit(1)
        return

    if args.cmd == 'ttl-all':
        d = call(base, token, '/api/admin/list', proxy=args.proxy)
        if not d.get('ok'):
            print('读取失败', file=sys.stderr)
            sys.exit(1)
        hours = float(args.a)
        for p in d['projects']:
            call(base, token, '/api/admin/ttl', {'slug': p['slug'], 'hours': hours, 'action': p.get('expireAction') or 'block'}, proxy=args.proxy)
        print('✅ 已把 %d 个项目重设为 %s' % (len(d['projects']), '永久' if hours <= 0 else '%g 小时' % hours))
        return

    if args.cmd == 'delete':
        if not args.a:
            print('用法: admin.py delete <slug>', file=sys.stderr)
            sys.exit(2)
        d = call(base, token, '/api/admin/delete', {'slug': args.a}, proxy=args.proxy)
        print('✅ 已删除 %s' % args.a if d.get('ok') else '失败：%s' % d.get('error'))
        return


if __name__ == '__main__':
    main()
