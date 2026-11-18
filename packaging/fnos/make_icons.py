"""从 frontend/public/icon-512.png 生成飞牛要求的 64 / 256 图标。"""
import base64
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
TPL = Path(__file__).resolve().parent / 'template'
SRC = ROOT / 'frontend' / 'public' / 'icon-512.png'

targets = [
    (64, TPL / 'ICON.PNG'),
    (64, TPL / 'app/ui/images/icon_64.png'),
    (256, TPL / 'ICON_256.PNG'),
    (256, TPL / 'app/ui/images/icon_256.png'),
]

if not SRC.exists():
    sys.exit(f'源图标不存在: {SRC}')

DATA_URI = 'data:image/png;base64,' + base64.b64encode(SRC.read_bytes()).decode()

with sync_playwright() as p:
    b = p.chromium.launch(channel='chrome')
    pg = b.new_page()
    for size, dest in targets:
        dest.parent.mkdir(parents=True, exist_ok=True)
        pg.set_viewport_size({'width': size, 'height': size})
        pg.set_content(
            '<body style="margin:0;background:transparent">'
            f'<img src="{DATA_URI}" '
            f'style="width:{size}px;height:{size}px;display:block">'
            '</body>'
        )
        pg.wait_for_timeout(150)
        pg.screenshot(path=str(dest))
        print(f'{size}px → {dest.relative_to(TPL)}')
    b.close()
print('图标生成完成')
