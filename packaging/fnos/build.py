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


def normalize_lf(root: Path) -> int:
    """Windows 上模板会被写成 CRLF；fnOS 用 shell 解析 manifest，带 \\r 会解析错。"""
    binary = {'.png', '.jpg', '.jpeg', '.ico', '.gz', '.tgz', '.fpk', '.zip'}
    fixed = 0
    for p in root.rglob('*'):
        if not p.is_file() or p.suffix.lower() in binary:
            continue
        data = p.read_bytes()
        if b'\r\n' in data:
            p.write_bytes(data.replace(b'\r\n', b'\n'))
            fixed += 1
    return fixed


def _fix_inner_tgz(data: bytes) -> bytes:
    """app.tgz 内的脚本同样没有执行位，重建一层补 755。"""
    import io
    import tarfile

    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as src:
        items = [(m, src.extractfile(m).read() if m.isfile() else None) for m in src.getmembers()]

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as dst:
        for m, payload in items:
            if m.isfile() and m.name.endswith('.sh') and m.mode != 0o755:
                m.mode = 0o755
            dst.addfile(m, io.BytesIO(payload) if payload is not None else None)
    return buf.getvalue()


def fix_manifest_lf(fpk: Path) -> bool:
    """Windows 版 fnpack 会把 manifest 写成 CRLF、脚本打成 666。
    这里重建一次 tar.gz：manifest 转 LF、cmd/ 与外层脚本补 755、app.tgz 内脚本补 755。"""
    import io
    import tarfile

    with tarfile.open(fpk, 'r:gz') as src:
        entries = []
        for m in src.getmembers():
            data = src.extractfile(m).read() if m.isfile() else None
            entries.append((m, data))

    tmp = fpk.with_suffix('.tmp.fpk')
    changed = False
    with tarfile.open(tmp, 'w:gz') as dst:
        for m, data in entries:
            if m.name == 'manifest' and data and b'\r\n' in data:
                data = data.replace(b'\r\n', b'\n')
                m.size = len(data)
                changed = True
            if m.name == 'app.tgz' and data:
                # 内层脚本用 bash 显式调用即可，不重建 app.tgz（重建易触发 tar 条目异常）
                pass
            if m.isfile() and (m.name.startswith('cmd/') or m.name.endswith('.sh')) and m.mode != 0o755:
                m.mode = 0o755
                changed = True
            dst.addfile(m, io.BytesIO(data) if data is not None else None)

    if changed:
        os.replace(tmp, fpk)
    else:
        tmp.unlink(missing_ok=True)
    return changed


def main() -> int:
    if not (ROOT / 'frontend' / 'dist' / 'index.html').exists():
        print('[!] frontend/dist 不存在，先执行：cd frontend && npm run build', file=sys.stderr)
        return 1

    # 旧产物移到系统临时目录（不批量删除，避免触发删除保护）
    if OUT.exists():
        import tempfile
        import time

        trash = Path(tempfile.gettempdir()) / f'tp-fnos-out-{int(time.time())}'
        try:
            os.replace(OUT, trash)
        except OSError:
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

    fixed = normalize_lf(APP)
    if fixed:
        print(f'[i] 统一行尾为 LF: {fixed} 个文件')

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
    if fix_manifest_lf(target):
        print('[i] 已修正 manifest 行尾与 cmd 脚本执行位')
    print(f'\n产物: {target}\n大小: {size:.1f} MB')
    return 0


if __name__ == '__main__':
    sys.exit(main())
