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

- **多 Agent 共享**：每个成员一把 API Key，上传的项目自带归属，互相看不到；管理员看全部。
- **权限清晰**：管理员 / 成员两级；项目可见性分「门户可见 / 持链接可见 / 仅自己」，三档各自一套默认时长。
- **到期自动化**：到期后可选「停止访问保留文件」或「连同文件删除」，后台每 60s 巡检；站点级可设默认策略。
- **访客门户** `/portal`：卡片带实时倒计时与访问量条，支持按类型/标签/关键词筛选，按创建、到期、访问排序。
- **访问统计**：只统计项目首页文档访问，内存累加 + 3s 批量落库（不牺牲响应速度），带 14 天趋势。
- **管理台**：按成员 / 标签 / 类型 / 状态筛选，按访问、创建、更新、到期、体积排序，抽屉里一键续期、改标签、开关下载。
- **轻**：前端 gzip 后约 65KB；后端只依赖 fastapi / uvicorn / python-multipart，无 ORM、无 Redis。
- **迁移友好**：自带 Cloudflare KV → 本地的搬运脚本，保留原 slug、创建时间、到期时间与访问数。

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

```bash
# 1) 登录一次，Key 存在 ~/.config/tmp-preview/config.json
python cli/agentctl.py login --url http://<站点地址>:8080 --username alice --password xxx

# 2) 部署一个目录（默认用服务端 TTL）
python cli/agentctl.py deploy ./dist --title "落地页 v3" --tags "前端,v3" --ttl 24

# 3) 日常
python cli/agentctl.py ls
python cli/agentctl.py extend landing-v3 48
python cli/agentctl.py extend landing-v3 --forever
python cli/agentctl.py tags landing-v3 前端,v3,已验收
python cli/agentctl.py rm landing-v3
```

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
cli/agentctl.py      成员侧命令行（仅标准库）
migrate/             Cloudflare KV → 本地
tests/               冒烟测试 / 截图脚本 / 演示数据
legacy/cloudflare/   旧版 Worker 实现（仅存档，不再维护）
docs/                架构、接口、迁移说明
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

## 安全约定

- 密钥只在 `.env` 与环境变量里，不写入仓库；
- 项目文件路径全部做穿越校验，只有 `data/projects/<slug>/` 下的文件可读；
- 上传/管理接口都要认证，成员只能操作自己的项目；
- 访客页与项目响应均带 `X-Robots-Tag: noindex, nofollow`。

## 接口

完整列表见 [docs/api.md](docs/api.md)，架构与设计取舍见 [docs/architecture.md](docs/architecture.md)。
