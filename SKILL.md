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
| `/download/<slug>/<文件相对路径>` | 单个文件下载；没开下载的项目 403，zip 类项目自动回落到整包 |
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
python cli/agentctl.py deploy ./dist --collection 办公          # 顺手归到收藏夹（也可写 id）
python cli/agentctl.py selfcheck                               # 建→探活→改私有→改回→续期→删除
```

`deploy` 传完会**自己去请求一次**这个地址，返回里带 `preview_url` 与 `http_status`
（`--no-verify` 可跳过）。`--json` 时 stdout 只有一行 JSON，退出码 0/1。

`--visibility` 三档：`link`（默认，持链接可见）、`portal`（进门户列表）、`private`（仅自己）。
`--expire-action` 两档：`block`（默认，到期停访留文件）、`delete`（到期删文件）。

同一成员名下**项目名不能重复**（忽略大小写/首尾空格），撞车返回 409 并点名占用的 slug；
覆盖更新同一个 slug 不算冲突，跨成员同名互不影响。

## 项目怎么起名

**名字要短：最多 10 个中文字符（≈ 20 个英文字符）。** 按显示宽度算，中文 1、半角 0.5，
所以在门户卡片、列表行、抽屉标题里都不会被截成省略号。

| 好 | 差 | 为什么 |
|---|---|---|
| `落地页 v3` | `最新版营销落地页（给客户看的那一版）` | 8 个字讲清了是什么 + 第几版 |
| `数据看板` | `数据可视化分析看板原型演示` | 卡片上只能显示一行 |
| `客户验收` | `李总那边明天下午要验收的项目` | 人名/时间属于说明或标签 |
| `figma 设计稿` | `https://figma.com/proto/xxxx` | URL 不是名字，放 `link_url` |

- 版本、环境这类区分度放进名字尾部（`落地页 v3` → `落地页 v4`），别堆在开头；
- 时间、客户名、用途这些细节写 `description` 或 `tags`，不占名字；
- 改名超长会被 `422` 拒绝，上传/建外链超长会**自动截短**（响应里给的是真实落库的名字）；
- 名字与 slug 无关：改名不动链接，`/v/<slug>` 永远不变。

## 收藏夹：给项目分门别类

左侧那一栏是**分类导航 + 收藏夹**二合一，点一下就筛；`⋯` 里能新建子夹 / 改名 / 删除，
勾选多个项目后底部能一键「移到收藏夹…」。

- 常驻分类：**全部项目 / 门户可见 / 持链接 / 仅自己 / 未归类**——按可见性和是否归类自动算，
  不用手动维护；数量跟列表页的总数同源（三档之和 = 全部项目）
- 再往下才是自己建的收藏夹（两级：**收藏夹 → 子收藏夹**）
- **侧栏三档 = 跳全站，工具栏下拉 = 夹内快筛**：点侧栏三档会跳出当前收藏夹看全站这一档；
  工具栏那个「可见性」下拉不换范围，是在当前夹里再筛（选中夹时文案变「本夹全部可见性」）。
  窗口窄于 1120px 侧栏收起时，工具栏另外补一个**归类下拉**兜底
- 管理员视角下侧栏**按成员分组**：自己的组排最前（组头有色点、夹数、折叠箭头），
  右上角成员下拉可只看某个人（只收侧栏、不改项目列表范围）；夹里混了别人的项目时数字后补 `+N`

控制台左侧导航栏右上角有一个折叠按钮（`‹` / `›`）：收起后只留图标，宽度 228px → 64px，
内容区跟着往左扩 164px；选择记在 localStorage，刷新后保持。

```bash
python cli/agentctl.py collections                       # 树 + 每个夹的直属/合计数量
python cli/agentctl.py collections add --name 办公        # 建一级夹
python cli/agentctl.py collections add --name 报表 --parent 办公   # 建子夹
python cli/agentctl.py ls --collection 办公               # 只看这个夹（含子夹）
python cli/agentctl.py set <slug> --collection 办公/报表  # 把项目挪进去
python cli/agentctl.py set <slug> --no-collection        # 移出来（回到未归类）
python cli/agentctl.py collections rm 办公 --with-projects  # 连项目一起删（默认只删壳）
```

- **只做两层**：再往下的层级建不出来（422）。数据结构没写死深度，以后要放开不用迁表。
- **删夹默认只删壳**：里面的项目退回「未归类」，不会跟着消失；要连项目一起删得显式说。
- **同名拦截**：同一层不允许两个同名夹（忽略大小写/首尾空格），撞上返回 409。
- **计数口径**：`count` 是直属项目数，`total` 含子夹；侧栏「全部项目」= 各夹合计 + 未归类，
  跟列表总数一致。非管理员只统计自己名下，看不到别人的项目数。
  管理员额外拿到 `count_own / count_foreign / total_foreign`（相对**看的人**：我名下 vs 别人名下），
  夹上那个 `+N` 就是 `total_foreign`。

## 导入 / 导出浏览器书签

Chrome / Edge / Firefox / Safari 导出的书签都是同一种 Netscape HTML，一个解析器全吃。

- 控制台项目页右上角「导入书签」：选文件 → **先预览**（可导入几条、几个收藏夹、跳过几个重复）→ 确认导入；
- 文件夹 → 收藏夹（一级 → 一级，二级 → 子夹，更深的折进第二级），书签 → **外链项目**；
- 默认 `visibility=private`（仅自己可见），导入时也能选持链接 / 门户，并可一批打同一个标签；
- 同一个网址重复导入**自动跳过**，反复导同一个文件不会造重复；
- 「导出」把当前收藏夹（含子集）导回成书签 HTML，能直接再导入浏览器。

```bash
curl -b cookiejar -F "file=@bookmarks.html" -F "dry_run=1" http://<host>:8080/api/import/bookmarks
curl -b cookiejar -OJ "http://<host>:8080/api/export/bookmarks?collection=3"
```

指定了「导入到某个收藏夹」时，只能再往下放一层：书签的一级文件夹变成它的子夹，更深的折进去，
免得做出第三层把项目藏到筛选管不到的地方。

## 备份与恢复

设置页「备份恢复」：一个 zip 带走 **数据库 + 项目文件 + 下载包 + 站点图标**。
数据库用 `sqlite3.backup()` 在线快照，正在写入也不会拷到半截。

```bash
curl -b cookiejar -OJ http://<host>:8080/api/backup                    # 打包下载
curl -b cookiejar -F "file=@preview-backup-xxx.zip" http://<host>:8080/api/backup/inspect   # 先看里面有什么
curl -b cookiejar -F "file=@preview-backup-xxx.zip" http://<host>:8080/api/backup/restore   # 覆盖恢复
```

恢复前会先把现网数据整体挪进 `data/.backup-before-restore-<时间>/`（只留最近 3 份），
所以**恢复错了还能手工挪回来**。只有管理员能做，成员一律 403。

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

浏览器控制台还能做：按成员/标签/类型/可见性（左侧分类）/状态筛选，按访问、创建、更新、到期、体积排序，
勾选后一键批量改可见性/续期/转永久/开放下载/删除，抽屉里看文件清单与 14 天访问趋势，
**点抽屉标题就能改项目名**（实时显示 当前宽度/10，超了保存按钮直接禁用）。

成员页：搜索（账号 / 显示名 / 绑定 Agent 名）、角色与状态筛选、按创建时间 / 最近登录 / 访问次数等排序
（可切升降序），一页 20 条（可切 20 / 50 / 100），筛选条件叠加后仍能清除回默认；
新建账号后弹窗里「复制登录命令」直接给一条能跑的 `agentctl login` 命令。

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
- 备份 = 设置页「打包下载」（或 `GET /api/backup`）；手工兜底也可以打包 `./data`，
  `sqlite3 data/db.sqlite3 ".backup backup.db"` 能单独热备数据库。
- 到期巡检每 60s；计数每 3s 落库，掉电最多丢 3 秒访问量。
- 日志：`docker compose logs -f --tail=100 preview`。
- **并发**：多 agent 同时上传安全（slug 级锁 + 每次上传独立临时目录 + 原子替换 + WinError 5/32 重试），
  同 slug 并发覆盖只有最后一次生效、不会写串。实测 18 路并发上传全 200，单次约 3.3s。
- **删除**：文件被占用时记录先删、目录留下，后台约 30 分钟内由孤儿清理收尾；启动时另清 `.tmp-*` / `.old-*`。
- **图标**：预览页优先用项目自带的 `favicon.ico/svg/png/apple-touch-icon.png`，否则退回站点图标。
- **升级 / 恢复的兼容**：`./data` 不动，启动时自动补列、改角色、收归无主项目；
  **上一个版本的备份包可以直接恢复**——换完当场跑迁移，不用重启；更老的包（缺 `kind` 这类核心列）
  会被 422 拒绝并说明缺什么，此时现网数据不动。恢复会把 `sessions` 一起换掉，**所有人都要重新登录**。

## 自检

```bash
python tests/smoke_test.py       --url http://127.0.0.1:8000   # 端到端
python tests/check_ttl.py        --url http://127.0.0.1:8000   # 三档默认时长与到期策略
python tests/check_roles.py      --url http://127.0.0.1:8000   # 三档角色接口/页面权限
python tests/check_migrate.py    --url http://127.0.0.1:8000   # 加列迁移、悬空外键自愈
python tests/check_portal.py     --url http://127.0.0.1:8000   # 门户结构回归
python tests/check_visibility.py --url http://127.0.0.1:8000   # 三档可见性 + 批量切换 + Key 绑定
python tests/check_cli.py        --url http://127.0.0.1:8000   # CLI 全命令 + 越权
python tests/check_concurrency.py --url http://127.0.0.1:8000  # 6 agent 并发 / 同 slug 抢占
python tests/check_copy.py       --url http://127.0.0.1:8000   # 复制按钮（需 chrome）
python tests/check_title.py      --url http://127.0.0.1:8000   # 同一成员重名拦截
python tests/check_rename.py     --url http://127.0.0.1:8000   # 改名链路 + 项目名长度规则
python tests/check_collections.py --url http://127.0.0.1:8000  # 收藏夹树 / 归类 / 筛选 / 删夹去向 / 侧栏折叠
python tests/check_bookmarks.py --url http://127.0.0.1:8000   # 书签导入预览/判重/导出回灌（需 chrome）
python tests/check_backup.py    --url http://127.0.0.1:8000   # 打包/预览/恢复/保留策略（会真恢复一次）
python tests/check_icon.py       --url http://127.0.0.1:8000   # 站点图标上传/恢复（含 .off 残骸回归，需 chrome）
python tests/check_owner_rail.py --url http://127.0.0.1:8000   # 收藏夹归属/侧栏分组与筛选/+N（需 chrome）
python tests/check_visfilter.py  --url http://127.0.0.1:8000   # 三档跳全站 vs 工具栏夹内快筛（需 chrome）
python tests/check_agents_filter.py --url http://127.0.0.1:8000 # 成员搜索/角色/状态/排序（需 chrome）
python tests/check_upload.py     --url http://127.0.0.1:8000   # 新建项目弹窗排版与标签上限（需 chrome）
python tests/check_license.py    --url http://127.0.0.1:8000   # LICENSE/NOTICE 与页面署名（需 chrome）
python tests/check_count_sync.py --url http://127.0.0.1:8000   # 删除/新建后侧栏收藏夹与分类计数当场同步（需 chrome）
python tests/check_compat.py    --url http://127.0.0.1:8000   # 老备份恢复+自动迁移/更老的包被拒/老书签/老字段/老 CLI（会覆盖数据，跑完自动恢复）
```

## 许可与署名

本项目以 **AGPL-3.0-only** 发布，全文见仓库根目录 [LICENSE](LICENSE)，
著作权与附加署名要求见 [NOTICE](NOTICE)：

- Copyright (C) 2026 Vita0519· <https://github.com/Vita0519/tmp-preview-deploy>
- 分发修改版要按 AGPL 提供完整源码；**对外提供服务也要给源码（第 13 条）**，自建自用同样适用；
- 依据 §7(b) 附加条款：任何再分发 / 修改版 / 对外服务都必须保留 LICENSE 与 NOTICE、
  保留「关于 / 许可」界面与登录页、门户页脚里指向本项目的署名（`Powered by tmp-preview` 不许删），
  并在显著位置注明「基于 tmp-preview 修改」及修改日期，不得用原作者名义背书；
- 闭源商用 / 白标分发需另取书面授权。

把这份 SKILL 交给 Agent 执行时，上面这几条同样成立：部署出来的站点页脚署名不能删。
