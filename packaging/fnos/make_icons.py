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
    # 本机不一定装了 chrome：依次退到 Edge / 内置 Chromium
    last = None
    for ch in ('chrome', 'msedge', None):
        try:
            b = p.chromium.launch(**({'channel': ch} if ch else {}))
            break
        except Exception as exc:  # noqa: BLE001
            last = exc
    else:
        sys.exit(f'找不到可用的浏览器内核：{last}')
    pg = b.new_page()
    for size, dest in targets:
        dest.parent.mkdir(parents=True, exist_ok=True)
        pg.set_viewport_size({'width': size, 'height': size})
        pg.set_content(
            '<style>html,body{margin:0;padding:0;overflow:hidden;background:transparent}'
            'svg{width:100vw;height:100vh;display:block}</style>' + svg
        )
        pg.wait_for_timeout(120)
        # 图标自带圆角，四角必须透明：之前漏了这个参数，导出的 PNG 四角是白的，
        # 放到深色桌面上会露出一圈白边
        pg.screenshot(path=str(dest), omit_background=True)
        print(f'{size}px → {dest.relative_to(TPL)}')
    b.close()
print('图标生成完成')
