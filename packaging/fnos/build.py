"""构建飞牛 fpk：复制模板 → 附带已构建前端与后端源码 → fnpack 打包。

用法：
    python packaging/fnos/build.py
    FNPACK=/path/to/fnpack python packaging/fnos/build.py
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TPL = HERE / 'template'
OUT = HERE / 'out'
APP = OUT / 'tmp-preview'
FNPACK = os.environ.get('FNPACK') or shutil.which('fnpack') or r'C:\tmp\fnpack.exe'


def main() -> int:
    if not (ROOT / 'frontend' / 'dist' / 'index.html').exists():
        print('[!] frontend/dist 不存在，先执行：cd frontend && npm run build', file=sys.stderr)
        return 1

    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)
    shutil.copytree(TPL, APP)

    # 构建上下文：单阶段镜像，前端用已构建的 dist
    src = APP / 'app' / 'docker' / 'src'
    src.mkdir(parents=True)
    shutil.copytree(ROOT / 'backend', src / 'backend',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copytree(ROOT / 'frontend' / 'dist', src / 'frontend' / 'dist')
    for name in ('LICENSE', 'NOTICE'):
        if (ROOT / name).exists():
            shutil.copy2(ROOT / name, src / name)
    shutil.copy2(APP / 'app' / 'docker' / 'Dockerfile', src / 'Dockerfile')

    required = [
        APP / 'manifest', APP / 'config/privilege', APP / 'config/resource',
        APP / 'ICON.PNG', APP / 'ICON_256.PNG', APP / 'app/ui/config',
        APP / 'app/docker/docker-compose.yaml', src / 'Dockerfile',
    ]
    missing = [str(p.relative_to(APP)) for p in required if not p.exists()]
    if missing:
        print('[!] 缺少必需文件: ' + ', '.join(missing), file=sys.stderr)
        return 1

    if not Path(FNPACK).exists():
        print(f'[!] 找不到 fnpack: {FNPACK}', file=sys.stderr)
        return 1

    r = subprocess.run([FNPACK, 'build'], cwd=APP, capture_output=True, text=True)
    print(r.stdout.strip()[-1500:])
    if r.returncode != 0:
        print(r.stderr.strip()[-1500:], file=sys.stderr)
        return r.returncode

    produced = sorted(APP.glob('*.fpk')) + sorted(OUT.glob('*.fpk'))
    if not produced:
        produced = sorted(OUT.rglob('*.fpk'))
    if not produced:
        print('[!] fnpack 没有产出 .fpk', file=sys.stderr)
        return 1

    target = OUT / produced[0].name
    if produced[0] != target:
        shutil.move(str(produced[0]), target)
    size = target.stat().st_size / 1024 / 1024
    print(f'\n产物: {target}\n大小: {size:.1f} MB')
    return 0


if __name__ == '__main__':
    sys.exit(main())
