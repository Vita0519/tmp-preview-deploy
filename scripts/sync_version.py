"""改版本号只改仓库根 VERSION，然后跑这个脚本同步到各处的硬编码。

用法：python scripts/sync_version.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ver = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+', ver):
        print(f'VERSION 内容不合法: {ver!r}', file=sys.stderr)
        return 1

    # 前端 package.json
    pkg = ROOT / 'frontend' / 'package.json'
    data = json.loads(pkg.read_text(encoding='utf-8'))
    data['version'] = ver
    pkg.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    # 飞牛 manifest
    mani = ROOT / 'packaging' / 'fnos' / 'template' / 'manifest'
    text = mani.read_text(encoding='utf-8')
    text = re.sub(r'^version\s*=.*$', f'version               = {ver}', text, flags=re.M)
    mani.write_text(text, encoding='utf-8')

    # fpk compose 的镜像 tag
    comp = ROOT / 'packaging' / 'fnos' / 'template' / 'app' / 'docker' / 'docker-compose.yaml'
    ctext = comp.read_text(encoding='utf-8')
    ctext = re.sub(r'(image: ghcr\.io/vita0519/tmp-preview:)\S+', rf'\g<1>{ver}', ctext)
    comp.write_text(ctext, encoding='utf-8')

    # 根 compose 的镜像 tag
    rcomp = ROOT / 'docker-compose.yml'
    rtext = rcomp.read_text(encoding='utf-8')
    rtext = re.sub(r'(image: ghcr\.io/vita0519/tmp-preview:)\S+', rf'\g<1>{ver}', rtext)
    rcomp.write_text(rtext, encoding='utf-8')

    # CI 默认 tag
    wf = ROOT / '.github' / 'workflows' / 'docker-image.yml'
    wtext = wf.read_text(encoding='utf-8')
    wtext = re.sub(r'default: "\d+\.\d+\.\d+"', f'default: "{ver}"', wtext)
    wtext = re.sub(r"inputs\.tag \|\| '\d+\.\d+\.\d+'", f"inputs.tag || '{ver}'", wtext)
    wf.write_text(wtext, encoding='utf-8')

    print(f'已同步版本 {ver}：package.json / manifest / compose x2 / workflow')
    return 0


if __name__ == '__main__':
    sys.exit(main())
