"""版本检查、署名校验、赞赏码只读展示验收。"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_test import Client

BASE = os.environ.get('PV_BASE', 'http://127.0.0.1:8000')
USER = os.environ.get('PV_USER', 'admin')
PASS = os.environ.get('PV_PASS', 'admin123')
ok, bad = [], []


def check(name, cond, extra=''):
    (ok if cond else bad).append(name)
    print(f"  {'✓' if cond else '✗'} {name}{(' → ' + str(extra)[:160]) if extra and not cond else ''}")


c = Client(BASE)
check('匿名访问版本接口 401', c.req('GET', '/api/settings/version')[0] == 401)
c.login(USER, PASS)

want = Path('VERSION').read_text(encoding='utf-8').strip()
code, meta = c.req('GET', '/api/meta')
check('meta.version 与 VERSION 一致', meta.get('version') == want, (meta.get('version'), want))
check('署名是 vita0519', (meta.get('project') or {}).get('author') == 'vita0519', meta.get('project'))

code, d = c.req('GET', '/api/settings/version?force=1')
check('版本接口可用', code == 200 and d.get('current') == want, (code, d))
check('返回结构完整', all(k in d for k in ('ok', 'current', 'has_update')), list(d))

print('[赞赏码：只读，无上传接口]')
code, _ = c.req('GET', '/api/settings')
check('settings 不再包含 qr 字段', 'qr' not in _)
for path in ('/qr-wechat.png', '/qr-alipay.png'):
    code, _, data = c.fetch_bytes(path, accept='image/*')
    check(f'静态图 {path} 可访问', code == 200 and len(data or b'') > 10_000, code)
code, _ = c.req('POST', '/api/settings/qr?name=wechat')
check('上传接口已移除', code in (404, 405), code)

total = len(ok) + len(bad)
print(f'\n{len(ok)}/{total} 通过')
sys.exit(0 if not bad else 1)
