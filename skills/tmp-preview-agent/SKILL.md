---
name: tmp-preview-agent
description: 以「一个账号 = 一个 Agent = 一把 API Key」的身份，用脚本或命令行管理自托管临时预览站上的项目：部署目录/静态站、建外链、改可见性（门户/持链接/仅自己）、续期、打标签、批量清理、查访问量，以及管理员如何管成员与权限。当用户说「把 dist 部署到预览站」「续期这个预览链接」「改成只有我能看」「这个预览站有哪些项目」「轮换 key」「加个成员」「批量删除过期项目」时使用。重点是权限边界与 Key 的一对一绑定。
---

# 以 Agent 身份管理预览站

这套服务里没有「机器人账号」这种独立概念：**成员账号本身就是 Agent**。
一个账号配一把 `pv_...` 的 API Key，这把 Key 就是该账号的全部身份。

```
账号 (users) 1 ──── 1 API Key   1 ──── 1 Agent（写清楚绑给谁：key_label）
   │
   └── 1 ── N 项目（publisher 只看自己名下的；admin 看全部）
```

## 零、这个 skill 不是说明书，它带可执行脚本

```
skills/tmp-preview-agent/
├── SKILL.md              你正在读的这份
└── scripts/agentctl.py   真正的客户端：单文件、只用标准库、Python 3.10+ 免安装
```

把 skill 目录整个交给任何一个能执行 shell 的 Agent，它就能真的建 / 改 / 删 / 查，
不用你代劳，也不需要 `pip install`：

```bash
python scripts/agentctl.py --help        # 14 个命令全部可用
python scripts/agentctl.py selfcheck     # 用当前身份真跑一遍：建→探活→改私有→改回→续期→删除
```

（仓库里 `cli/agentctl.py` 只是指向同一份实现的三行入口壳，两个路径等价。）

| 命令 | 作用 | 关键参数 |
|---|---|---|
| `login` | 账号密码或已有 Key 换成本地凭据（0600 落盘） | `--url` `--username` `--password` / `--api-key` |
| `whoami` | 我是谁、什么角色、能干什么 | — |
| `health` | 站点是否活着 + Key 是否还有效 | — |
| `deploy` | 上传目录，**传完自动探活** | `--slug` `--title` `--ttl` `--visibility` `--collection` `--zip` `--no-verify` |
| `link` | 只登记外链，不发文件 | `--url` `--title` `--ttl` `--collection` |
| `ls` | 列项目（默认只看自己的） | `--status` `--visibility` `--collection` `--tag` `--q` `--sort` `--limit` |
| `show` | 单个项目详情：文件清单、14 天访问、事件流水 | `<slug>` |
| `set` | 改可见性 / 到期 / 标题 / 标签 / 下载 / 归属收藏夹 | `--visibility` `--ttl` `--forever` `--tags` `--collection` `--no-collection` |
| `extend` | 只续期 | `<slug> <小时>` 或 `--forever` |
| `rm` | 删项目（文件 + zip + 访问记录） | `<slug>` `--yes` |
| `bulk` | 批量改可见性 / 续期 / 删 | `--action` `--slugs` `--yes` |
| `stats` | 访问趋势 | `--days` |
| `members` | 成员管理（**需 admin**） | `list/create/set/rm/key`、`--role` `--label` `--rotate-key` |
| `collections` | 收藏夹：列表 / 新建 / 删除 | `ls`(默认) `add --name [--parent]` `rm <id或名字> [--with-projects]` |
| `selfcheck` | 自检，别信文档，信这个 | — |

**输出契约（给上游程序读）**

- `--json`：stdout 只有**一行** JSON `{"ok":true,"cmd":"deploy","data":{…}}`，
  人读的提示全部走 stderr，两者永不混流；
- 退出码：`0` 成功 / `1` 失败（原因在 `error` 字段，形如 `HTTP 403：…`）；
- 5xx 与网络错误自动重试 3 次；4xx 不重试（重试也一样）。

**`deploy` 到底返回什么**（最常被问的「会不会自动给你地址」）

```json
{"ok":true,"cmd":"deploy","data":{
  "slug":"landing-v3",
  "preview_url":"https://preview.example.com/v/landing-v3",
  "expires_at":1793000000000,"files":3,"size_bytes":84213,
  "visibility":"link","verified":true,"http_status":200}}
```

`preview_url` 是完整可点开的地址；`verified` / `http_status` 是**上传完成后真去请求一次**的结果。
若项目是 `private`，匿名探活拿到的会是 302（跳门户/登录页）而不是 200——那是正常的，
所以你以「不是 200」来判定打不开即可（`--no-verify` 可跳过探活）。

> **失效不是 404 了。** 过期 / 已删除 / 改私有 / 访问别人私有项目，预览地址统一 `302` 回门户首页，
> 门户需要登录时再转 `/login`。所以拿 `curl -I` 看到的常常是 302 而不是 404，别误判成「还能访问」。
> 判定标准只有一个：**原地返回 200 才算活着**。

**图标**：预览页自动用项目自带的 `favicon.ico / favicon.svg / favicon.png / apple-touch-icon.png`，
都没有才退回站点默认图标，不需要额外配置。

**并发**：各 agent 用自己的 Key 并行上传是安全的（slug 级锁 + 每次上传独立临时目录 + 原子替换 +
Windows 文件句柄重试）。同一个 slug 被多路同时覆盖时文件不会写串，但**只有最后一次生效**；
要保留多份就换 slug。实测 6 个 agent × 3 路并发共 18 个上传全部 200，单次约 3.3s。

## 一、凭据：一个账号只能有一个 Agent

| 规则 | 说明 |
|---|---|
| 一对一 | `users.api_key` 有 UNIQUE 约束，一个账号只可能有一把 Key |
| 绑定可追溯 | 成员页每行能编辑「绑定 Agent」（`key_label`，如 `claude-code`），并显示 `…尾号 · 最近使用时间` |
| 不可共享 | 两套脚本共用一个 Key = 两条执行流共用一个身份，出问题无法归因。要第二个 Agent，就再开一个成员 |
| 轮换即失效 | 轮换后旧 Key 立刻 401，`key_uses` 归零重新计数 |
| 停用即断 | 成员停用后 Key 立即失效（`active=0` 直接查不到用户） |

**怎么拿到 Key**：管理员在「成员」页创建成员时填「绑定 Agent」，创建成功弹窗里只显示一次
`API Key` 和密码；之后可用 `GET /api/agents/{id}/key`（仅管理员）取回，或用轮换重新生成。

**怎么用**：

```bash
# 方式一：CLI 一次性登录，凭据存本地
python scripts/agentctl.py login --url https://preview.example.com --username alice --password xxx
python scripts/agentctl.py deploy ./dist --title "落地页 v3" --ttl 24 --tags 前端,v3

# 方式二：账号密码直接换 Key（CLI 内部就是这一步）
curl -X POST -d '{"username":"alice","password":"xxx"}' https://<站点>/api/token

# 方式三：直接打 API（脚本 / Agent 里最常用）
curl -H "Authorization: Bearer pv_xxx" https://preview.example.com/api/projects
```

> **账号密码和 Key 等权**：`POST /api/token` 能用密码换出同一把 Key，
> 所以「一个 agent 一个账号」意味着**密码也只能给这一个 agent**。
> 把密码同时交给两个 Agent，等于让两个执行流共用一个身份，同样无法归因。

> Key 等价于密码。不要写进 git、不要打印到日志、不要放进前端的可读位置。
> 本地配置在 `%APPDATA%\tmp-preview\config.json`（Linux/macOS 是 `~/.config/tmp-preview/config.json`），权限 600。

## 二、权限矩阵

| 能力 | `viewer`（仅门户） | `publisher`（可发布） | `admin`（管理员） |
|---|---|---|---|
| 打开门户 `/portal` | ✅ | ✅ | ✅ |
| 打开 `link` / `portal` 项目 | ✅ | ✅ | ✅ |
| 打开别人的 `private` 项目 | ❌ 302 回门户 | ❌ 302 回门户 | ✅ |
| `GET /api/projects`（项目列表） | ❌ 403 | ✅ 只返回自己的 | ✅ 全部 |
| 上传 / 建外链 / 改 / 删 项目 | ❌ 403 | ✅ 仅自己名下 | ✅ 任意 |
| 批量操作别人的项目 | ❌ | 计入 `skipped`，不报错 | ✅ |
| `GET /api/agents`、成员增删改、取 Key | ❌ 403 | ❌ 403 | ✅ |
| 站点设置 `/api/settings` | ❌ | ❌ 403 | ✅ |

判定实现：`backend/app/security.py`（`admin_user` / `publisher_user`）+
`projects.py::can_edit`（`admin` 或 `owner_id == 自己`）。
`viewer` 的 Key 能读**访客侧**（`/v/<slug>`、`/portal`），但进不了 `/api/projects`。

管理员给自己的 Key 就带着管理员权限——**这是最危险的一把钥匙**，
建议日常跑脚本用 `publisher` 账号，只有需要管成员时才用管理员 Key。

## 三、常见任务的调用方式

### 1. 部署一个目录

```bash
# CLI（会自动打包成 zip 上传，跳过 node_modules/.git 等）
python scripts/agentctl.py deploy ./dist --title "落地页 v3" --ttl 24 --tags 前端,v3 --visibility link
```

```bash
# 原始 API（multipart，注意 files 可重复）
curl -H "Authorization: Bearer pv_xxx" \
  -F "slug=landing-v3" -F "title=落地页 v3" -F "hours=24" \
  -F "visibility=link" -F "tags=前端,v3" \
  -F "files=@dist/index.html" \
  -F "files=@dist/assets/app.js" \
  https://<站点>/api/projects
```

- **入口规则**：只有 1 个文件时，那个文件就是入口（叫 `report.html` 也无所谓）；多个文件时根目录必须有
  `index.html`（或 `index.htm`），否则接口直接返回 `422`。别等部署完才发现打开是空白。
- `visibility`：`portal`（进门户）/ `link`（不进门户但可转发）/ `private`（只有自己）
- 不传 `hours` 时按可见性给默认寿命：门户 6h / 持链接 12h / 私有永久
- 同名 `slug` 再传一次 = 覆盖更新（保留原到期时间与归属）
- **标题不能重复**：你自己名下已经有一个同名项目时，再建会拿到 `409`，
  `detail` 里会写明占用这个名字的 slug。两条出路：想更新就用那个 slug 覆盖，想并存就换个名字。
  比较时忽略大小写与首尾空格；别人用同样的名字不影响你。
- **名字要短**：最多 **10 个中文字符（≈ 20 个英文字符）**，按显示宽度算（中文 1、半角 0.5）。
  门户卡片和列表只有一行，长名字会被截成省略号。上传时超长会**自动截短**（返回体里 `title`
  是真实落库的名字，跟传进去的不一样就说明被截了）；`set --title` 改名超长则直接 `422`。
  版本/环境放名字尾部（`落地页 v3`），客户名、时间、用途写 `--tags` 或 `--desc`。

### 2. 只登记一个外链（不发文件）

```bash
curl -X POST -H "Authorization: Bearer pv_xxx" -H "Content-Type: application/json" \
  -d '{"link_url":"https://figma.com/proto/xxx","title":"设计稿","hours":12,"visibility":"link"}' \
  https://<站点>/api/projects/link
```

`/v/<slug>` 与 `/p/<slug>/` 都会 302 跳到该外链，**跳之前记一次访问**，所以外链项目的访问数也有。
分享出去请给 `/v/<slug>` 短链（门户卡片和「复制链接」给的就是它）：直接给源站地址就统计不到了。
对访客而言仍然是一次跳转，没有中间页，也没有 iframe 空壳。

### 3. 改可见性 / 续期 / 打标签

```bash
# 单个
curl -X PATCH -H "Authorization: Bearer pv_xxx" -H "Content-Type: application/json" \
  -d '{"visibility":"private"}' https://<站点>/api/projects/landing-v3

# 续 48 小时 / 转永久
curl -X PATCH ... -d '{"hours":48}'  ...
curl -X PATCH ... -d '{"permanent":true}' ...

# 改项目名（≤10 个中文字符，超了 422；改名不动 slug，链接照旧）
curl -X PATCH ... -d '{"title":"落地页 v4"}' ...

# 批量（最多 500 个 slug）
curl -X POST -H "Authorization: Bearer pv_xxx" -H "Content-Type: application/json" \
  -d '{"slugs":["a","b","c"],"action":"extend","hours":24}' \
  https://<站点>/api/projects/bulk
```

`action` 取值：`delete` / `expire` / `block` / `permanent` / `extend` / `allow_download` /
`deny_download` / `visibility` / `tag_add`。

返回 `{"done":N,"skipped":M,"expired":K,"trimmed":T}`：`skipped` 是无权操作的项目数，
`expired` 是被改成门户可见但已经到期的项目数（需先续期才会出现在门户），
`trimmed` 是打标签时「凑满上限就停」的项目数（上限默认 6，管理员可在设置里调到 1–6）。

**标签有硬规则**（超了直接 422，不会悄悄截断）：

| 项 | 规则 |
|---|---|
| 数量 | 每个项目最多 6 个（设置里可调小到 1–6，`GET /api/meta` 的 `tags.max_per_project` 是当前值） |
| 长度 | 单个 1–12 字 |
| 字符 | 中英文、数字与 `+ # . - _`，不许空格 |
| 分隔 | `,` `，` `、` `;` `；` 或空格 |
| 归一化 | 全角转半角、英文转小写，`Vue`/`VUE`/`vue` 合并成一个 |
| 全站池 | 最多 300 个不同标签，池满只能复用已有标签 |

422 的 `detail` 是给人看的中文，直接转述给用户即可，例如
`每个项目最多 3 个标签，你填了 8 个`、`标签「数据/分析」含有不允许的字符`。

门户顶部那条标签栏另有显示上限（默认只放最常用的 12 个，`tags.bar_limit`，设置里可改），
跟「一个项目能打几个」是两回事，不用向用户解释成限制。

### 4. 查自己的项目 / 访问量

```bash
GET /api/projects?status=online&visibility=portal&sort=views&order=desc&limit=50
GET /api/projects/{slug}          # 详情：文件清单、14 天访问、事件流水
GET /api/stats/trend?days=14      # 访问趋势
```

`status`：`online`（默认，在用）/ `expired` / `permanent` / `deleted` / `all`。
`sort`：`created_at` / `updated_at` / `expires_at` / `views` / `downloads` / `size_bytes` / `title`。

### 5. 删除

```bash
DELETE /api/projects/{slug}     # 文件、zip、访问记录一起清
```

删除是不可恢复的，批量删之前先用 `GET /api/projects?status=expired` 确认清单。

### 6. 收藏夹：把项目分门别类

两级（收藏夹 → 子收藏夹）。**归类是幂等的**，重复放同一个夹不会出错。

```bash
# CLI
agentctl collections                        # 树：id / 直属数 / 合计 / 名字
agentctl collections add --name 办公         # 建一级夹
agentctl collections add --name 报表 --parent 办公
agentctl deploy ./dist --collection 办公     # 部署顺手归类（也可写 id）
agentctl set <slug> --collection 办公/报表   # 挪进去
agentctl set <slug> --no-collection         # 移出来
agentctl ls --collection 办公                # 只看这个夹（含子夹）

# 原始 API
GET    /api/collections                     # {items:[...], unassigned, total, visibility:{portal,link,private}}
POST   /api/collections                     # {"name":"办公","parent_id":null}
PATCH  /api/collections/{id}                # {"name":"...","parent_id":...}
DELETE /api/collections/{id}?with_projects=0
GET    /api/projects?collection=12          # 12 及其子夹；collection=none = 未归类
PATCH  /api/projects/{slug}                 # {"collection_id": 12} / {"collection_id": null}
```

- 想「连项目一起删」得显式 `with_projects=1`，默认只删壳、项目退回未归类；
- 建第三层会 422；同层重名会 409；
- `GET /api/projects?collection=abc`（既不是数字也不是 `none`）会 400，不会静默返回全部。

返回里的 `visibility` 是三档可见性的数量（三者之和 = `total`）。控制台侧栏把
「全部项目 / 门户可见 / 持链接 / 仅自己 / 未归类」做成了常驻分类，用的就是这几个数——
**API 侧没变**，筛可见性仍然走 `GET /api/projects?visibility=portal|link|private`，
只是控制台不再单独放一个可见性下拉（窄屏除外）。

### 7. 导入 / 导出浏览器书签

Chrome / Edge / Firefox / Safari 导出的 HTML 都能直接吃，**文件夹变收藏夹、书签变外链项目**。

```bash
# 先预览（不落库），确认条数与层级再真导
curl -H "Authorization: Bearer $KEY" -F "file=@bookmarks.html" -F "dry_run=1" \
     $BASE/api/import/bookmarks

# 真导：默认仅自己可见，可选 link / portal，可统一打标签，可指定落到哪个收藏夹
curl -H "Authorization: Bearer $KEY" -F "file=@bookmarks.html" \
     -F "visibility=private" -F "tag=书签" -F "parent_id=12" \
     $BASE/api/import/bookmarks

# 导回成书签（浏览器能直接导入）：?collection=12 只导这个夹
curl -H "Authorization: Bearer $KEY" -OJ "$BASE/api/export/bookmarks?collection=12"
```

要点：同一网址**重复导入自动跳过**（响应里的 `skipped_duplicate`），所以脚本可以放心重跑；
`javascript:` 之类的地址会被丢弃（`skipped_invalid`）。单文件 8MB、单次最多 500 条。

### 8. 管理员：备份 / 恢复

```bash
GET  /api/backup                              # 下载全站 zip（库 + 项目文件 + zip + 图标）
POST /api/backup/inspect   (multipart file)   # 先看包里有什么，再决定恢复
POST /api/backup/restore   (multipart file)   # 覆盖现网数据，旧数据进 data/.backup-before-restore-<时间>/
```

**这是破坏性操作，Agent 不该自己发起**：只在人明确说「用这个包恢复」时调用，
并且先 `inspect` 把 `counts` 报回去让人确认。成员 Key 调用一律 403。

### 9. 管理员：管成员

```bash
GET    /api/agents                     # 列表（含 key_label / key_last_used_at / key_uses）
POST   /api/agents                     # {"username","display_name","role","key_label","password"}
PATCH  /api/agents/{id}                # display_name / role / active / password / rotate_key / key_label
DELETE /api/agents/{id}                # 连同其名下项目一起删
GET    /api/agents/{id}/key            # 取回完整 Key
```

护栏：
- 不能改自己的角色，也不能删自己；
- 不会把最后一个管理员降级或停用；
- 非法角色返回 400；
- 删除成员会连带删除他名下全部项目文件。

## 四、错误码速查

| 状态码 | 含义 | 处理 |
|---|---|---|
| 401 | Key 无效 / 已轮换 / 成员被停用 | 检查 `key_label` 与 `key_last_used_at`，重新取 Key |
| 403 | 角色不够（`viewer` 摸项目接口、非管理员摸成员接口） | 换账号或提权 |
| 404 | 项目不存在，**或你没权限看这个私有项目**（仅出现在 API 与子资源上） | 私有项目只对作者和管理员开放；预览地址 `/v/` 遇到这种情况是 302 回门户，不是 404 |
| 409 | slug 冲突 / **项目名重复** / 账号已存在 | 同名就用那个 slug 覆盖更新；不同项目就换个名字 |
| 422 | 改名时项目名超长（>10 个中文字符）/ 入口文件缺失 / 图标格式不对 | 名字砍到 10 个中文字以内再来一次；上传场景不会 422，只会被截短 |
| 410 | 项目已到期（`/api/public/p/{slug}` 返回；`/v/` 页面本身是 302 回门户） | 续期后访问恢复 |
| 413 | 单项目超过 `MAX_UPLOAD_MB` / 书签文件超过 8MB | 拆包或调大上限 |
| 400 | `collection` 参数既不是 id 也不是 `none` | 用 `GET /api/collections` 拿到的 id，或直接传 `none` |

## 五、Agent 执行时的红线

1. **不要猜 Key**：拿不到就停下问人，别去翻 `config.json` 之外的路径。
2. **不要跨账号**：一把 Key 只干一个账号的事。需要管理员操作就单独要管理员 Key，
   不要用 publisher 的 Key 去试越权接口（会拿到 403，没有意义）。
3. **默认用 `link` 而不是 `portal`**：进门户意味着所有人都能逛到。
4. **交付前确认到期时间**：脚本部署完打印 `preview_url` 与 `expires_at`，
   客户验收场景建议 ≥ 24h。
5. **批量操作先 dry-run**：先用 `GET /api/projects?...` 拉清单确认命中范围，
   再发 `bulk`。`delete` 立刻生效、不可恢复。
6. **Key 泄漏的第一步是轮换**，不是改密码：`PATCH /api/agents/{id} {"rotate_key": true}`。

## 六、相关文档

- `docs/visibility.md`：三档可见性的完整判定表（谁能看、私有链接怎么打开）
- `docs/api.md`：接口一览（含收藏夹、书签导入导出、备份恢复）
- `SKILL.md`：把这套服务部署起来（运维侧）
