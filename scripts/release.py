"""一键发版：改版本号 → 打 tag → 推送 → 等 CI 出镜像 → 打包 fpk → 建 Release。

用法：
    python scripts/release.py 2.0.1
    python scripts/release.py 2.0.1 --skip-ci     # 不等 CI（镜像稍后自己看）
    python scripts/release.py 2.0.1 --dry-run     # 只打印将要做什么

约定：
    - 版本号 SemVer，tag 为 vX.Y.Z，镜像 tag 同名且**不可变**
    - 必须在 main 分支、工作区干净时执行
    - CI（.github/workflows/docker-image.yml）由 tag 触发，构建 X.Y.Z 与 latest
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SSH_URL = "ssh://git@ssh.github.com:443/Vita0519/tmp-preview-deploy.git"
SSH_KEY = "C:/Users/15457/.ssh/id_ed25519_github"
REPO = "Vita0519/tmp-preview-deploy"
GH_API = "https://api.github.com"
SSH_ENV = {
    "GIT_SSH_COMMAND": f"ssh -i {SSH_KEY} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
}


def push_target() -> tuple[str, dict | None]:
    """git 推送目标：作者本机的专用 SSH key 优先，没有就回退 origin（https 凭据）。"""
    if Path(SSH_KEY).exists():
        return SSH_URL, SSH_ENV
    return "origin", None


def run(cmd, cwd=None, env=None, check=True):
    e = None
    if env:
        import os

        e = {**os.environ, **env}
    r = subprocess.run(cmd, cwd=cwd or ROOT, capture_output=True, text=True, env=e)
    if check and r.returncode != 0:
        raise SystemExit(f"命令失败: {' '.join(cmd)}\n{r.stdout}\n{r.stderr}")
    return r.stdout.strip()


_TOKEN = None


def token() -> str:
    """GitHub token。优先环境变量，其次 git credential。

    没有 TTY 时 `git credential fill` 会挂在系统凭据弹窗上（GCM 不会自己返回），
    所以在非交互环境里必须先备好 GH_TOKEN，否则这里 15 秒后直接报错，
    而不是让整个发版流程僵在那里。取一次就缓存，免得每次 API 调用都重试。
    """
    global _TOKEN
    if _TOKEN:
        return _TOKEN

    import os

    env = (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    if env:
        _TOKEN = env
        return _TOKEN

    try:
        out = subprocess.run(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n\n",
            capture_output=True, text=True, cwd=ROOT, timeout=15,
        ).stdout
    except subprocess.TimeoutExpired:
        raise SystemExit(
            "取不到 GitHub token：git credential 在无交互环境会挂住。\n"
            "先设置环境变量再跑，例如 PowerShell: $env:GH_TOKEN='gho_...'"
        )

    _TOKEN = dict(l.split("=", 1) for l in out.strip().splitlines() if "=" in l).get("password", "")
    return _TOKEN


def api(method, path, payload=None, timeout=180):
    args = ["curl", "--noproxy", "*", "-sS", "--max-time", str(timeout),
            "-X", method, "-H", f"Authorization: Bearer {token()}",
            "-H", "Accept: application/vnd.github+json",
            "-H", "Content-Type: application/json"]
    if payload is not None:
        args += ["--data-binary", json.dumps(payload, ensure_ascii=False)]
    args.append(GH_API + path)
    r = subprocess.run(args, capture_output=True, text=True)
    try:
        return json.loads(r.stdout or "{}")
    except json.JSONDecodeError:
        return {"raw": r.stdout[:400], "stderr": r.stderr[:200]}


def upload_asset(release_id: int, path: Path, name: str | None = None) -> dict:
    args = ["curl", "--noproxy", "*", "-sS", "--max-time", "300", "-X", "POST",
            "-H", f"Authorization: Bearer {token()}",
            "-H", "Accept: application/vnd.github+json",
            "-H", "Content-Type: application/octet-stream",
            "--data-binary", f"@{path}",
            f"https://uploads.github.com/repos/{REPO}/releases/{release_id}/assets?name={name or path.name}"]
    r = subprocess.run(args, capture_output=True, text=True)
    try:
        return json.loads(r.stdout or "{}")
    except json.JSONDecodeError:
        return {"raw": r.stdout[:300]}


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if not args:
        print(__doc__)
        return 1
    ver = args[0].lstrip("v")
    if not re.fullmatch(r"\d+\.\d+\.\d+", ver):
        print(f"版本号必须是 X.Y.Z：{ver}")
        return 1
    tag = f"v{ver}"
    dry = "--dry-run" in flags

    # ---- 前置检查 ----
    branch = run(["git", "branch", "--show-current"])
    if branch != "main":
        print(f"只能在 main 发版，当前是 {branch}")
        return 1
    dirty = run(["git", "status", "--porcelain"])
    if dirty:
        print("工作区不干净，先提交或清理：\n" + dirty)
        return 1
    if run(["git", "tag", "-l", tag]):
        print(f"本地已有 tag {tag}，版本不可复用")
        return 1
    target, target_env = push_target()
    remote_tags = run(["git", "ls-remote", "--tags", target], env=target_env)
    if f"refs/tags/{tag}" in remote_tags:
        print(f"远端已有 tag {tag}")
        return 1

    prev = run(["git", "describe", "--tags", "--abbrev=0"]) if run(["git", "tag"]) else ""
    print(f"发版 {prev or '(首次)'} → {tag}")

    if dry:
        print("[dry-run] 将执行：写 VERSION、sync_version、commit、tag、push、等 CI、打包 fpk、建 Release")
        return 0

    # ---- 改版本 + 提交 + 打 tag ----
    (ROOT / "VERSION").write_text(ver + "\n", encoding="utf-8")
    run([sys.executable, "scripts/sync_version.py"])
    run(["git", "add", "VERSION", "frontend/package.json", "docker-compose.yml", ".env.example",
         "packaging/fnos/template", ".github/workflows"])
    run(["git", "commit", "-m", f"chore(release): {tag}"])
    run(["git", "tag", "-a", tag, "-m", f"{tag}"])
    run(["git", "push", target, "main:main"], env=target_env)
    run(["git", "push", target, tag], env=target_env)
    print(f"✅ 已推送 {tag}")

    # ---- 等 CI 出镜像 ----
    run_ok = True
    if "--skip-ci" not in flags:
        print("等待 CI 构建镜像…")
        run_ok = False
        for _ in range(45):
            runs = api("GET", f"/repos/{REPO}/actions/runs?per_page=10").get("workflow_runs", [])
            hit = next((r for r in runs if r.get("head_branch") == tag), None)
            if hit and hit["status"] == "completed":
                run_ok = hit["conclusion"] == "success"
                print(f"CI {hit['status']} / {hit['conclusion']}（run {hit['id']}）")
                break
            time.sleep(20)
        if not run_ok:
            print("⚠️ CI 未成功，Release 仍会创建，镜像稍后手动补构建")

    # ---- 打包 fpk ----
    print("打包飞牛 fpk…")
    run([sys.executable, "packaging/fnos/build.py"])
    fpk = ROOT / "packaging" / "fnos" / "out" / "tmp-preview.fpk"
    if not fpk.exists():
        print("fpk 未生成")
        return 1

    # ---- 建 Release ----
    log = ""
    if prev:
        # 排除发版自身的 chore(release) 提交，否则「变更」里会出现「- chore(release): vX.Y.Z」
        log = run(["git", "log", f"{prev}..HEAD", "--pretty=- %s", "--no-merges",
                   "--invert-grep", "--grep=^chore(release)"])
    body = "\n".join([
        f"## {tag}",
        "",
        "### 镜像",
        "```bash",
        f"docker pull ghcr.io/vita0519/tmp-preview:{ver}",
        "```",
        "固定版本可复现；`latest` 同步指向本版本。",
        "",
        "### 飞牛 fnOS 安装包",
        f"`tmp-preview.fpk`（见下方 Assets），安装后访问 `http://<NAS 地址>:519`。",
        "安装前确认 NAS 能拉镜像，或解包用 `docker/build_image.sh` 本地构建。",
        "",
        "### 变更",
        log or "- 首个正式版",
        "",
        "### 许可",
        "AGPL-3.0-only，再分发或对外提供服务须保留出处与署名（见 NOTICE）。",
    ])
    rel = api("POST", f"/repos/{REPO}/releases", {
        "tag_name": tag, "name": tag, "body": body, "draft": False, "prerelease": False,
    })
    if "id" not in rel:
        print("创建 Release 失败:", rel)
        return 1
    rid = rel["id"]
    print(f"Release: {rel.get('html_url')}")

    for name in ("tmp-preview.fpk",):
        a = upload_asset(rid, fpk)
        print(f"  附件 {name}: {a.get('state') or a.get('message')}")
    compose = ROOT / "docker-compose.yml"
    if compose.exists():
        a = upload_asset(rid, compose)
        print(f"  附件 docker-compose.yml: {a.get('state') or a.get('message')}")
    envf = ROOT / ".env.example"
    if envf.exists():
        # GitHub 会把前导点改写成 default.，所以显式命名
        a = upload_asset(rid, envf, name="env.example")
        print(f"  附件 env.example: {a.get('state') or a.get('message')}")

    print(f"\n✅ {tag} 完成：{rel.get('html_url')}")
    if not run_ok:
        print("提醒：CI 未成功，需手动触发工作流补镜像")
    return 0


if __name__ == "__main__":
    sys.exit(main())
