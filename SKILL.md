---
name: tmp-preview-deploy
description: 把本地目录（静态站 / HTML / WebGL / 构建产物）一键部署成带到期时间的临时预览与下载站，默认按可见性给寿命（门户 6 小时 / 持链接 12 小时 / 私有永久，可配）。自托管版：Docker Compose 起一个 FastAPI + SQLite + 本地磁盘的服务，Vue 3 控制台，多 Agent 共用一套服务且各自只能看自己的项目，管理员可看全部并按成员/标签/类型筛选、按访问与时间排序。当用户说「部署预览」「临时部署」「分享给客户验收」「上传项目让人预览下载」「24 小时后自动删除的预览链接」「自建预览站」「迁移 Cloudflare 预览站到本地」「docker compose 部署预览服务」时使用。也用于管理成员与 API Key、续期、打标签、从 Cloudflare KV 迁移历史项目。
---

# tmp-preview-deploy（自托管版）

临时预览 / 下载站，跑在自己的机器上：**一个容器**（FastAPI 托管 API + 访客页 + Vue 控制台），
数据落在 `./data`（SQLite + 项目文件 + zip）。

## 关键路径

| 路径 | 用途 |
|---|---|
| `/` | 控制台（登录后） |
| `/v/<slug>` | 访客预览外壳：标题、实时倒计时、下载、复制链接、刷新；外链项目记一次访问后 302 到目标站，失效项目直接 302 回门户 |
| `/p/<slug>/...` | 项目原始文件（可直接嵌 iframe / 引用子资源） |
| `/download/<slug>` | zip 下载（项目开启后才有） |
| `/portal` | 门户列表（`PUBLIC_PORTAL=1` 才允许匿名） |
| `/rss.xml` | 门户 RSS（门户不公开且未登录时 404） |

## 入口文件规则

| 上传内容 | 结果 |
|---|---|
| 只有 1 个文件（任意名字、任意类型） | 就是入口，`report.html` / `menu.pdf` 都能直接打开 |
| 多个文件 + 根目录 `index.html`（或 `.htm`） | 用它当入口 |
| 多个文件 + 没有 `index.html` | **422 拒绝**，提示改名 / 拆成单文件 / 改用 zip 上传 |

## 起服务

```bash
cp .env.example .env          # 至少改 ADMIN_PASSWORD
docker compose up -d --build
docker compose logs -f preview   # 未配密码时日志里打印初始密码
```

首次启动自动建表并创建管理员。升级：`git pull && docker compose up -d --build`。

## 部署一个项目

```bash
python cli/agentctl.py login --url http://<host>:8080 --username alice --password xxx
python cli/agentctl.py whoami                                  # 我是谁、什么角色、能干什么
python cli/agentctl.py deploy ./dist --title "落地页 v3" --tags "前端,v3" --ttl 24
python cli/agentctl.py deploy ./dist --forever --download      # 永久 + 开放下载
python cli/agentctl.py deploy ./build.zip --zip                # 只做下载包
python cli/agentctl.py selfcheck                               # 建→探活→改私有→改回→续期→删除
```

`deploy` 传完会**自己去请求一次**这个地址，返回里带 `preview_url` 与 `http_status`
（`--no-verify` 可跳过）。`--json` 时 stdout 只有一行 JSON，退出码 0/1。

`--visibility` 三档：`link`（默认，持链接可见）、`portal`（进门户列表）、`private`（仅自己）。
`--expire-action` 两档：`block`（默认，到期停访留文件）、`delete`（到期删文件）。

同一成员名下**项目名不能重复**（忽略大小写/首尾空格），撞车返回 409 并点名占用的 slug；
覆盖更新同一个 slug 不算冲突，跨成员同名互不影响。

## 管理

```bash
python cli/agentctl.py ls --status online --sort views
python cli/agentctl.py show <slug>
python cli/agentctl.py set <slug> --visibility private      # 也可 --ttl / --forever / --tags / --download
python cli/agentctl.py extend <slug> 48                     # 续 48 小时
python cli/agentctl.py extend <slug> --forever              # 转永久
python cli/agentctl.py bulk --action visibility --visibility portal --slugs a,b,c
python cli/agentctl.py stats --days 14
python cli/agentctl.py members set alice --label "claude-code@笔记本" --rotate-key
python cli/agentctl.py rm <slug>
```

浏览器控制台还能做：按成员/标签/类型/可见性/状态筛选，按访问、创建、更新、到期、体积排序，
勾选后一键批量改可见性/续期/转永久/开放下载/删除，抽屉里看文件清单与 14 天访问趋势。

## 访客门户

- `/portal` 顶部（标题/作者名片/筛选/标签）吸顶，滚动时不动。
- 支持卡片 / 列表两种视图，选择记在 localStorage；右上角圆环是访问量，底部是倒计时。
- 每张卡片和每个列表行右上角都有快捷复制按钮：点一下复制 `origin + /v/<slug>`，
  按钮变绿打勾并弹出「已复制」气泡，1.6s 后复原；失败显示红色「复制失败」。
  按钮层级高于整卡的覆盖式链接（`.hit`），点击不会跳转。
- 支持按类型、标签、关键词筛选，按创建/到期/访问/名称排序。

## 成员与权限

- 管理员（`role=admin`）：全部项目 + 成员管理 + 站点设置。
- 发布者（`role=publisher`）：只有自己的项目；`/api/agents`、`/api/settings` 返回 403。
- 仅门户（`role=viewer`）：连 `/api/projects` 都是 403，控制台只显示一条提示 + 门户入口，
  适合发给只需要看预览的人。
- 角色在「成员」页的下拉里随时改，改完对已有会话立即生效；不能改自己的角色，
  也不会把最后一个管理员降级。老库里的 `role=agent` 启动时自动迁移成 `publisher`。
- 每个成员一把 `pv_...` API Key，可在「成员」页轮换；命令行 `login` 后保存在
  `%APPDATA%\tmp-preview\config.json`（Linux/macOS: `~/.config/tmp-preview/config.json`）。
- **一个账号只绑一个 Agent**：`users.api_key` 有 UNIQUE 约束；成员页每行可编辑
  「绑定 Agent」（`key_label`），并显示尾号、`key_last_used_at`、`key_uses`。
  轮换会刷新签发时间并把计数归零。注意账号密码可用 `POST /api/token` 换出同一把 Key，
  所以密码也只能给这一个 Agent。

## 可见性三档

`portal` / `link` / `private` 的完整判定表见 [docs/visibility.md](docs/visibility.md)。
速记：**门户与持链接在权限上完全一样（有 URL 就能看），只是门不进门户列表；
私有不是「登录就能看」，而是「只有作者本人或管理员能看」。**

## Agent 侧技能包

给「用一把 Key 管理项目」的 Agent 用的技能包在 [skills/tmp-preview-agent/](skills/tmp-preview-agent/)：
`SKILL.md` 是权限边界与调用示例，**`scripts/agentctl.py` 是可直接执行的客户端**（单文件、仅标准库，
`cli/agentctl.py` 是同实现的入口壳）。整包交给 Agent，它就能自己建/改/删/查。

## 从 Cloudflare KV 迁移

```bash
docker compose stop
export CF_API_TOKEN=xxx CF_ACCOUNT_ID=xxx CF_KV_NAMESPACE_ID=xxx
python migrate/from_cloudflare.py --dry-run
python migrate/from_cloudflare.py --agent admin
docker compose start
```

保留 slug / 标题 / 文件 / zip / 创建与到期时间 / 访问数。细节见 `docs/migration.md`。

## 运维要点

- **保持 1 个 worker**：访问计数缓冲与到期巡检是进程内任务。
- 备份 = 打包 `./data`；热备用 `sqlite3 data/db.sqlite3 ".backup backup.db"`。
- 到期巡检每 60s；计数每 3s 落库，掉电最多丢 3 秒访问量。
- 日志：`docker compose logs -f --tail=100 preview`。
- **并发**：多 agent 同时上传安全（slug 级锁 + 每次上传独立临时目录 + 原子替换 + WinError 5/32 重试），
  同 slug 并发覆盖只有最后一次生效、不会写串。实测 18 路并发上传全 200，单次约 3.3s。
- **删除**：文件被占用时记录先删、目录留下，后台约 30 分钟内由孤儿清理收尾；启动时另清 `.tmp-*` / `.old-*`。
- **图标**：预览页优先用项目自带的 `favicon.ico/svg/png/apple-touch-icon.png`，否则退回站点图标。

## 自检

```bash
python tests/smoke_test.py       --url http://127.0.0.1:8000   # 26 项端到端
python tests/check_ttl.py        --url http://127.0.0.1:8000   # 16 项：三档默认时长与到期策略
python tests/check_roles.py      --url http://127.0.0.1:8000   # 26 项：三档角色接口/页面权限
python tests/check_migrate.py    --url http://127.0.0.1:8000   # 19 项：加列迁移、悬空外键自愈
python tests/check_portal.py     --url http://127.0.0.1:8000   # 41 项门户结构回归
python tests/check_visibility.py --url http://127.0.0.1:8000   # 41 项：三档可见性 + 批量切换 + Key 绑定
python tests/check_cli.py        --url http://127.0.0.1:8000   # 57 项：CLI 全命令 + 越权
python tests/check_concurrency.py --url http://127.0.0.1:8000  # 20 项：6 agent 并发 / 同 slug 抢占
python tests/check_copy.py       --url http://127.0.0.1:8000   # 26 项复制按钮（需 chrome）
python tests/check_title.py      --url http://127.0.0.1:8000   # 22 项：同一成员重名拦截
```
