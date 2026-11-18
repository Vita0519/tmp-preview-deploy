# tmp-preview · 临时预览站

把任意本地目录（静态站 / 单页 HTML / WebGL 作品 / 构建产物）**一键变成带到期时间的预览链接**。
按可见性给寿命（门户 6 小时 / 持链接 12 小时 / 私有永久，可改），多成员共用一套服务，管理员看全部。

自托管：**FastAPI + SQLite + 本地磁盘 + Vue 3**，一个进程一块盘，拉一个镜像就能跑。
从 Cloudflare Workers + KV 迁移而来，旧实现留在 [`legacy/cloudflare/`](legacy/cloudflare/)。

[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-a8332b.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12-3c5f8f.svg)](backend/requirements.txt)
[![Docker](https://img.shields.io/badge/docker-compose-2f6f78.svg)](docker-compose.yml)

```
浏览器 ──┬── /v/<slug>          访客预览外壳（倒计时 + 下载）
         ├── /p/<slug>/...      项目本体（原始文件直出，支持 SPA 回退）
         ├── /download/<slug>   zip 下载（可选开放）
         └── /                  控制台（Vue 3 SPA）
                    │
              FastAPI (uvicorn) ── SQLite(WAL) + /data 磁盘
```

## 截图

| 控制台：项目、访问数据、分类筛选 | 项目详情：可见性、到期时间、文件清单 |
|---|---|
| ![控制台](docs/screenshots/console.png) | ![项目详情](docs/screenshots/project-detail.jpg) |

| 成员与 API Key：一个账号绑一个 Agent | 设置：主题、站点图标、默认时长 |
|---|---|
| ![成员](docs/screenshots/members.png) | ![设置](docs/screenshots/settings.png) |

| 访客门户：卡片墙，按分类直接挑 |
|---|
| ![门户](docs/screenshots/portal.png) |

## 安装

### 一、Docker Compose（推荐）

预构建镜像：`ghcr.io/vita0519/tmp-preview:2.0.0`

```bash
git clone https://github.com/Vita0519/tmp-preview-deploy.git
cd tmp-preview-deploy
cp .env.example .env            # 至少改 ADMIN_PASSWORD
docker compose up -d            # 直接拉镜像，不构建
docker compose logs -f preview  # 没设密码时，日志会打印初始管理员密码
```

打开 `http://<机器IP>:8080`，用 `.env` 里的 `ADMIN_USERNAME` / `ADMIN_PASSWORD` 登录。

> 拉不动 ghcr：把 compose 里的 `image:` 注释掉、取消 `build:` 段，改 `docker compose up -d --build` 本地构建。

### 二、飞牛 fnOS 应用包（.fpk）

下载：[**tmp-preview.fpk**](https://github.com/Vita0519/tmp-preview-deploy/releases/download/v2.0.0/tmp-preview.fpk)（v2.0.0，其他版本见 [Releases](https://github.com/Vita0519/tmp-preview-deploy/releases)）

1. 先在 NAS 上确认能拉到镜像：`docker pull ghcr.io/vita0519/tmp-preview:2.0.0`
   —— 私有仓库的包默认是私有的，需要先在 GitHub Packages 把它设为 Public，或 `docker login ghcr.io`
2. 应用中心 → 手动安装 → 选择 fpk
3. 向导里填管理员用户名 / 密码（留空则首启自动生成，见容器日志）
4. 启动后访问 `http://<NAS 地址>:519`（519 是特权端口，绑定失败就改 10519）

应用数据在 `${TRIM_PKGVAR}/data`，卸载不删除。打包与调试细节见 [packaging/fnos/README.md](packaging/fnos/README.md)。

### 三、从源码跑

<details>
<summary>没有 Docker，或想改代码</summary>

```bash
python -m venv .venv && .venv/Scripts/pip install -r backend/requirements.txt   # Linux/macOS: .venv/bin/pip
cd frontend && npm i && npm run build && cd ..
DATA_DIR=./data .venv/Scripts/python -m uvicorn app.main:app --app-dir backend --port 8080
```

</details>

## 公网访问

推荐 **Cloudflare Tunnel**：不需要公网 IP，也不用在路由器上开端口。

```bash
cloudflared tunnel run --protocol http2 --token <TOKEN>
```

`--protocol http2` 别省。家宽对 UDP 常有 QoS，默认的 QUIC 会让上传掉到几十 KB/s，表现就是大文件一直 524。

自建反向代理时：`client_max_body_size` 不小于上传上限，`proxy_read_timeout` / `proxy_send_timeout` ≥ 300s。

> Cloudflare 免费版对单次请求有 100 秒响应上限。按你的上行带宽，超过约 30–50MB 的单次上传会撞 524；
> 更大的文件建议先压成 zip，或在局域网内直连上传。

## 能力

### 项目与链接

| 能力 | 说明 |
|---|---|
| **入口规则简单** | 单个文件（`report.html` / `menu.pdf` 都行）直接当入口；多文件必须有根目录 `index.html`，没有就上传时 422 说清楚，不会传完才发现是白屏 |
| **到期自动化** | 每 60s 巡检；到期可选「停访留文件」或「连文件删除」，站点级可设默认策略，两种后果在界面上分得开 |
| **失效链接回门户** | 过期 / 删除 / 改私有 / 不存在，`/v/` 一律 302 回门户并提示「链接已失效」，不再原地渲染破页面；iframe 里引用时用能 `window.top` 跳走的失效页，子资源请求静默 404。看 URL 猜不出项目在不在 |
| **外链当短链** | `kind=link` 项目分享出去的是本站 `/v/<slug>`，点开记一次访问再 302 到源站——一次跳转、没有中间页、也不套 iframe，但访问数有了 |
| **下载** | 上传即可下载是默认；整包 zip 之外，抽屉里的文件清单每行都能单独下载（`/download/<slug>/<相对路径>`）。文件夹上传保留相对路径 |
| **项目名有规矩** | 最多 10 个中文字符（按显示宽度算），同成员名下不允许重名（忽略大小写/首尾空格），新建/外链/改名三条路都拦；改名不动链接 |
| **项目自带图标** | 预览页优先用项目里的 `favicon.ico/svg/png`、`apple-touch-icon.png`，没有才退回站点图标 |

### 权限与成员

| 能力 | 说明 |
|---|---|
| **三档可见性** | 门户可见 / 持链接可见 / 仅自己，各有一套默认时长。**门户与持链接在权限上完全一样**（有 URL 就能看），区别只是会不会被列进门户；「仅自己」不是登录就能看，而是只有作者本人或管理员能看。详见 [docs/visibility.md](docs/visibility.md) |
| **三种角色** | `viewer` 只能浏览门户、`publisher` 管自己的项目、`admin` 管全部。成员页下拉即改、立即生效，不能改自己，也不会把最后一个管理员降级 |
| **一账号 = 一 Agent = 一把 Key** | 每个成员一把 `pv_...`，成员页可给 Key 标「绑定给谁」并显示尾号、最近使用时间、累计次数——共用了能看出来 |
| **归属跟着人走** | 谁上传、谁挂的外链就归谁；删成员时项目记录一起清掉，不留 `owner` 为空的孤儿；历史遗留的无主项目自动收归最早的管理员 |
| **批量改可见性** | 勾选若干条后在底部工具条一键切换三档，返回里单独报出「已到期、需先续期」的条数 |

### 收藏夹与门户

| 能力 | 说明 |
|---|---|
| **收藏夹归类** | 左侧「分类 + 收藏夹」二合一：常驻按可见性统计的**全部 / 门户 / 持链接 / 仅自己 / 未归类**（三档之和 = 全部），再往下是两级收藏夹（夹 → 子夹）。点一下筛、勾选后可「移到收藏夹」，管理员能跨成员归类。删夹默认**只删壳**，项目退回未归类 |
| **两套筛选不打架** | 侧栏三档是「跳出收藏夹、看全站这一档」，工具栏的可见性下拉是「在当前夹里快筛」（选中夹时文案变「本夹全部可见性」），互不换范围；窄屏侧栏收起时再补一个归类下拉兜底 |
| **收藏夹归属可见** | 管理员视角下侧栏**按成员分组**（自己的组排最前，组头有成员色点、夹数、折叠箭头），右上角成员下拉可只看某个人——只收侧栏不换列表范围。夹里混了别人的项目时数字后补 `+N`（`39+1` = 39 个里有 1 个不是夹主的） |
| **书签导入 / 导出** | 直接吃 Chrome / Edge / Firefox / Safari 导出的 HTML，先预览再落库；**文件夹变收藏夹、书签变外链项目**，同一网址重复导入自动跳过；导出的仍是标准书签 HTML |
| **访客门户** `/portal` | 标题与筛选区整体吸顶；卡片 / 列表两种视图（记在本地）；卡片右上角圆环是访问量、底部是实时倒计时与进度条；按类型 / 成员 / 标签 / 关键词筛选，按创建 / 到期 / 访问 / 名称排序。每张卡片都有快捷复制，点一下复制直链并冒「已复制」气泡 |
| **门户分页** | 默认 24 / 页（可切 48、96、全部），底部页码 + 「第 1–24 / 共 37 个」；翻页不重新请求，筛选一变回第 1 页。服务端一次最多 500 个，超出明确写出「另有 N 个更早的未显示」 |
| **标签有规矩** | 每项目最多 6 个（可调到 1–6）、单个 12 字、只允许中英文 / 数字 / `+ # . - _`；全角转半角、英文转小写、重名合并。门户标签条永远单行横滑，按引用次数只放前 N 个（8/12/16/24/全部），多的折成「还有 N 个」；卡片上的标签装不下就折成 `+N` |
| **作者名片** | 设置里填显示名、一句话介绍和若干链接（GitHub / 邮箱 / 抖音 / 博客 / X / B站 / 知乎 / RSS / 自定义），门户顶部多出一条名片，移动端收成图标。默认 `vita` /「互联网混子」，**不含真实个人信息** |
| **RSS** | `/rss.xml`（`/feed.xml` 同）输出最近 50 个门户可见且未过期的项目，带绝对链接与标签；门户 `<head>` 有自动发现，入口在页脚。门户不公开且未登录时 404，不会把登录页塞给阅读器 |

### 界面与观感

| 能力 | 说明 |
|---|---|
| **配色系列可换** | 设置页 6 套整套方案（经典墨绿 / 科技感 / 马卡龙 / 莫兰迪 / 新中式 / 极简黑白），卡片即缩略预览，保存后控制台、门户、预览页、错误页、`theme-color` 一起换 |
| **配色不是随手配的** | 按 60-30-10 分：画布留白 60%、卡片容器 30%、主色 10%（按钮 / 圆环 / 进度条 / 选中态）。每套只给「画布底 + 正文色 + 次级文字」三个锚点，其余中性色由它们混出；主色在白底对比度不足 3:1 时自动等比压深（色相不动），设置页写明「实际按 #xxxxxx 渲染」 |
| **「到期删除」看得见** | 到期动作是删文件的项目，门户卡片带琥珀色左边条 + 徽章 + 琥珀进度条，列表行、预览页顶栏、控制台表格与抽屉同样标记 |
| **站点图标** | 出厂是枚「沙漏」（限时可用 = 临时预览），SVG + ICO + PNG 齐全，`tools/gen_icons.py` 从同一份 SVG 生成；设置页可上传替换（`png/svg/ico/jpg/webp`，≤512KB），随时恢复默认 |
| **侧栏可折叠** | 228px → 64px 只留图标，状态记在本地，刷新后保持 |
| **管理台** | 按成员 / 类型 / 可见性 / 状态 / 标签筛选，按访问、创建、更新、到期、体积排序；抽屉里续期、改标签、开关下载、看文件清单与 14 天趋势 |
| **访问统计** | 只统计项目首页文档访问，内存累加 + 3s 批量落库（不牺牲响应速度），带 14 天趋势 |

### 运行与运维

| 能力 | 说明 |
|---|---|
| **轻** | 前端 gzip 后约 65KB；后端只依赖 fastapi / uvicorn / python-multipart，无 ORM、无 Redis、无消息队列 |
| **并发安全** | 多 agent 同时上传、同一 slug 6 路覆盖、混合读写都不写串不 500：slug 级锁 + 每次上传独立临时目录 + 原子替换 + Windows 文件句柄重试。删除时文件被占用，记录照样删，残留目录交给孤儿清理 |
| **备份 / 恢复** | 设置页一个按钮打出 zip（数据库在线快照 + 项目文件 + 下载包 + 图标 + manifest），也能拿它一键覆盖恢复；恢复前把现网数据整体挪进 `data/.backup-before-restore-<时间>/`（留 3 份），**恢复错了还能挪回来** |
| **迁移友好** | 自带 Cloudflare KV → 本地的搬运脚本，保留 slug / 标题 / 文件 / 创建与到期时间 / 访问数 |

## 给 Agent 用

命令行是**真能增删改查**的：单文件、只用标准库，拷到任何 Python 3.10+ 的机器上就能跑。

```bash
# 1) 登录一次，Key 存到 ~/.config/tmp-preview/config.json（0600）
python cli/agentctl.py login --url http://<站点>:8080 --username alice --password xxx
python cli/agentctl.py whoami                    # 我是谁、什么角色、能干什么

# 2) 部署：传完自己去探活，返回可点开的地址 + HTTP 状态
python cli/agentctl.py deploy ./dist --title "落地页 v3" --tags "前端,v3" --ttl 24
#   → 预览地址  http://.../v/landing-v3
#     已验证    HTTP 200

# 3) 日常
python cli/agentctl.py ls --status online --sort views
python cli/agentctl.py set landing-v3 --visibility private   # 门户可见 / 持链接 / 仅自己
python cli/agentctl.py extend landing-v3 48                  # 或 --forever
python cli/agentctl.py rm landing-v3

# 4) 批量 / 统计 / 管理员
python cli/agentctl.py bulk --action visibility --visibility portal --slugs a,b,c
python cli/agentctl.py members set alice --label "claude-code@笔记本" --rotate-key

# 5) 自检：建→探活→改私有(打不开)→改回(200)→续期→删除→链接失效
python cli/agentctl.py selfcheck
```

`--json` 时 stdout 只有一行 JSON（给上游程序读），人读的提示全走 stderr，两者不混。
完整命令与权限边界见 [skills/tmp-preview-agent/SKILL.md](skills/tmp-preview-agent/SKILL.md)。

也可以直接打 API：

```bash
curl -X POST http://127.0.0.1:8080/api/projects \
  -H "Authorization: Bearer pv_xxx" \
  -F "slug=demo" -F "title=演示" -F "tags=前端,验收" -F "hours=24" \
  -F "files=@dist/index.html;filename=index.html" \
  -F "files=@dist/assets/app.js;filename=assets/app.js"
```

## 部署与运维

| 事项 | 做法 |
|---|---|
| 看日志 | `docker compose logs -f --tail=100 preview` |
| 升级 | `git pull && docker compose pull && docker compose up -d`（数据在 `./data`，不受影响） |
| 改端口 | `.env` 里 `PORT=9000` |
| 反向代理 | 交给 Nginx / Caddy 终止 TLS，转发到 `127.0.0.1:8080`，并设 `COOKIE_SECURE=1` |
| 备份 | 设置页「打包下载」（数据库走在线快照，不用停服）；兜底也可以打包 `./data`，或 `sqlite3 data/db.sqlite3 ".backup backup.db"` 单独热备 |
| 恢复 | 设置页传 zip →「先看看里面有什么」→「覆盖恢复」，旧数据留在 `data/.backup-before-restore-<时间>/` |
| 进程数 | **保持 1 个 worker**：访问计数与到期巡检是进程内任务，要横向扩展得换成外置计数 / 锁 |
| 并发上限 | 多 agent 同时上传安全，同一 slug 同时写只有最后一次生效；实测 18 路并发上传单次约 3.3s，再高建议排队 |
| 清残留目录 | 文件被占用会留下目录，后台约 30 分钟内自动清；要立刻清就重启（启动时扫 `.tmp-*` / `.old-*`） |

### 版本兼容（升级前看这一段）

**升级不迁数据**：`./data` 原样留着，新版本启动时自动把老库补齐（加列、放开角色、收归无主项目、
规范化存量标签）。这几步都是幂等的，重复启动不会重复改。

**老备份能恢复**：上一个版本打的包拿过来直接「覆盖恢复」就行——恢复完会**当场跑一遍迁移**，
不用重启、不用重启后再点一次。更老的包（缺 `kind` 这类核心列）会被**明确拒绝**并列出缺哪些字段，
而且**不动现网**：与其换上去之后每个接口 500，不如先告诉你「用保存这个包时的版本升级到新版再备份」。

**书签导入导出是标准格式**：导入吃的是 Netscape Bookmark HTML，Chrome / Edge / Firefox / Safari
各自的写法（`PERSONAL_TOOLBAR_FOLDER`、`<DD>` 描述、`ICON`、没有 `<!DOCTYPE>`）都认；
本站导出的文件也能原样回灌（同网址自动跳过）。

**接口只加不改**：新版本只往响应里**加**字段（`owner_display`、`total_foreign`、`meta.project`…），
不重命名、不删除老的（`count`、`total`、`children`、`visibility`、`urls` 这些照旧），
旧的 CLI 与脚本不用改。`--collection 名字`、`set --visibility` 这类老写法仍然有效。

> 一个副作用要提前说：备份包里带着 `sessions` 表，**恢复之后所有人都要重新登录**
> （旧会话属于被覆盖的那个库）。这是有意的——恢复就该把「谁登录着」也一起回到过去。

### 资源占用

单进程、无 Redis、无 ORM，整套东西基本就是「一个 Python 进程 + 一块磁盘」。

| 项目 | 实测 / 估算 | 说明 |
|---|---|---|
| 镜像体积 | 约 **160 MB**（拉取压缩后 ~65 MB） | `python:3.12-slim` 基础镜像 ~130 MB，运行时依赖 ~22 MB，应用与前端产物不到 1 MB |
| 内存（空载） | **35 MB** | 启动完成、无请求时 |
| 内存（12 并发压测后） | **49 MB** | 900 个混合请求跑完就稳住，不随请求数线性增长 |
| 打包大文件的峰值 | **+0.2 MB** | 80 MB 文件按需打 zip，全程流式 |
| 上传时的内存 | 基本不涨 | 按 512 KB 分块写盘 |
| CPU | 单核足够 | `--workers 1`；压测约 50 req/s，瓶颈在单进程 + 同步 SQLite |
| 磁盘（数据卷） | 上传总量 × 约 2 | 项目文件 + 按需生成的 zip 缓存 |
| 数据库 | 10 个项目约 **230 KB** | SQLite + WAL，千级项目也就几 MB |

建议配置：`1C / 512MB / 5GB` 能跑，`2C / 1GB` 更从容（构建镜像时 npm install 吃点内存）。
磁盘按「预计上传总量的 2 倍」留，这是唯一会真正吃紧的资源。要限额就在 `docker-compose.yml` 里加：

```yaml
    deploy:
      resources:
        limits: { cpus: "1.0", memory: 512M }
```

> 别把内存压到 128M 以下：解释器 + 依赖本身就要几十 MB，Linux 下 RSS 通常 45–60 MB，
> 留 256M 才不会在打包 / 并发时被 OOM kill。

## 从 Cloudflare 迁到本地

```bash
docker compose stop                 # 先停服务，避免与后台任务抢写
export CF_API_TOKEN=xxx CF_ACCOUNT_ID=xxx CF_KV_NAMESPACE_ID=xxx
python migrate/from_cloudflare.py --dry-run
python migrate/from_cloudflare.py --agent admin
docker compose start
```

保留 slug、标题、说明、文件、zip、创建/更新时间、到期时间与策略、访问次数。详见 [docs/migration.md](docs/migration.md)。

## 目录结构

```
LICENSE / NOTICE     AGPL-3.0 正文 与 附加署名条款（分发/对外服务时别删）
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
cli/agentctl.py      成员侧命令行入口（兼容壳）
skills/tmp-preview-agent/  Agent 技能包：scripts/agentctl.py 是真实实现 + SKILL.md 权限边界
migrate/             Cloudflare KV → 本地
tools/               gen_icons.py、push_api.py
tests/               冒烟测试 / 截图脚本 / 演示数据
legacy/cloudflare/   旧版 Worker 实现（仅存档，不再维护）
docs/                架构、接口、可见性、迁移说明；screenshots/ 界面截图
packaging/fnos/      飞牛 fnOS 应用包工程（manifest / cmd / wizard / 打包脚本）
.github/workflows/   CI：构建镜像并推送 ghcr
```

## 自检与测试

全部是「打真服务的黑盒脚本」，跑前先起后端（带 `需 chrome` 的那几项还要有 Chrome）：

```bash
python tests/smoke_test.py       --url http://127.0.0.1:8000   # 上传/列表/改属性/批量/下载/删除/成员
python tests/check_ttl.py        --url http://127.0.0.1:8000   # 三档默认时长与到期策略
python tests/check_roles.py      --url http://127.0.0.1:8000   # 三档角色的接口与页面权限
python tests/check_visibility.py --url http://127.0.0.1:8000   # 三档可见性的真实访问结果 + Key 使用痕迹
python tests/check_collections.py --url http://127.0.0.1:8000  # 收藏夹树 / 归类 / 筛选 / 删夹去向 / 侧栏折叠
python tests/check_owner_rail.py --url http://127.0.0.1:8000   # 收藏夹归属 / 侧栏分组与筛选 / +N 计数（需 chrome）
python tests/check_visfilter.py  --url http://127.0.0.1:8000   # 侧栏三档=跳全站、工具栏=夹内快筛（需 chrome）
python tests/check_bookmarks.py  --url http://127.0.0.1:8000   # 书签导入预览 / 判重 / 导出回灌（需 chrome）
python tests/check_portal.py     --url http://127.0.0.1:8000   # 门户结构、吸顶、卡片/列表、复制按钮
python tests/check_portal_page.py --url http://127.0.0.1:8000  # 门户分页、按成员筛选、标签横滑与 +N
python tests/check_rss.py        --url http://127.0.0.1:8000   # RSS 结构、绝对链接、门户不公开时 404
python tests/check_title.py      --url http://127.0.0.1:8000   # 同成员重名拦截（新建/外链/改名/跨成员）
python tests/check_rename.py     --url http://127.0.0.1:8000   # 改名链路 + 项目名长度规则
python tests/check_entry.py      --url http://127.0.0.1:8000   # 单文件任意名 / 多文件必须有 index.html / 覆盖上传
python tests/check_gone.py       --url http://127.0.0.1:8000   # 失效链接一律 302 回门户，不泄露是否存在
python tests/check_tags.py       --url http://127.0.0.1:8000   # 标签归一化/数量/长度/字符、批量截断、孤儿回收
python tests/check_del_badge.py  --url http://127.0.0.1:8000   # 到期删除在卡片/列表/预览页的标记
python tests/check_theme.py      --url http://127.0.0.1:8000   # 主色派生、可读性兜底、非法值回落、站点图标
python tests/check_series.py     --url http://127.0.0.1:8000   # 6 套配色下发/切换/回落、对比度、画布变量
python tests/check_copy.py       --url http://127.0.0.1:8000   # 复制按钮的层级、剪贴板内容、移动端、无溢出
python tests/check_backup.py     --url http://127.0.0.1:8000   # 打包/预览/恢复/保留策略（会真恢复一次）
python tests/check_migrate.py    --url http://127.0.0.1:8000   # 老库加列迁移、悬空外键自愈
python tests/check_cli.py        --url http://127.0.0.1:8000   # CLI 全命令与越权
python tests/check_concurrency.py --url http://127.0.0.1:8000  # 6 agent 并发 / 同 slug 抢占 / 混合读写
python tests/check_icon.py       --url http://127.0.0.1:8000   # 站点图标上传/恢复（需 chrome）
python tests/check_agents_page.py --url http://127.0.0.1:8000  # 成员管理分页、越界归位、每页条数（需 chrome）
python tests/check_agents_filter.py --url http://127.0.0.1:8000 # 成员搜索/角色/状态/排序及叠加（需 chrome）
python tests/check_agent_copy.py --url http://127.0.0.1:8000   # 复制登录命令进剪贴板、失败能降级（需 chrome）
python tests/check_upload.py     --url http://127.0.0.1:8000   # 新建项目弹窗一屏放下、两列不塌（需 chrome）
python tests/check_license.py    --url http://127.0.0.1:8000   # LICENSE/NOTICE 完整 + 门户页脚/登录页/关于页署名（需 chrome）
python tests/check_count_sync.py --url http://127.0.0.1:8000   # 删除/新建后侧栏收藏夹与分类计数当场同步（需 chrome）
python tests/check_compat.py    --url http://127.0.0.1:8000   # 老备份恢复+自动迁移/更老的包被拒/老书签/老字段/老 CLI（会覆盖数据，跑完自动恢复）
```

## 安全约定

- 密钥只在 `.env` 与环境变量里，不写进仓库；
- 项目文件路径全部做穿越校验，只有 `data/projects/<slug>/` 下的文件可读；
- 上传 / 管理接口都要认证，`publisher` 只能动自己的项目，`viewer` 连项目列表都读不到；
- 访客页与项目响应均带 `X-Robots-Tag: noindex, nofollow`。

## 许可与署名

本项目以 **GNU Affero 通用公共许可证第 3 版（AGPL-3.0-only）** 发布，
全文见 [LICENSE](LICENSE)，著作权与附加署名要求见 [NOTICE](NOTICE)。

Copyright (C) 2026 Vita0519· <https://github.com/Vita0519/tmp-preview-deploy>

这意味着：

- **改了要开源。** 分发修改版要按 AGPL 提供完整源码；
- **提供网络服务也要给源码。** AGPL 第 13 条：即使不分发二进制，只要让它对外提供服务，
  就要向使用者提供完整对应源码（自建自用、内部部署同样适用）；
- **署名要保留。** 依据 AGPL-3.0 第 7(b) 条，本项目另加要求：任何再分发、修改版或对外提供的服务，
  都必须保留 [LICENSE](LICENSE) 与 [NOTICE](NOTICE)、保留「关于 / 许可」页面与登录页、门户页脚里
  指向本项目的署名与链接（页脚那句 `Powered by tmp-preview` 不许删），并在显著位置注明
  「基于 tmp-preview 修改」及修改日期；不得用原作者名义为修改版背书；
- **不想开源就谈授权。** 闭源商用、白标分发等需要豁免上述条款，请单独联系作者取得书面许可。

第三方依赖各自保留其原许可：FastAPI / uvicorn / python-multipart（MIT）、
Vue 3（MIT）、Vite（MIT）；`legacy/cloudflare/` 里的旧实现同样适用本项目许可。

## 接口

完整列表见 [docs/api.md](docs/api.md)，架构与取舍见 [docs/architecture.md](docs/architecture.md)。

## 赞赏与联系

这个项目大部分时间花在踩坑、修边角和写文档上。如果它帮你省了事，可以请作者喝杯咖啡。

| 微信赞赏 | 支付宝赞赏 |
|---|---|
| <img src="docs/qr-wechat.png" width="220" alt="微信赞赏"> | <img src="docs/qr-alipay.png" width="220" alt="支付宝赞赏"> |

| 渠道 | 地址 |
|---|---|
| GitHub | <https://github.com/Vita0519> |
| 反馈邮箱 | <admin@allfather.de5.net> |
| 交流群 | QQ `154578485` |
| 问题反馈 | [Issues](https://github.com/Vita0519/tmp-preview-deploy/issues)，附上版本号（设置 → 关于 / 许可 可见） |
| 最新版本 | [Releases](https://github.com/Vita0519/tmp-preview-deploy/releases) |

作者：**vita0519** · 许可：[AGPL-3.0-only](LICENSE)（再分发或对外服务请保留署名，见 [NOTICE](NOTICE)）
