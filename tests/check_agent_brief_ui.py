"""成员 Key 交接文案验收：创建成员后一句话可复制，含 skill 地址、站点、Key。"""
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from playwright.sync_api import sync_playwright
from smoke_test import Client

BASE = os.environ.get('PV_BASE', 'http://127.0.0.1:8000')
USER = os.environ.get('PV_USER', 'admin')
PASSWORD = os.environ.get('PV_PASS', 'admin123')
ok, bad = [], []
tag = uuid.uuid4().hex[:5]
uname = f'agt{tag}'

with sync_playwright() as p:
    b = p.chromium.launch(channel='chrome')
    ctx = b.new_context(viewport={'width': 1440, 'height': 950},
                        permissions=['clipboard-read', 'clipboard-write'])
    pg = ctx.new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(BASE + '/', wait_until='networkidle')
    pg.fill('input[autocomplete="username"]', USER)
    pg.fill('input[type="password"]', PASSWORD)
    pg.click('button[type="submit"]')
    pg.wait_for_url(lambda u: '/login' not in u, timeout=15000)

    pg.goto(BASE + '/agents', wait_until='networkidle')
    pg.wait_for_timeout(400)
    pg.locator('button', has_text='添加成员').first.click()
    pg.wait_for_timeout(300)
    pg.fill('input[placeholder*="小写字母"]', uname)
    pg.fill('input[placeholder*="留空自动生成"]', 'Test12345')
    pg.locator('.modal-foot button', has_text='创建').click()
    pg.wait_for_selector('.modal:has-text("凭据（只显示一次）")', timeout=15000)
    pg.wait_for_timeout(300)

    brief = pg.locator('.modal .muted', has_text='tmp-preview-deploy skill').first.inner_text().strip()
    print('文案:', brief)

    def check(name, cond, extra=''):
        (ok if cond else bad).append(name)
        print(f"  {'✓' if cond else '✗'} {name}{(' → ' + str(extra)[:140]) if extra and not cond else ''}")

    check('一句话含 skill 地址', f'{BASE}/v/agent-guide' in brief, brief)
    check('含站点地址', f'站点 {BASE}' in brief, brief)
    check('含 API Key', 'API Key pv_' in brief, brief)
    check('含上传方式', 'POST /api/projects' in brief, brief)

    pg.locator('button', has_text='复制给 Agent').click()
    pg.wait_for_timeout(400)
    clip = pg.evaluate('navigator.clipboard.readText()')
    check('复制内容与展示一致', clip.strip() == brief, clip[:120])
    check('无 JS 报错', not errs, errs)
    pg.screenshot(path='C:/tmp/audit/agent_brief.png')
    b.close()

c = Client(BASE)
c.login(USER, PASSWORD)
_, data = c.req('GET', '/api/agents')
row = next((x for x in (data if isinstance(data, list) else data.get('items', [])) if x.get('username') == uname), None)
if row:
    c.req('DELETE', f"/api/agents/{row['id']}")
print('清理:', uname, '已删除' if row else '未找到')

total = len(ok) + len(bad)
print(f'\n{len(ok)}/{total} 通过')
sys.exit(0 if not bad else 1)
