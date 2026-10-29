# 接口一览

鉴权方式：

- 浏览器：`pv_sid` HttpOnly Cookie（`POST /api/auth/login` 下发，7 天）
- 机器调用：`Authorization: Bearer <api_key>` 或 `X-API-Key: <api_key>`

标记含义：🟢 公开 · 👤 需登录 · 🛡 仅管理员

## 认证

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/api/auth/login` | 🟢 | `{username, password}` → 设置 Cookie，返回 user |
| POST | `/api/auth/logout` | 👤 | 清会话 |
| GET | `/api/auth/me` | 👤 | 当前用户 + 自己的 api_key |
| POST | `/api/auth/token` | 🟢 | `{username, password}` → 长期 API Key（CLI 用） |
| POST | `/api/auth/password` | 👤 | `{old_password, new_password}` |

## 项目

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/projects` | 👤 | 列表。参数：`q`、`agent`、`tag`(可重复)、`kind`、`status`(online/expired/permanent/all)、`visibility`、`expiring_hours`、`sort`、`order`、`limit`、`offset`。返回 `items`、`total`、`stats`、`facets`、`server_now` |
| GET | `/api/projects/{slug}` | 👤 | 详情：含 `files[]`、`daily_views[]`、`events[]` |
| POST | `/api/projects` | 👤 | 上传（multipart）：`slug,title,description,tags,hours,forever,expire_action,allow_download,visibility,files[],zip,owner(管理员)`。`hours` 省略时按可见性取默认时长 |
| POST | `/api/projects/link` | 👤 | 登记外链：`{link_url,title,slug,description,tags,hours,forever,visibility}` |
| PATCH | `/api/projects/{slug}` | 👤 | 改属性：`title,description,tags[],visibility,allow_download,expire_action,hours,permanent,expires_at,slug(改名),revive` |
| DELETE | `/api/projects/{slug}` | 👤 | 删除项目与文件 |
| POST | `/api/projects/bulk` | 👤 | `{slugs[], action}`，action ∈ `delete, expire, permanent, extend, allow_download, deny_download, visibility, tag_add` |
| POST | `/api/projects/{slug}/reset-views` | 👤 | 访问计数清零 |
| GET | `/api/stats/trend` | 👤 | 近 N 天访问趋势（默认 14） |

## 成员

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/agents` | 🛡 | 成员列表（含项目数、在线数、访问数、Key 末 6 位） |
| POST | `/api/agents` | 🛡 | 创建：`{username, display_name, password, role}` → 返回 password/api_key |
| PATCH | `/api/agents/{id}` | 🛡 | `{display_name, active, password, rotate_key}` |
| DELETE | `/api/agents/{id}` | 🛡 | 删除成员及其全部项目 |
| GET | `/api/agents/{id}/key` | 🛡 | 查看完整 API Key |

## 设置

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/settings` | 🛡 | 站点配置 + `ttl_defaults` + 运行信息 + 最近操作 |
| PATCH | `/api/settings` | 🛡 | `{site_title, ttl_defaults:{portal,link,private}, default_expire_action, public_portal}` |

`ttl_defaults` 是**按可见性**区分的默认存活小时数，`0` 表示永久。上传/建外链时若没传 `hours`，
后端就按项目可见性取这里的值（门户默认 6h、链接 12h、私有永久）。`default_expire_action`
取值 `block`（到期停访、保留文件）或 `delete`（到期删文件与记录），新建项目时预选。

## 访客侧

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/meta` | 🟢 | 站点标题 / 在线项目数（SPA 启动用） |
| GET | `/api/public/p/{slug}` | 🟢 | 项目公开信息 + `server_now` |
| GET | `/v/{slug}` | 🟢 | 预览外壳（倒计时、下载、复制链接） |
| GET | `/p/{slug}/{path}` | 🟢 | 项目文件；无扩展名补 `index.html`；SPA 回退到 `entry` |
| GET | `/download/{slug}` | 🟢 | zip 下载（需项目开启 `allow_download`） |
| GET | `/portal` | 🟢/👤 | 门户列表（`PUBLIC_PORTAL=1` 或已登录） |
| GET | `/api/health` | 🟢 | 健康检查（容器探针） |
