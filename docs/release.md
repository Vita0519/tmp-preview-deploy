# 发版流程

版本号规则：`MAJOR.MINOR.PATCH`（SemVer）。**tag 一旦推送就不可变**，镜像 tag 与之一一对应。

| 改动性质 | 升哪一位 | 例子 |
|---|---|---|
| 不兼容的接口 / 数据结构变更 | MAJOR | `2.0.0 → 3.0.0` |
| 新增功能，向后兼容 | MINOR | `2.0.0 → 2.1.0` |
| 修 bug、文档、界面微调 | PATCH | `2.0.0 → 2.0.1` |

## 一、一键发版（推荐）

```bash
git checkout main && git pull
python scripts/release.py 2.0.1
```

脚本会依次做：

1. 校验：在 `main`、工作区干净、本地与远端都没有该 tag
2. 写 `VERSION`，跑 `scripts/sync_version.py` 同步 `package.json`、fnOS `manifest`、
   两处 `compose`、`.env.example`、CI 默认值
3. `chore(release): v2.0.1` 提交 → 打 annotated tag → 推送 main 与 tag
4. 等 GitHub Actions 构建 `ghcr.io/vita0519/tmp-preview:2.0.1` 与 `latest`
5. 打包 `tmp-preview.fpk`（版本号已同步）
6. 创建 Release，挂上 `tmp-preview.fpk`、`docker-compose.yml`、`.env.example`

参数：

```bash
python scripts/release.py 2.0.1 --dry-run   # 只检查，不动仓库
python scripts/release.py 2.0.1 --skip-ci   # 不等 CI，镜像稍后手动补
```

## 二、手工兜底

脚本跑不通时按同样顺序手工执行：

```bash
echo 2.0.1 > VERSION
python scripts/sync_version.py

git add -A && git commit -m "chore(release): v2.0.1"
git tag -a v2.0.1 -m v2.0.1
git push origin main && git push origin v2.0.1

python packaging/fnos/build.py            # 产出 packaging/fnos/out/tmp-preview.fpk
# 然后在 GitHub 上按 tag 建 Release，上传 fpk
```

CI 没触发时，可在 Actions 页面手动 `Run workflow`（会读仓库里的 `VERSION`）。

## 三、发布检查清单

- [ ] `git status` 干净，本地与远端没有同名 tag
- [ ] `VERSION`、`frontend/package.json`、`packaging/fnos/template/manifest` 版本一致
      （`sync_version.py` 负责，别手改）
- [ ] CI 绿色，`ghcr.io/vita0519/tmp-preview:X.Y.Z` 可拉取
- [ ] fpk 包内 `manifest` 的 `version` 与本次一致，`desc`/`maintainer` 未回退
- [ ] Release 附件含 `tmp-preview.fpk`
- [ ] README 的安装说明没有写死过期版本号（fpk 用 `releases/latest/download/...`）

## 四、回滚

```bash
# 部署侧：退到上一个固定版本
IMAGE_TAG=2.0.0 docker compose pull && IMAGE_TAG=2.0.0 docker compose up -d

# 代码侧：tag 不要删，Release 不要删，重新发一个 PATCH 版本修问题
```

不要复用或覆盖已发布的 tag——那是所有可复现性的基础。

## 五、镜像可见性

仓库是私有的，ghcr 的 package 默认也私有。首次发版后去
`https://github.com/users/Vita0519/packages/container/tmp-preview/settings`
把可见性改成 **Public**，否则外部部署拉取会 `denied`。
