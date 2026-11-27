"""渲染飞牛要求的 64 / 256 图标。

源文件两种，按优先级取：
  1. icon-src.jpg —— 原始设计稿（位图）。图标最终只交付 64/256 两档 PNG，
     位图降采样比自动描摹的矢量更干净（描摹版在 128px 以上有明显毛边），所以以它为准；
  2. icon.svg    —— 手绘矢量稿，icon-src.jpg 不存在时回退到它。

圆角 22%（56/256）与图标自身形状对齐，四角导出为透明。
"""
import base64
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
TPL = HERE / 'template'
RASTER = HERE / 'icon-src.jpg'
SVG_FILE = HERE / 'icon.svg'

targets = [
    (64, TPL / 'ICON.PNG'),
    (64, TPL / 'app/ui/images/icon_64.png'),
    (256, TPL / 'ICON_256.PNG'),
    (256, TPL / 'app/ui/images/icon_256.png'),
]

BASE_CSS = 'html,body{margin:0;padding:0;overflow:hidden;background:transparent}'

if RASTER.exists():
    b64 = base64.b64encode(RASTER.read_bytes()).decode()
    # 原图四周留了一圈白底，放大 4.5% 把它挤出可视区，圆角边缘才不会挂白
    markup = (
        f'<style>{BASE_CSS}'
        '.card{width:100vw;height:100vh;border-radius:22%;overflow:hidden}'
        '.card img{width:100%;height:100%;object-fit:cover;object-position:center;'
        'transform:scale(1.045);display:block}</style>'
        f'<div class="card"><img src="data:image/jpeg;base64,{b64}"></div>'
    )
    src_name = RASTER.name
elif SVG_FILE.exists():
    markup = (
        f'<style>{BASE_CSS}svg{{width:100vw;height:100vh;display:block}}</style>'
        + SVG_FILE.read_text(encoding='utf-8')
    )
    src_name = SVG_FILE.name
else:
    sys.exit(f'找不到图标源文件：{RASTER} 或 {SVG_FILE}')

print(f'图标源：{src_name}')

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
        pg.set_content(markup)
        pg.wait_for_timeout(140)
        # 图标自带圆角，四角必须透明：漏掉 omit_background 会导出白底方块
        pg.screenshot(path=str(dest), omit_background=True)
        print(f'{size}px → {dest.relative_to(TPL)}')
    b.close()
print('图标生成完成')
