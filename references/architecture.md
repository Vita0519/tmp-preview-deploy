# 架构与接口约定

## 组件

```
Cloudflare 账号
└── Worker "tmp-preview"        ← 唯一入口，处理所有请求
    ├── 动态门户 HTML（内联模板 + 前端 fetch API）
    ├── /api/projects 实时清单（前端每秒按服务端时间重算倒计时）
    ├── /<slug>/* 静态资源（从 KV 拼回字节）
    ├── /download/<slug> zip 下载
    ├── /upload 上传（口令鉴权，multipart，分片写 KV）
    ├── /admin 管理页 + /api/admin/*
    └── Cron */10 * * * *  到期清理
KV 命名空间 "tmp-preview-registry"
```

选 KV 而非 R2：**R2 开通需要绑卡**，KV 不需要，且免费额度足够中小项目。
清单"删除/改 TTL 立即生效"的诉求，这里是单点上写，读到自己刚写的数据没问题
（KV 最终一致只在跨边缘节点读时有秒级延迟，门户本身也是每次查）。

## KV 键布局

```
meta:__index__                 → ["slug1","slug2",...]  全量索引
meta:<slug>                    → 元数据 {name,desc,files,size,zipName,allowDownload,expireAction,createdAt,expireAt,...}
                                  expireAt=0 表示永久；expireAction='block'(默认) | 'delete'
file:<slug>:<ph(path)>         → 文件记录 {path,size,type,chunks,etag}
chunk:<slug>:<ph(path)>:<i>    → 第 i 个分片的 base64 文本（每片 <= 18MB 原始字节）
```

`ph(path)` = 路径的稳定短哈希（FNV-1a + 长度），避免 KV key 超长或含非法字符。

`__zip__` 是一个特殊"路径"，存放整包 zip 的字节。

## HTTP 接口

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| GET | `/` | 无 | 门户页（动态 HTML） |
| GET | `/api/projects` | 无 | 在线项目清单，含 `serverNow` 用于倒计时校准 |
| GET | `/<slug>/...` | 无 | 静态资源；找不到则回退该站 `index.html` |
| GET | `/download/<slug>` | 无 | 下载 zip（**默认关闭，需管理员开启**） |
| GET | `/admin` | Cookie/口令 | 管理页 |
| GET | `/api/admin/list` | `x-admin-token` | 全部项目（含已过期） |
| POST | `/api/admin/ttl` | `x-admin-token` | `{slug, hours, action}` hours<=0=永久；action 可选 block/delete |
| POST | `/api/admin/download` | `x-admin-token` | `{slug, allow}` 开关下载 |
| POST | `/api/admin/delete` | `x-admin-token` | `{slug}` 清分片 + 记录 |
| POST | `/upload` | `x-admin-token` | multipart: `slug,name,desc,ttl,allowDownload,expireAction,files[],zip`（ttl=forever/0 表永久） |
| Cron | `*/10 * * * *` | — | 到期项目：block 仅停访保留文件，delete 物理删除 |

## 门户页（前台）

服务端渲染的外壳 + 前端每 1s 重算倒计时。要点：

- **卡片是可点击的 `<div data-card>`（不是 `<a>`）**。因为卡片内含下载按钮 `<a class="dl">`，而 HTML 不允许 `<a>` 嵌套 `<a>`：一旦嵌套，浏览器会提前闭合外层 a，导致**下载按钮位置错乱/卡片结构塌陷**（早期正是这个 bug）。点击与回车由 `#grid` 上的委托监听处理，碰到 `.dl` 则 `return` 不跳转。
- **工具栏**：搜索框（实时按 名称/说明/路径/slug 过滤）、时长筛选下拉（全部/永久/24h 内/7 天内/可下载）、网格⇄列表视图切换（选择记在 localStorage）。
- **两种视图**：网格 = `repeat(auto-fill,minmax(300px,1fr))` 多列卡片；列表 = 单列紧凑行（隐藏描述/进度条，倒计时右对齐）。
- 下载按钮仅在 `allowDownload && zipName` 时出现。

## 倒计时如何做到"实时"且准确

1. `/api/projects` 返回 `serverNow`（Worker 时钟）。
2. 前端记 `offset = serverNow - Date.now()`，每秒用 `Date.now()+offset` 重算。
→ 访客手机时间不准也和服务端一致。

## 鉴权

`ADMIN_TOKEN` 环境变量。校验顺序：
`x-admin-token` 头 → `Authorization: Bearer` → `?token=` → `pp_token`/`pp_tok` Cookie。
`/admin?token=xxx` 会 `Set-Cookie: pp_token=...; HttpOnly; Secure; SameSite=Lax`；
页面 JS 成功加载后还会写一个 `pp_tok` Cookie + localStorage（30 天），实现“下次免输”。
登录状态失效时页面只提示“口令错误”而不清空已有列表。

## 上传约定

`deploy.py` 自实现 multipart（不依赖第三方库），字段：

- `slug`：URL 段 `[a-z0-9-_]`；中文名 slugify 成 `p-<hash>`
- `name`：显示名（可中文）
- `desc`：卡片副标题
- `ttl`：小时数（浮点）或 `forever`/`0`（永久），省略用 `DEFAULT_TTL_H`
- `allowDownload`：`1`/`0`，是否开放下载（**默认 0**）
- `expireAction`：`block`（默认，停访保留）/ `delete`（到期删除）
- `files`：每源文件一个 part，filename 为相对路径
- `zip`：可选整包（**必须是真的文件 part**；若传字符串 `1` Worker 会忽略，不再报错）

Worker 端先清掉同名 slug 的旧数据 → 逐文件分片写 KV → 一次性写 meta + 更新 index。

### 管理页「新增项目」面板（浏览器端）

- 文件选择支持**整个文件夹**（`webkitdirectory`）与拖拽文件夹（`webkitGetAsEntry` 递归），相对路径保留。
- 「打包 zip」在浏览器端用 **STORE 无压缩 ZIP**（`buildZip()` + 内置 `crc32`）生成，
  以 `zip` 文件名追加到 FormData，再 `POST /upload`。
- 表格每秒刷新会重建 DOM，已加保护：**当焦点在表格内输入框时只刷新倒计时，不重建**，避免抹掉正在输入的时长。

## 部署方式为什么不用 wrangler

本机走 HTTP 代理时，wrangler 的上传接口容易 `fetch failed`；
`scripts/cf_deploy.py` 直接用 REST API `PUT /accounts/<id>/workers/scripts/<name>`
（multipart 带 `metadata` + 各 ES module），稳定且能一次性配好 bindings 和 cron。
