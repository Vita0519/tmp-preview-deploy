# tmp-preview · 临时预览站（自托管版）

把任意本地目录（静态站 / HTML 单页 / WebGL 作品 / 构建产物）**一键变成带到期时间的预览链接**：
默认按可见性给不同寿命（门户 6 小时 / 持链接 12 小时 / 私有永久，可改），多成员共享同一套服务，
管理员能看到全部项目。

从 Cloudflare Workers + KV 迁移而来（旧实现保留在 [`legacy/cloudflare/`](legacy/cloudflare/)），
现在跑在自己的机器上：**FastAPI + SQLite + 本地磁盘 + Vue 3**，一个容器，`docker compose up` 即用。

```
浏览器 ──┬── /v/<slug>          访客预览外壳（倒计时 + 下载）
         ├── /p/<slug>/...      项目本体（原始文件直出，支持 SPA 回退）
         ├── /download/<slug>   zip 下载（可选开放）
         └── /                  控制台（Vue 3 SPA）
                    │
              FastAPI (uvicorn) ── SQLite(WAL) + /data 磁盘
```

## 特性

- **多 Agent 共享**：每个成员一把 API Key，上传的项目自带归属，互相看不到；管理员看全部。**一个账号只绑一个 Agent**——成员页可给 Key 标「绑定给谁」，并显示尾号、最近使用时间与累计调用次数，共用了就能看出来。
- **三种角色**：`viewer` 只能浏览访客门户、`publisher` 能上传并管理自己的项目、`admin` 管全部成员与设置；管理员在成员页直接下拉改角色，改完立即生效（不能改自己，也不会把最后一个管理员降级）。
- **权限清晰**：项目可见性分「门户可见 / 持链接可见 / 仅自己」，三档各自一套默认时长。**注意「门户」和「持链接」在权限上完全一样**（有 URL 就能看），区别只是会不会被列进门户；「仅自己」不是登录就能看，而是只有作者本人或管理员能看。详见 [docs/visibility.md](docs/visibility.md)。
- **批量改可见性**：项目页勾选若干条后，底部工具条可直接「门户可见 / 持链接 / 仅自己」一键切换，返回里会单独报出「已到期、需先续期」的条数。
- **Agent 侧真能动手**：`cli/agentctl.py` 是可执行的单文件客户端（`login / whoami / health / deploy / link / ls / show / set / extend / rm / bulk / stats / members / selfcheck`），部署完自动探活，直接告诉你「预览地址 + HTTP 200」；`--json` 时 stdout 只有一行 JSON，好接上游程序。
- **并发安全**：多个 agent 同时上传、同一 slug 被 6 路同时覆盖、混合读写都不会写串也不会 500——slug 级锁 + 每次上传独立临时目录 + 原子替换 + Windows 文件句柄重试。删除时若文件被占用，记录照样删掉，残留目录交给孤儿清理收尾。
- **项目自带图标**：预览页优先用项目自带的 `favicon.ico / favicon.svg / favicon.png / apple-touch-icon.png`，没有才退回站点默认图标，标签页不会一水的空白页。
- **项目名不重名**：同一个成员名下不允许两个同名项目（忽略大小写与首尾空格），新建、登记外链、改名三条路径都会拦，撞上返回 409 并点名占用的 slug。覆盖更新同一个 slug 不算冲突，跨成员同名互不影响。
- **失效链接回门户**：链接过期、被删除、改私有或根本不存在时，`/v/` 一律 `302` 回门户首页并给一条「你打开的链接已失效」提示——**不再原地渲染一个「项目已到期」的破页面**。在 iframe 里被引用时返回的是能 `window.top` 跳走的失效页，顶层窗口直接被带走；css/js/图片之类的子资源请求则静默 404，不会把资源跳成一张 HTML。门户本身要登录时继续 302 到 `/login`，所以**看 URL 也猜不出项目在不在**。
- **外链当短链用**：`kind=link` 的项目（Figma / 在线文档 / 别人的站）分享出去的是本站的 `/v/<slug>`，点开先记一次访问、再 302 到源站——**一次跳转，没有中间页，也不套 iframe 空壳**，但访问数有了，门户圆环不再是死的 0。
- **主题色可换**：设置页一个调色盘（8 个预设 + 取色器 + hex 输入），选完即时预览、保存后全站生效。控制台、访客门户、预览页、错误页、浏览器 `theme-color` 共用同一个主色，hover / 浅底 / 描边 / 渐变深色都由主色自动派生，不用一格一格调。
- **门户 RSS**：`/rss.xml`（`/feed.xml` 同）输出最近 50 个门户可见且未过期的项目，带标题、绝对链接、创建时间、简介与标签；门户 `<head>` 里有 `alternate` 自动发现，入口放在页脚右侧（不占顶栏，也不跟「进入控制台」抢位置）。门户不公开且访客未登录时返回 404，不会把 HTML 登录页塞给阅读器。
- **入口规则简单**：**单个 HTML 不管叫 index.html 还是 report.html 都能直接打开**（单个 PDF/图片同理）；**多文件项目必须有根目录 `index.html`**，没有就上传时 422 直接说清楚，不会传上去才发现是一团空白。
- **到期自动化**：到期后可选「停止访问保留文件」或「连同文件删除」，后台每 60s 巡检；站点级可设默认策略。
- **访客门户** `/portal`：标题＋筛选区整体吸顶（滚动时标签以上不动），提供卡片/列表两种视图（记在本地），卡片右上角圆环显示访问量、底部是实时倒计时与进度条；支持按类型/标签/关键词筛选，按创建、到期、访问、名称排序。每张卡片（含列表行）右上角有**快捷复制**按钮，一点即复制完整直链，按钮自分绿打勾并冒出「已复制」气泡，1.6 秒后自动复原。
- **作者名片**：设置里填显示名、一句话介绍和几个链接（GitHub / 邮箱 / 抖音 / 博客 / X / B站 / 知乎 / RSS / 自定义），门户顶部就多出一条作者名片，图标 + 标签，移动端自动收成图标。出厂默认显示名 `vita`、介绍「互联网混子」，**不含任何真实个人信息**；改 `.env` 的 `AUTHOR_NAME` / `AUTHOR_BIO` 或直接在设置页改。
- **站点图标**：一枚「沙漏」标记（限时可用 = 临时预览），SVG + ICO + PNG 全尺寸齐全，门户、控制台、访客预览栏、错误页统一使用；项目自带的 favicon 仍然优先。位图由 `tools/gen_icons.py` 从同一份 SVG 生成。想换成自己的图标：设置页 →「站点图标」→ 上传（`png / svg / ico / jpg / webp`，≤512KB），顶栏、门户、manifest、手机主屏图标一起换；点「恢复默认」随时退回沙漏。
- **访问统计**：只统计项目首页文档访问，内存累加 + 3s 批量落库（不牺牲响应速度），带 14 天趋势。
- **管理台**：按成员 / 类型 / 可见性 / 状态 / 标签筛选，按访问、创建、更新、到期、体积排序，表格直接展示可见性列，抽屉里一键续期、改标签、开关下载。
- **轻**：前端 gzip 后约 65KB；后端只依赖 fastapi / uvicorn / python-multipart，无 ORM、无 Redis。
- **迁移友好**：自带 Cloudflare KV → 本地的搬运脚本，保留原 slug、创建时间、到期时间与访问数。

## 资源占用

单进程、无 Redis、无 ORM，整套东西的体量基本就是「一个 Python 进程 + 一块磁盘」。

| 项目 | 实测 / 估算 | 说明 |
|---|---|---|
| 镜像体积 | 约 **160 MB**（拉取压缩后 ~65 MB） | `python:3.12-slim` 基础镜像 ~130 MB，运行时依赖约 22 MB，应用与前端产物不到 1 MB |
| 内存（空载） | **35 MB**（Private Bytes） | 启动完成、无请求时 |
| 内存（12 并发压测后） | **49 MB** | 900 个混合请求跑完，涨完就稳住，不随请求数线性增长 |
| 打包大文件时的峰值 | **+0.2 MB** | 80 MB 文件按需打 zip，全程流式，不把文件读进内存 |
| 上传时的内存 | 基本不涨 | 按 512 KB 分块写盘 |
| CPU | 单核足够 | `--workers 1`；压测约 50 req/s，瓶颈在单进程 + 同步 SQLite，不在资源 |
| 磁盘（数据卷） | 上传总量 × 约 2 | 项目文件 + 按需生成的 zip 缓存（开了下载的项目多占一份） |
| 数据库 | 10 个项目约 **230 KB** | SQLite + WAL，千级项目也就几 MB |

**建议配置**：`1C / 512MB / 5GB` 能跑起来；`2C / 1GB` 更从容（构建镜像时 npm install 会吃点内存）。
磁盘按「预计上传总量的 2 倍」留，这是唯一会真正吃紧的资源。

需要限制一下的话，`docker-compose.yml` 里加：

```yaml
    deploy:
      resources:
        limits: { cpus: "1.0", memory: 512M }
```

> 内存上限别压到 128M 以下：容器里的 Python 解释器 + 依赖本身就要几十 MB，
> Linux 下 RSS 通常在 45–60 MB，留 256M 才不会在打包/并发时被 OOM kill。

## 快速开始

```bash
cp .env.example .env           # 改 ADMIN_PASSWORD、SITE_TITLE、PORT
docker compose up -d --build    # 首次构建约 1-2 分钟
docker compose logs -f preview  # 若未指定密码，日志里会打印初始管理员密码
```

打开 `http://<机器IP>:8080`，用 `.env` 里的 `ADMIN_USERNAME` / `ADMIN_PASSWORD` 登录。

> 没装 Docker？本地也能跑：
> `python -m venv .venv && .venv/Scripts/pip install -r backend/requirements.txt`（Linux 用 `.venv/bin/pip`），
> `cd frontend && npm i && npm run build`，然后
> `DATA_DIR=./data .venv/Scripts/python -m uvicorn app.main:app --app-dir backend --port 8080`。

## 给成员（Agent）用

命令行是**真能增删改查**的，不是说明书。单文件、只用标准库，拷到任何有 Python 3.10+ 的机器上就能跑：

```bash
# 1) 登录一次，Key 存到 ~/.config/tmp-preview/config.json（0600）
python cli/agentctl.py login --url http://<站点地址>:8080 --username alice --password xxx
python cli/agentctl.py whoami          # 我是谁、什么角色、能干什么

# 2) 部署：上传完直接探活，返回可点开的预览地址 + HTTP 状态
python cli/agentctl.py deploy ./dist --title "落地页 v3" --tags "前端,v3" --ttl 24
#   → 预览地址  http://.../v/landing-v3
#     已验证    HTTP 200

# 3) 日常
python cli/agentctl.py ls --status online --sort views
python cli/agentctl.py ls --tag 前端 --visibility portal
python cli/agentctl.py show landing-v3
python cli/agentctl.py set landing-v3 --visibility private   # 门户可见 / 持链接 / 仅自己
python cli/agentctl.py extend landing-v3 48                  # 或 --forever
python cli/agentctl.py rm landing-v3

# 4) 批量 / 统计 / 管理员
python cli/agentctl.py bulk --action visibility --visibility portal --slugs a,b,c
python cli/agentctl.py bulk --action delete --slugs a,b,c --yes
python cli/agentctl.py stats --days 14
python cli/agentctl.py members list
python cli/agentctl.py members set alice --label "claude-code@笔记本" --rotate-key

# 5) 自检：用当前身份真跑一遍 建→探活→改私有(打不开)→改回(200)→续期→删除→链接失效
python cli/agentctl.py selfcheck
```

加 `--json` 时 stdout 只有一行 JSON（给上游程序读），人读的提示全部走 stderr，两者不混。
完整能力边界与调用示例见 [skills/tmp-preview-agent/SKILL.md](skills/tmp-preview-agent/SKILL.md)。

机器调用也可以直接走 API：

```bash
curl -X POST http://127.0.0.1:8080/api/projects \
  -H "Authorization: Bearer pv_xxx" \
  -F "slug=demo" -F "title=演示" -F "tags=前端,验收" -F "hours=24" \
  -F "files=@dist/index.html;filename=index.html" \
  -F "files=@dist/assets/app.js;filename=assets/app.js"
```

## 从 Cloudflare 迁到本地

```bash
docker compose stop            # 先停服务，避免与后台任务抢写

export CF_API_TOKEN=xxx        # 只需 Workers KV 读取权限
export CF_ACCOUNT_ID=xxx
export CF_KV_NAMESPACE_ID=xxx

python migrate/from_cloudflare.py --dry-run   # 先看清单
python migrate/from_cloudflare.py --agent admin
docker compose start
```

迁移会保留：slug、标题、说明、文件内容、zip、创建/更新时间、到期时间、到期策略、访问次数。
详见 [docs/migration.md](docs/migration.md)。

## 目录结构

```
backend/app/
  main.py            FastAPI 入口（API + 访客页 + SPA 托管）
  config.py          全部配置走环境变量
  db.py              SQLite schema / 连接 / 标签写入
  security.py        PBKDF2 密码、会话 Cookie、API Key
  storage.py         文件落盘、路径穿越校验、按需打包 zip
  views.py           访问计数缓冲与批量落库
  cleanup.py         到期巡检 + 计数 flush 后台任务
  serializers.py     行 → API 结构（含倒计时派生字段）
  pages.py           访客预览外壳 / 门户 / 错误页（服务端渲染）
  routers/           auth · projects · agents · settings · public
frontend/src/        Vue 3 控制台（零 UI 框架，手写设计系统）
frontend/public/     站点图标与 manifest（favicon.svg 是唯一矢量源）
cli/agentctl.py      成员侧命令行入口（兼容壳，实现见下）
skills/tmp-preview-agent/  Agent 侧技能包：scripts/agentctl.py 是真实实现（单文件、仅标准库）+ SKILL.md 权限边界
migrate/             Cloudflare KV → 本地
tools/               gen_icons.py（从 favicon.svg 生成 ICO/PNG）、push_api.py（推 GitHub）
tests/               冒烟测试 / 截图脚本 / 演示数据
legacy/cloudflare/   旧版 Worker 实现（仅存档，不再维护）
docs/                架构、接口、可见性、迁移说明
```

## 常用运维

| 事项 | 做法 |
|---|---|
| 看日志 | `docker compose logs -f --tail=100 preview` |
| 备份 | 停服后打包 `./data`（SQLite + 项目文件 + zip）；或热备 `sqlite3 data/db.sqlite3 ".backup backup.db"` |
| 升级 | `git pull && docker compose up -d --build`（数据在 `./data`，不受影响） |
| 改端口 | `.env` 里 `PORT=9000` |
| 反向代理 | 交给 Nginx/Caddy 终止 TLS，转发到 `127.0.0.1:8080`，并把 `COOKIE_SECURE=1` |
| 单进程 | 计数与清理是进程内任务，**保持 1 个 worker**；要横向扩展需改用外置计数/锁 |
| 并发上限 | 多个 agent 同时上传是安全的（slug 级锁 + 原子替换），但同一个 slug 同时写只有最后一次生效；打满约 18 路并发上传时单次约 3.3s，再高建议排队 |
| 清残留目录 | 删除时文件被占用会留下目录，`data/projects/` 下无人认领的目录会在后台约 30 分钟内自动清掉；要立刻清就重启一次（启动时会扫 `.tmp-*` / `.old-*`） |

## 自检与测试

全部测试都是「打真服务的黑盒脚本」，跑之前先起好后端（Playwright 那几项还要起前端 `npm run dev`）：

```bash
python tests/smoke_test.py       --url http://127.0.0.1:8000   # 26 项：上传/列表/改属性/批量/下载/删除/成员
python tests/check_ttl.py        --url http://127.0.0.1:8000   # 16 项：三档可见性各自的默认时长与到期策略
python tests/check_roles.py      --url http://127.0.0.1:8000   # 26 项：三档角色的接口权限与页面权限
python tests/check_migrate.py    --url http://127.0.0.1:8000   # 19 项：老库加列迁移、悬空外键自愈
python tests/check_portal.py     --url http://127.0.0.1:8000   # 41 项：门户页结构、吸顶、卡片/列表、复制按钮
python tests/check_visibility.py --url http://127.0.0.1:8000   # 41 项：三档可见性的真实访问结果 + Key 使用痕迹
python tests/check_cli.py        --url http://127.0.0.1:8000   # 57 项：CLI 真子进程跑一遍所有命令与越权
python tests/check_concurrency.py --url http://127.0.0.1:8000 # 20 项：6 agent 并发部署 / 同 slug 抢占 / 混合读写
python tests/check_copy.py       --url http://127.0.0.1:8000   # 26 项：复制按钮的层级、剪贴板内容、移动端、无溢出
python tests/check_title.py      --url http://127.0.0.1:8000   # 22 项：同一成员重名拦截（新建/外链/改名/跨成员）
python tests/check_gone.py       --url http://127.0.0.1:8000   # 34 项：失效链接一律 302 回门户，不泄露项目是否存在
python tests/check_entry.py      --url http://127.0.0.1:8000   # 23 项：单文件任意名 / 多文件必须有 index.html / 覆盖上传
python tests/check_rss.py        --url http://127.0.0.1:8000   # 24 项：RSS 结构、绝对链接、门户不公开时的 404、页脚入口
python tests/check_theme.py      --url http://127.0.0.1:8000   # 48 项：主色派生、非法值回落、站点图标上传与 /site-icon
```

## 安全约定

- 密钥只在 `.env` 与环境变量里，不写入仓库；
- 项目文件路径全部做穿越校验，只有 `data/projects/<slug>/` 下的文件可读；
- 上传/管理接口都要认证，`publisher` 只能操作自己的项目，`viewer` 连项目列表都读不到；
- 访客页与项目响应均带 `X-Robots-Tag: noindex, nofollow`。

## 接口

完整列表见 [docs/api.md](docs/api.md)，架构与设计取舍见 [docs/architecture.md](docs/architecture.md)。
