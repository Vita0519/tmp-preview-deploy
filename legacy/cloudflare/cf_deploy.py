#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cf_deploy.py —— 不依赖 wrangler，直接用 Cloudflare REST API 部署 Worker
（走代理时 wrangler 上传接口容易 fetch failed，REST 更稳）

用法:
  export CLOUDFLARE_API_TOKEN=xxx
  python3 cf_deploy.py --account <id> [--script tmp-preview] [--proxy http://172.17.0.1:20172]
"""
import argparse
import json
import os
import sys
import time
import uuid
import urllib.error
import urllib.request

API = 'https://api.cloudflare.com/client/v4'


class CF:
    def __init__(self, token, proxy=None):
        self.token = token
        handlers = []
        if proxy:
            handlers.append(urllib.request.ProxyHandler({'https': proxy, 'http': proxy}))
        self.opener = urllib.request.build_opener(*handlers)

    def req(self, method, path, data=None, ctype='application/json'):
        url = API + path
        headers = {'Authorization': 'Bearer ' + self.token}
        body = None
        if data is not None:
            body = data if isinstance(data, bytes) else json.dumps(data).encode()
            headers['Content-Type'] = ctype
        r = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with self.opener.open(r, timeout=120) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            raw = e.read().decode('utf-8', 'replace')
            try:
                return json.loads(raw)
            except Exception:
                return {'success': False, 'errors': [{'message': raw[:300]}]}

    def get(self, p):
        return self.req('GET', p)

    def post(self, p, d):
        return self.req('POST', p, d)

    def put(self, p, d):
        return self.req('PUT', p, d)


def multipart(files):
    """files: list[(name, filename, bytes, ctype)]"""
    boundary = '----cfdeploy' + uuid.uuid4().hex
    out = b''
    for name, fname, data, ctype in files:
        out += ('--%s\r\n' % boundary).encode()
        if fname:
            out += ('Content-Disposition: form-data; name="%s"; filename="%s"\r\n' % (name, fname)).encode()
        else:
            out += ('Content-Disposition: form-data; name="%s"\r\n' % name).encode()
        out += ('Content-Type: %s\r\n\r\n' % ctype).encode()
        out += data + b'\r\n'
    out += ('--%s--\r\n' % boundary).encode()
    return boundary, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--account', required=True)
    ap.add_argument('--script', default='tmp-preview')
    ap.add_argument('--worker', default=os.path.join(os.path.dirname(__file__), '..', 'assets', 'worker.js'))
    ap.add_argument('--admin', default=os.path.join(os.path.dirname(__file__), '..', 'assets', 'admin.js'))
    ap.add_argument('--title', default='临时预览服务')
    ap.add_argument('--ttl', default='24')
    ap.add_argument('--site-url', default='')
    ap.add_argument('--admin-token', required=True)
    ap.add_argument('--kv-id', required=True)
    ap.add_argument('--proxy', default=os.environ.get('HTTPS_PROXY', ''))
    args = ap.parse_args()

    token = os.environ.get('CLOUDFLARE_API_TOKEN')
    if not token:
        print('缺少 CLOUDFLARE_API_TOKEN', file=sys.stderr)
        sys.exit(2)

    cf = CF(token, args.proxy or None)
    A = args.account

    worker_src = open(args.worker, 'rb').read()
    admin_src = open(args.admin, 'rb').read()

    # ES module 入口：worker.js 里 import './admin.js'，所以两个模块都要传
    metadata = {
        'main_module': 'worker.js',
        'compatibility_date': '2024-11-01',
        'bindings': [
            {'type': 'kv_namespace', 'name': 'KV', 'namespace_id': args.kv_id},
            {'type': 'plain_text', 'name': 'SITE_TITLE', 'text': args.title},
            {'type': 'plain_text', 'name': 'DEFAULT_TTL_H', 'text': str(args.ttl)},
            {'type': 'plain_text', 'name': 'LOCAL_SITE_URL', 'text': args.site_url},
            {'type': 'plain_text', 'name': 'ADMIN_TOKEN', 'text': args.admin_token},
        ],
    }

    boundary, body = multipart([
        ('metadata', None, json.dumps(metadata).encode(), 'application/json'),
        ('worker.js', 'worker.js', worker_src, 'application/javascript+module'),
        ('admin.js', 'admin.js', admin_src, 'application/javascript+module'),
    ])

    print('→ 上传 Worker %s ...' % args.script)
    r = cf.req('PUT', '/accounts/%s/workers/scripts/%s' % (A, args.script), body,
               'multipart/form-data; boundary=' + boundary)
    if not r.get('success'):
        print('❌ 部署失败: %s' % json.dumps(r.get('errors'), ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
    print('✅ Worker 已上传 (etag=%s)' % r['result'].get('etag', '')[:16])

    # 配置 cron 触发器
    print('→ 配置 Cron */10 * * * * ...')
    sched = cf.put('/accounts/%s/workers/scripts/%s/schedules' % (A, args.script),
                   [{'cron': '*/10 * * * *'}])
    print('   %s' % ('✅ cron 已设置' if sched.get('success') else '⚠️ cron 设置失败: %s' % sched.get('errors')))

    # 开启 workers.dev 访问
    sub = cf.get('/accounts/%s/workers/subdomain' % A)
    subdomain = sub.get('result', {}).get('subdomain') if sub.get('success') else None
    if subdomain:
        cf.post('/accounts/%s/workers/scripts/%s/subdomain' % (A, args.script), {'enabled': True, 'previews_enabled': False})
        print('✅ workers.dev 地址: https://%s.%s.workers.dev' % (args.script, subdomain))
    else:
        print('⚠️  账号没有 workers.dev 子域，需去控制台 Workers 页首次访问以创建')

    print('\n完成。自定义域名请在控制台 Workers → %s → Settings → Domains 绑定。' % args.script)


if __name__ == '__main__':
    main()
