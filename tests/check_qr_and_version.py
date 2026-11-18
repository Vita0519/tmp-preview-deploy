"""关于页二维码与版本/署名验收。"""
import base64
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_test import Client, multipart

BASE = os.environ.get('PV_BASE', 'http://127.0.0.1:8000')
USER = os.environ.get('PV_USER', 'admin')
PASS = os.environ.get('PV_PASS', 'admin123')
ok, bad = [], []

PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
)


def check(name, cond, extra=''):
    (ok if cond else bad).append(name)
    print(f"  {'✓' if cond else '✗'} {name}{(' → ' + str(extra)[:160]) if extra and not cond else ''}")


c = Client(BASE)
code, _ = c.login(USER, PASS)
check('登录', code == 200, code)

print('[1] 版本与署名')
code, meta = c.req('GET', '/api/meta')
want = (Path('VERSION').read_text(encoding='utf-8').strip() if Path('VERSION').exists() else '')
check('meta.version 与 VERSION 一致', meta.get('version') == want, (meta.get('version'), want))
check('约可见版本', (meta.get('project') or {}).get('author') == 'vita0519', (meta.get('project') or {}).get('author'))
check('未出现真实姓名', '孟庆炜' not in str(meta), 'meta 里仍有真名')

print('[2] 二维码上传 / 读取 / 删除')
code, d = c.req('GET', '/api/settings')
check('settings 有 qr 字段', code == 200 and 'qr' in d, list(d)[:8] if code == 200 else code)

body, ct = multipart({}, [('file', 'pay.png', PNG)])
code, d = c.req('POST', '/api/settings/qr?name=wechat', body, ct=ct)
check('上传赞赏码 200', code == 200, (code, d))
url = ((d.get('qr') or {}).get('wechat') or {}).get('url') if code == 200 else None
check('返回图片 URL', bool(url), d.get('qr'))

if url:
    code, _h, data = c.fetch_bytes(url, accept='image/*')
    check('图片可访问且内容一致', code == 200 and data == PNG, (code, len(data) if data else 0))

code, _h, _d = c.fetch_bytes('/api/settings/qr/group', accept='image/*')
check('未上传的槽返回 404', code == 404, code)

body, ct = multipart({}, [('file', 'bad.txt', b'not an image')])
code, d = c.req('POST', '/api/settings/qr?name=wechat', body, ct=ct)
check('非法格式 400', code == 400, (code, d))

code, d = c.req('DELETE', '/api/settings/qr/wechat')
check('删除 200', code == 200 and (d.get('qr') or {}).get('wechat') is None, d.get('qr'))

total = len(ok) + len(bad)
print(f'\n{len(ok)}/{total} 通过')
sys.exit(0 if not bad else 1)
