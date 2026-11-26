# 架构与设计取舍

## 组件

```
                    ┌──────────────────────────────┐
  浏览器 / agent ──▶│ FastAPI (uvicorn, 单进程)      │
                    │                              │
   /v/<slug>        │  pages.py   服务端渲染外壳     │
   /p/<slug>/*      │  routers/public.py  文件直出   │
   /download/<slug> │  routers/projects.py  增删改查 │
   /api/*           │  routers/auth|agents|settings │
   /                │  SPA（frontend/dist）         │
                    └───────┬──────────────┬───────┘
                            │              │
                    SQLite (WAL)     /data/projects/<slug>/
                    /data/db.sqlite3 /data/zips/<slug>.zip
```

单容器部署：前端在构建阶段由 Node 编成静态产物，运行时由 FastAPI 同端口托管，
不额外挂 Nginx（少一跳、少一个容器），反向代理交给宿主机的 Caddy/Nginx（可选）。

## 为什么这么选

| 决策 | 原因 |
|---|---|
| SQLite + WAL | 万级项目、单机、读多写少。WAL 让读不阻塞写，`BEGIN IMMEDIATE` 短事务即可；无需额外中间件 |
| 文件存磁盘而非 DB blob | 大文件（模型/视频）走 `FileResponse` 零拷贝，DB 只存元数据 |
| 访问计数内存累加 | 每次访问写盘会成为瓶颈。内存计数 + 3s 批量落库 + 日粒度 `daily_views`，掉电最多丢 3 秒计数 |
| 访客页服务端渲染 | 预览页要"秒开"，不加载 40KB+ 的 SPA；外壳 HTML 约 7KB，内联 CSS/JS |
| 单 worker | 计数缓冲与到期巡检是进程内任务。多 worker 需拆成外置计数（Redis）与独立 cron |
| API Key 而非 JWT | 机器调用场景，Key 可直接吊销、可轮换；浏览器端仍用 HttpOnly 会话 Cookie |

## 数据模型

```sql
users(id, username UNIQUE, display_name, role[admin|agent], password_hash,
      api_key UNIQUE, active, created_at, last_login_at)
sessions(token PK, user_id, created_at, expires_at, ua)
projects(id, slug UNIQUE, title, description, owner_id, kind[static|zip|link],
         entry, file_count, size_bytes, has_zip, zip_name, link_url,
         visibility[portal|link|private], allow_download, expire_action[block|delete],
         expires_at NULL=永久, status[active|expired|deleted], views, downloads,
         created_at, updated_at, last_viewed_at, legacy_source)
tags(id, name UNIQUE) / project_tags(project_id, tag_id)
daily_views(project_id, day, count)
events(id, at, user_id, action, project_id, detail)
settings(key, value)
```

索引覆盖：`owner_id`、`status`、`expires_at`、`views`、`updated_at`，列表页默认按 `updated_at DESC`。

## 权限模型

- **管理员**：全部项目的读写、成员管理、系统设置。
- **成员（agent）**：只能读写 `owner_id = 自己` 的项目；成员管理接口返回 403。
- **访客**：只看得到 `visibility != private` 的项目；`private` 仅归属者与管理员可访问
  （实现方式：`_public_state()` 里对 private 项目要求已登录且是 owner/admin）。
- 机器调用：`Authorization: Bearer <api_key>`；浏览器：`pv_sid` HttpOnly Cookie（默认 7 天）。

## 请求路径与缓存

| 路径 | 行为 |
|---|---|
| `GET /p/<slug>/<path>` | 命中文件 → `FileResponse`；无扩展名 → 补 `index.html`；仍无 → 回退项目 `entry`（SPA 兜底）；路径越界 → 404 |
| 缓存头 | 入口文档 `no-store`；静态子资源 `public, max-age=300`；均带 `ETag`，命中 `If-None-Match` 返回 304 |
| 计数 | 只有「入口文档 + `Accept: text/html` + GET」才 +1，子资源与 SPA 内部跳转不重复计 |
| `GET /download/<slug>` | 有预置 zip 直接发；没有则按需打包（`ZIP_DEFLATED`，保留 mtime）并缓存到 `/data/zips`；项目失效则 302 回门户 |
| `GET /v/<slug>` | 可见且未到期 → 预览外壳；外链 → 302 到 `link_url`；失效/无权/无入口 → 302 `/?gone=1` |

## 到期处理

后台任务每 60s 扫一遍 `status='active' AND expires_at <= now`：

- `expire_action='block'` → 置 `status='expired'`，文件保留，访问 **302 回门户首页**（并带「链接已失效」提示）；
- `expire_action='delete'` → 删目录 + 删 zip + 删行（`project_tags`、`daily_views` 级联）。

`PATCH /api/projects/{slug}` 带 `revive: true` 可以把已到期项目重新激活。

## 上传流程

1. `multipart/form-data` 接收 `files[]`（保留相对路径）或单个 `zip`；
2. 先写 `data/projects/.tmp-<slug>/`，全部成功后再 `os.replace` 成正式目录（原子替换，避免半成品）；
3. 计算 `file_count` / `size_bytes` / `entry`，写元数据与标签（同一事务）；
4. 同名 slug 视为覆盖：保留 `views` 与 `created_at`，`updated_at` 刷新。

## 前端

Vue 3 + Vite，无 UI 框架，`styles.css` 是一套手写设计系统（暖灰画布 + 单强调色、
1px 描边分层、160–220ms 缓动）。强调色默认电光蓝 `#2563eb`，由设置页写进
`--brand*` 一组 token，全站（含门户页）跟着换。图标是一套 16px 栅格的线性图标
（`Icon.vue`，1.5 描边、圆头端点），标志是纯色平涂的直角沙漏（`BrandMark.vue`，
`frontend/public/favicon.svg` 为唯一矢量源，其余尺寸由 `tools/gen_icons.py` 生成）。
列表页的分面、筛选、排序全部走服务端，前端只维护筛选状态（写入 localStorage），
倒计时用 `server_now` 校准后本地每秒重算。
