"""用同目录的 icon.svg 渲染飞牛要求的 64 / 256 图标。"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
TPL = HERE / 'template'
SVG_FILE = HERE / 'icon.svg'

targets = [
    (64, TPL / 'ICON.PNG'),
    (64, TPL / 'app/ui/images/icon_64.png'),
    (256, TPL / 'ICON_256.PNG'),
    (256, TPL / 'app/ui/images/icon_256.png'),
]

if not SVG_FILE.exists():
    sys.exit(f'找不到图标源文件: {SVG_FILE}')

svg = SVG_FILE.read_text(encoding='utf-8')

with sync_playwright() as p:
    b = p.chromium.launch(channel='chrome')
    pg = b.new_page()
    for size, dest in targets:
        dest.parent.mkdir(parents=True, exist_ok=True)
        pg.set_viewport_size({'width': size, 'height': size})
        pg.set_content(
            '<style>html,body{margin:0;padding:0;overflow:hidden}'
            'svg{width:100vw;height:100vh;display:block}</style>' + svg
        )
        pg.wait_for_timeout(120)
        pg.screenshot(path=str(dest))
        print(f'{size}px → {dest.relative_to(TPL)}')
    b.close()
print('图标生成完成')
