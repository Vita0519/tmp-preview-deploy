# 接口一览

鉴权方式：

- 浏览器：`pv_sid` HttpOnly Cookie（`POST /api/auth/login` 下发，7 天）
- 机器调用：`Authorization: Bearer <api_key>` 或 `X-API-Key: <api_key>`

标记含义：🟢 公开 · 👤 需登录 · ✍ 需 `publisher` 及以上 · 🛡 仅管理员

角色三档：`viewer`（仅门户）/ `publisher`（可发布项目）/ `admin`（管理员）。老的 `agent` 角色在启动迁移时会自动转成 `publisher`。

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
| GET | `/api/projects` | ✍ | 列表。参数：`q`、`agent`、`tag`(可重复)、`kind`、`status`(online/expired/permanent/all)、`visibility`、`collection`(收藏夹 id / `none`)、`expiring_hours`、`sort`、`order`、`limit`、`offset`。返回 `items`、`total`、`stats`、`facets`、`server_now` |
| GET | `/api/projects/{slug}` | ✍ | 详情：含 `files[]`、`daily_views[]`、`events[]` |
| POST | `/api/projects` | ✍ | 上传（multipart）：`slug,title,description,tags,hours,forever,expire_action,allow_download,visibility,collection,files[],zip,owner(管理员)`。`hours` 省略时按可见性取默认时长；`allow_download` **默认为开**，传 `0` 才关；`collection` 是收藏夹 id 或 `none` |
| POST | `/api/projects/link` | ✍ | 登记外链：`{link_url,title,slug,description,tags,hours,forever,visibility,collection_id}` |
| PATCH | `/api/projects/{slug}` | ✍ | 改属性：`title,description,tags[],visibility,allow_download,expire_action,hours,permanent,expires_at,slug(改名),revive,collection_id`（`null` / `"none"` = 移出收藏夹） |
| DELETE | `/api/projects/{slug}` | ✍ | 删除项目与文件 |
| POST | `/api/projects/bulk` | ✍ | `{slugs[], action}`，action ∈ `delete, expire, permanent, extend, allow_download, deny_download, visibility, tag_add, collection`（后者带 `collection_id`，`null` = 移出） |
| POST | `/api/projects/{slug}/reset-views` | ✍ | 访问计数清零 |
| GET | `/api/stats/trend` | ✍ | 近 N 天访问趋势（默认 14） |

**重名规则**：同一个成员名下不允许出现两个同名项目（比较时忽略大小写与首尾空格）。
新建、登记外链、改名三条路径都会校验，撞上就返回 `409`，`detail` 里会点名占用的那个 slug：

```json
{"detail": "项目名「落地页 v3」已被你的其它项目占用（landing-v3）。换个名字，或者直接用那个 slug 覆盖更新。"}
```

- **覆盖更新不算冲突**：上传时用已有的 `slug` 再传一次，标题不变也照样成功；
- **跨成员不算冲突**：两个人各有一个「落地页 v3」互不影响（彼此看不到）；
- 管理员 `owner=` 替某人建项目时，按**那个成员**的命名空间判重；
- 历史上已经重名的老数据不会被自动改名，只在新建/改名时拦截。

**长度规则**：按**显示宽度**数，不是字符个数——中文算 `1`、半角（英文字母/数字/空格/标点）算 `0.5`，
上限 `10`，也就是 **10 个中文字符 ≈ 20 个英文字符**。规则由 `/api/meta` 的 `title_rule` 下发：

```json
{"max_width": 10, "max_cjk": 10, "max_narrow": 20, "hint": "最多 10 个中文字符（约 20 个英文字符）"}
```

两条路走法不同，故意的：

| 场景 | 超长时 | 为什么 |
|---|---|---|
| `PATCH /api/projects/{slug}` 改名 | **422**，`detail` 写明当前宽度 | 名字是用户刚敲的，偷偷改掉更讨厌 |
| 上传 / 登记外链时传的 `title` | **自动截断**到上限内，响应里给真实落库的名字 | 为了一个名字把人拦在上传门外不值当 |

```json
{"detail": "项目名最多 10 个中文字符（约 20 个英文字符），当前 11 个"}
```

截断不会劈坏字符，也会去掉尾部的空格与标点；不传 `title` 时从文件名 / URL 推导，同样按这条规则截。

## 收藏夹（项目层级归类）

两级：**收藏夹 → 子收藏夹**，项目挂在任意一层（挂在父夹上的不会自动算进子夹）。
表里只有 `parent_id`，没有写死 `level`，以后要放开深度不用迁表。

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/collections` | ✍ | 树：`{items:[{id,name,parent_id,icon,sort,count,total,children}], unassigned, total, visibility:{portal,link,private}, max_depth}` |
| POST | `/api/collections` | ✍ | 新建：`{name, parent_id?, icon?}`。同名（同层）→ 409；挂到子夹下（第三层）→ 422 |
| PATCH | `/api/collections/{id}` | ✍ | 改名 / 换图标 / 调顺序 / 移动：`{name?,icon?,sort?,parent_id?}` |
| DELETE | `/api/collections/{id}` | ✍ | 删夹。默认**只删壳**，里面的项目退回「未归类」；`?with_projects=1` 才连项目与文件一起删 |

返回字段里 `count` 是直属项目数，`total` 是含子夹的合计；`total`（顶层）已经包含「未归类」，
所以侧栏的「全部项目」跟项目列表的 `total` 永远对得上。非管理员只统计**自己名下**的项目。
`visibility` 是三档可见性的数量（`portal/link/private`，三者之和 = `total`），
控制台侧栏把它们当成常驻分类，所以工具栏里的可见性下拉只在窄屏兜底时才出现。

删夹的返回：

```json
{"ok": true, "removed": 2, "moved_to_unassigned": 1, "deleted_projects": 0, "name": "办公"}
```

`removed` 是删掉的收藏夹个数（含子夹），两个数字只会有一个非零。

**筛选**：`GET /api/projects?collection=12` 取 12 及其子夹的项目；`collection=none` 只取未归类的；
非数字且不是 `none` → `400`（以前会静默当成「全部」，看着像筛了其实没筛）。

## 导入 / 导出（浏览器书签）

Chrome、Edge、Firefox、Safari 导出的书签都是同一种 Netscape HTML，一个解析器全吃。
**文件夹 → 收藏夹，书签 → 外链项目**（默认 `visibility=private`，仅自己可见）。

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/api/import/bookmarks` | ✍ | multipart：`file`（或 `text` 直接贴 HTML）、`parent_id`、`visibility`、`tag`、`dry_run` |
| GET | `/api/export/bookmarks` | ✍ | Netscape HTML 附件；`?collection=<id>` 只导这个夹（含子夹） |

导入的层级映射：

| 场景 | 结果 |
|---|---|
| 不指定 `parent_id` | 书签一级文件夹 → 一级收藏夹；二级 → 子收藏夹；**更深的层折进第二级** |
| 指定 `parent_id` | 目标夹已经是一级，只能再往下放一层：书签一级文件夹 → 它的子夹，更深折进去 |

其它规则：

- 同一个网址**重复导入自动跳过**（按 `link_url` 判重，跨次也有效），所以反复导同一个文件不会长出一堆重复项目；
- `javascript:` / `place:` / `data:` / `chrome:` / `about:` / `file:` 这类地址直接丢弃；
- 书名超长会按项目名规则截短并加 `(2)` / `(3)` 去重；
- 单文件 8MB 上限，一次最多 500 条，超出的部分在 `truncated` 里报数。

```json
{"ok": true, "dry_run": false, "created": 5, "folders_created": 3, "parsed": 6,
 "skipped_duplicate": 0, "skipped_invalid": 1, "truncated": 0, "visibility": "private"}
```

`dry_run=1` 时只解析不落库，额外返回 `folders`（`[[一级, 二级], …]`）、`items`（最多 200 条预览）与 `will_create`。
导出的响应带 `X-Bookmark-Count`，方便脚本核对条数。

## 备份 / 恢复（仅管理员）

备份 = **一个 zip**：数据库在线快照（`sqlite3.backup()`，WAL 里没落盘的也会带上）+ `projects/` + `zips/` + `branding/` + `manifest.json`。

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/backup` | 👑 | 直接下载 `preview-backup-<时间>.zip`；打完临时文件自动清掉 |
| POST | `/api/backup/inspect` | 👑 | 上传 zip，只读检查：`{db, files, zips, branding, manifest}`。不是本站备份 → 422 |
| POST | `/api/backup/restore` | 👑 | 用 zip 覆盖现网数据，返回 `{ok, counts, backup_dir, files, zips}` |

恢复是**整体换血**，但旧数据不会消失：现网的 `db.sqlite3`（连同 `-wal`/`-shm`）、`projects/`、`zips/`、`branding/` 会被整体挪进
`data/.backup-before-restore-<时间>/`，只保留最近 3 份。实在删不掉的会被改名丢进 `data/.trash/`，不会悄悄占满磁盘。

```json
{"ok": true, "counts": {"projects": 25, "users": 6, "collections": 3, "tags": 15},
 "backup_dir": ".../data/.backup-before-restore-20261102-083925", "files": 324, "zips": 3}
```

`counts.projects` 只数 `status='active'`，跟控制台列表的总数一致。

## 成员

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/agents` | 🛡 | 成员列表（含项目数、在线数、访问数、Key 末 6 位）。`?limit=&offset=` 分页，`limit=0`（默认）返回全部；响应带 `total` |
| POST | `/api/agents` | 🛡 | 创建：`{username, display_name, password, role}` → 返回 password/api_key |
| PATCH | `/api/agents/{id}` | 🛡 | `{display_name, active, password, rotate_key, role}`。`role` ∈ `viewer/publisher/admin`，不能改自己，也不会让管理员数量归零 |
| DELETE | `/api/agents/{id}` | 🛡 | 删除成员及其全部项目 |
| GET | `/api/agents/{id}/key` | 🛡 | 查看完整 API Key |

## 设置

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/settings` | 🛡 | 站点配置 + `ttl_defaults` + `theme` + `site_icon` + `author` + `author_types` + 运行信息 + 最近操作 |
| PATCH | `/api/settings` | 🛡 | `{site_title, ttl_defaults:{portal,link,private}, default_expire_action, public_portal, theme_series, theme_accent, tag_max_per_project, tag_bar_limit, author}` |
| POST | `/api/settings/icon` | 🛡 | `multipart/form-data` 上传站点图标，字段名 `file`；同时间只留一份 |
| DELETE | `/api/settings/icon` | 🛡 | 删除自定义图标，回到内置沙漏图标 |
| POST | `/api/settings/tags/prune` | 🛡 | 清理没有任何项目在用的标签，返回剩余占用 |

`ttl_defaults` 是**按可见性**区分的默认存活小时数，`0` 表示永久。上传/建外链时若没传 `hours`，
后端就按项目可见性取这里的值（门户默认 6h、链接 12h、私有永久）。`default_expire_action`
取值 `block`（到期停访、保留文件）或 `delete`（到期删文件与记录），新建项目时预选。

`author` 结构：`{name, bio, links:[{type,label,url}]}`，`type` ∈
`github|x|mail|blog|douyin|wechat|bilibili|zhihu|rss|link`（白名单，未知类型落到 `link`）。
`url` 会做规范化：邮箱可只填地址（自动补 `mailto:`），其他不带协议的自动补 `https://`，
`javascript:` / `data:` 之类非 http(s) 协议直接丢弃。门户页顶部据此渲染一行图标链接。

## 访客侧

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/meta` | 🟢 | 站点标题 / 在线项目数 / `theme` 色板 / `site_icon` / `tags` 标签规则 / `title_rule` 项目名规则（SPA 启动用） |
| GET | `/api/public/p/{slug}` | 🟢 | 项目公开信息 + `server_now` |
| GET | `/v/{slug}` | 🟢 | 预览外壳（倒计时、下载、复制链接）；外链项目 **记一次访问后 302 直达目标站**，失效/无权访问 **302 回 `/portal?gone=1`** |
| GET | `/p/{slug}/{path}` | 🟢 | 项目文件；无扩展名补 `index.html`；SPA 回退到 `entry` |
| GET | `/download/{slug}` | 🟢 | zip 下载（需项目开启 `allow_download`）；失效同样 302 回门户 |
| GET | `/download/{slug}/{rel}` | 🟢 | **单个文件**下载（文件名取原名，中文名走 RFC 5987）；`allow_download=0` → 403；非静态项目（zip 包）自动回落到整包下载；`../` 越界一律 404 |
| GET | `/portal` | 🟢/👤 | 门户列表（`PUBLIC_PORTAL=1` 或已登录） |
| GET | `/rss.xml`、`/feed.xml` | 🟢/👤 | 门户 RSS（最近 50 个门户可见且未过期项目）；门户不公开且未登录 → 404 |
| GET | `/site-icon` | 🟢 | 自定义站点图标；没上传过 → `404`（页面回落到内置图标） |
| GET | `/site.webmanifest` | 🟢 | 动态 manifest：`icons` 跟自定义图标走，`theme_color` 跟主色走 |
| GET | `/api/health` | 🟢 | 健康检查（容器探针） |

**失效与权限一律用「跳转」表达，不再用 404 页：**

- 项目不存在 / 已删除 / 已过期 / 无权访问 → `302 /portal?gone=1`。门户本身若需要登录，会继续 302 到 `/login`，因此**不会通过 URL 泄露项目是否存在**。
- `/p/{slug}/{path}` 在 iframe 里被引用时（`Accept: text/html`）→ 返回一张只做一件事的失效页：`window.top.location.replace()` + `<meta refresh>`，把**顶层**窗口带走，不在 iframe 里显示 404。
- 子资源请求（css/js/png，`Accept` 不含 `text/html`）→ 静默 `404`，避免图片被跳成一张 HTML 页。
- `kind=link` 的项目：`/v/{slug}`、`/p/{slug}/` 都直接 `302` 到 `link_url`，**并在 `302` 之前记一次访问**（`Accept: text/html` 的 GET 才算），所以门户卡片、复制按钮给的都是本站短链 `/v/{slug}`——转发出去照样统计得到。

**入口文件规则**

| 上传内容 | 入口 `entry` | 结果 |
|---|---|---|
| 只有 1 个文件（任意名字、任意类型） | 该文件 | `/v/` 的 iframe 直接指向它 |
| 多个文件 + 根目录 `index.html`/`index.htm` | `index.html` | 正常 |
| 多个文件 + 没有 `index.html` | — | **422**，提示改名、拆单文件或改用 zip 上传 |

历史项目（`entry` 为空）仍按「根目录唯一 html」兜底，不会被判成失效。

**标签规则**

自由输入的标签不设上限就会长成一团乱麻，所以规则是硬约束：超了就 `422` + 一句中文说明，
**不静默截断**（截断会让人以为加上了）。规则实现在 `backend/app/tagspec.py`，前端 `src/tags.js` 是同一套镜像。

| 项 | 规则 | 违规返回 |
|---|---|---|
| 每个项目数量 | ≤ 6 个（**设置里可调到 1–6**） | `每个项目最多 3 个标签，你填了 8 个` |
| 单个长度 | 1–12 字（中文按 1 字） | `标签「xxx」太长了：最多 12 个字` |
| 允许字符 | 中英文、数字与 `+ # . - _`（不许空格） | `标签「数据/分析」含有不允许的字符…` |
| 分隔符 | `,` `，` `、` `;` `；` 空白 | — |
| 归一化 | NFKC 全角转半角 + 英文小写 + 去重保序 | `Vue`/`VUE`/`vue` → `vue` |
| 全站池 | ≤ 300 个不同标签 | `全站标签已达 300 个上限，请改用已有标签` |

写入入口只有 `db.set_tags()` 一处：`POST /api/projects`、`POST /api/projects/link`、
`PATCH /api/projects/{slug}`、`POST /api/projects/bulk`（`tag_add`）都走它。
没人引用的标签会自动回收（改标签、删项目、到期清理时），所以池子不会越用越脏。
批量 `tag_add` 是「合并」语义：已有标签在前，新标签塞到上限为止，塞不下的项目计入返回的 `trimmed`。

两条软限制在设置页能改，都走 `PATCH /api/settings`：

| 字段 | 默认 | 范围 | 作用 |
|---|---|---|---|
| `tag_max_per_project` | 6 | 1–6 | 每个项目最多几个标签；越界值会被夹到合法区间 |
| `tag_bar_limit` | 12 | `0` 或 4–40 | 门户标签条放几个标签；`0` = 全部（仍以 40 封顶） |

`GET /api/settings` 与 `GET /api/meta` 的 `tags` 字段会带上生效值
（`max_per_project`、`max_per_project_cap`、`bar_limit`、`bar_limit_max`）。门户标签条按
**被引用次数从多到少**取前 `tag_bar_limit` 个，同频按首次出现顺序，被折叠的用「还有 N 个」
占位（无点击行为，鼠标悬停提示去设置里放宽）；如果当前筛选的标签不在前 N 个里，会强制顶到条上，
避免出现「筛选中却看不到选中项」。

**到期删除的视觉标记**

`expire_action` 为 `delete` 的项目（到期连目录一起删掉）在所有出现的地方都会被标出来：

- 门户卡片：`class="card del"` + 琥珀色左边条（`::before`）+ 「到期删除」徽章 `.deltag` + 进度条改琥珀；
- 门户列表行：`class="row del"`，同样带徽章；
- 预览页 `/v/{slug}` 顶栏：带 `.deltag` 徽章（窄屏只留图标）；
- 卡片上还有 `data-act="delete|block"`，方便脚本按到期动作筛。

**配色系列 / 主题色**

`GET /api/meta` 与 `GET /api/settings` 都带 `theme` 字段：

| 字段 | 说明 |
|---|---|
| `accent` | 实际生效的主色（可能是被压深后的值，见 `adjusted`） |
| `raw` | 用户填的原值 |
| `adjusted` | `accent != raw`，浅色被可读性兜底压深过 |
| `hover/soft/line/deep/light/rgb` | 由 `accent` 派生（与 `frontend/src/theme.js` 同公式） |
| `neutral` | 整套中性色：`bg` `bg-2` `bg-deep` `surface-2` `surface-3` `ink` `ink-2` `ink-3` `ink-4` `line` `line-2` `ink-rgb` `bg-rgb` |
| `series` / `series_name` | 当前系列 key 与名字 |
| `custom` | 主色不属于任何一套系列（手改过） |
| `series_list` | 全部 6 套系列，每套带 `key/name/desc/use/accent/neutral` |

`PATCH /api/settings {"theme_series": "tech"}` 换整套配色：系列决定中性色画布，并把主色换成该系列的
（除非同一请求里也给了 `theme_accent`，那就以 `theme_accent` 为准——允许选完系列再微调）。
`theme_accent` 接受 `#abc` / `abc` 简写，非法值静默回落 `#0f766e`。未知的 `theme_series` 回落 `classic`。

服务端渲染的页面把变量写进 `:root`（`--brand*` + `--bg/--ink/--line` 一整套），控制台启动时用
`/api/meta` 的同一份色板覆盖。设置页的 6 张系列卡就是按 `series_list` 里每套的真实配色渲染的缩略图，
点一下即时预览，不保存则离开页面自动回滚。

主色只当强调色用，**跟白底的对比度低于 3:1 会等比压深**（色相不变，见 `theme.readable()`），
避免选个淡黄导致按钮上的白字和浅底上的主色文字一起看不见。

**站点图标**

`POST /api/settings/icon` 上传自定义 favicon，落在 `DATA_DIR/branding/site-icon.<ext>`，**只保留一份**：

| 校验 | 不通过时 |
|---|---|
| 后缀 ∈ `png / svg / ico / jpg / jpeg / webp` | `422` |
| 文件非空 | `422` |
| ≤ 512KB | `422` |
| `.svg` 头部得真像 SVG | `422` |

`site_icon` 字段在所有接口里形状一致：
`{custom, url, ext, size, max_kb, formats}`。没上传时 `custom=false`、`url=""`，前端据此回落到内置图标。
`url` 里带 `?v=<mtime>`，换图后不会被浏览器老缓存卡住。
门户页的 `<link rel="icon">`、`apple-touch-icon`、`/site.webmanifest` 的 `icons` 全部跟着它走；
`theme_color` 则跟主题色走，手机加到主屏后标题栏也是当前主色。

**门户页脚**

RSS 入口固定在门户页脚右下（`<footer class="pfoot">`），与左侧「站点标识 · 公开项目数」同一行，
不再占用顶栏按钮位；`<link rel="alternate" type="application/rss+xml">` 同时在 `<head>` 里，阅读器可直接发现。
页脚用 `margin-top:auto` 贴住视口底部，项目少时页面也不会在中间断层。
