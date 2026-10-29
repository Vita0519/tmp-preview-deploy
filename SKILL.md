---
name: tmp-preview-deploy
description: 把一个本地项目目录（HTML/JS/静态站/WebGL 作品等）一键部署成临时预览+下载站，带实时倒计时、默认 24 小时到期自动删除、管理员可改存活时长。基于 Cloudflare Workers + KV，单个 Worker 承载动态门户、实时倒计时 API、静态资源、zip 下载、上传接口和定时清理，无需服务器、证书，也无需绑卡开通 R2。当用户说「部署预览」「临时部署」「分享给客户验收」「上传项目让人预览下载」「搞个类似 test.aitell.vip 的站」「24 小时后自动删除的预览链接」「部署到 Cloudflare/Workers」「workers.dev 预览站」时使用。也用于首次搭建该站（setup.sh）、增删项目、调整到期时间、查剩余时长。
---

# tmp-preview-deploy

临时预览 / 下载站，整套跑在 Cloudflare 上：**一个 Worker + 一个 KV 命名空间**。

- 门户首页：项目卡片列表（**整张卡片可点击跳转**）+ **每秒刷新的实时倒计时**（前端按服务端时间校准）
- **门户根路径需密码**（复用 `ADMIN_TOKEN`，与 `/admin` 同一套 Cookie，登录一次通用）；**子页面 `/<slug>/` 与 `/download/<slug>` 仍免密直连** —— 密码只为防止有人一次把整站清单抓光
- 子页面：`/<slug>/` 直接访问项目本体（HTML/JS/图片/模型文件都行）
- 下载：`/download/<slug>` 打包 zip 下载。**默认关闭**，需管理员显式开启（`--allow-download` 或管理页开关）
- 默认 24 小时到期；时长可设为**具体小时**或**永久**（`--forever` / `0`）
- **到期行为可选**：`block`（默认，停止访问但保留文件）或 `delete`（删掉项目及文件）；cron `*/10 * * * *` 执行
- 门户标题右侧有 **⚙ 设置图标** 进管理页
- **访问计数（10-09 省额度改造）**：每个项目记录访问次数（只计项目首页文档的 HTML 访问，子资源/SPA 内部跳转不重复计）。门户卡片显示 **👁 访问次数 + 🕒 创建时间（相对时间，hover 看绝对）**，工具栏有 **排序切换：按访问次数（默认）/ 按创建时间**；管理页表格也有 **访问 + 创建时间** 列与同一排序切换。外链项目不统计（显示 —）。
  - **省 KV 写额度设计（重要）**：免费额度仅 **1000 写/天**，旧的「每次访问写一次」很快打爆（会报 `KV put() limit exceeded for the day`，随后所有写操作 1101）。现改为两层：
    1. **抽样计数**：仅约 **1/20** 的访问触发一次写入（`VIEW_SAMPLE_RATE=20`），那次把 `+20` 记到待写入增量 `pv:d:<slug>`；其余访问零写入。总次数 ≈ 写入次数 × 20（大数定律，误差小）。
    2. **批量落库**：主计数 `views:<slug>` 由 flush 合并落库（cron `*/10` 自动 + 管理端可手动），把「每次访问 1 写」压缩为「每 10 分钟 ≤1 写/项目」。
  - 展示值 = 已落库 `views:<slug>` + 待写入增量 `pv:d:<slug>`（最终一致，有延迟，不追求精确及时）。flush 逐项 try/catch：额度耗尽时增量保留、下次再落，**绝不丢数据、不再 500**。删除项目时两个 key 一并删。
  - 手动落库：`scripts/admin.py flush-views`（或 POST `/api/admin/flush-views`）。调整抽样率改 `assets/worker.js` 的 `VIEW_SAMPLE_RATE` 后重新部署。
- 管理页 `/admin`：口令登录（**默认隐藏，带 👁 显隐切换；登录状态保存 30 天，下次免输**）、**搜索框**（名/slug）+ 计数、**新增项目**面板（可开可收）、退出登录
- **新增项目（直接在后台建）**：填显示名/URL段/说明/时长/到期行为/下载开关，选择或拖拽文件（支持整个文件夹、保留目录结构），可选自动打 zip；上传即建好并上线
- **每个项目可单独设时长**：每行有独立小时输入框 + `设为`；也有 `设为永久|取消永久` / `到期停访|到期删除` / `删除`；顶部还有全局 `读取/刷新` 与 `全部重设为该时长`
- **手机端**：表格自动变卡片布局，字段带标签，操作按钮两行不拥挤；新增项目表单也单列自适应
- 门户工具栏：**搜索**（名/说明/路径）+ **时长筛选**（全部/永久/24h内/7天内/可下载）+ **网格⇄列表视图切换**（自动记忆）

> ⚠️ **门户卡片是 `<div data-card>` 而非 `<a>`**。因为卡片里含下载按钮 `<a class="dl">`，HTML 不允许 a 嵌套 a，一旦巢套浏览器会提前闭合外层标签、**下载按钮位置错乱**（这正是当初的显示 bug）。点击/回车由 `#grid` 事件委托处理。

**存储用 KV 而非 R2**：R2 首次开通需要绑卡，很多账号（尤其临时/测试账号）没有卡，KV 不需要。
文件按 18MB 分片、base64 存进 KV。KV 免费额度：读 10 万次/天、写 1000 次/天、存储 1GB。
**适合中小型项目**（单站 < 100MB）。需要托管大文件（视频/大模型）时再考虑 R2。

架构细节见 `references/architecture.md`。Cloudflare Token 权限清单见 `references/cloudflare-token.md`。

## 首次部署（每个账号只做一次）

```bash
export CLOUDFLARE_API_TOKEN=xxx
scripts/setup.sh --domain <预览域名> --admin-token '<自己定的强口令>' \
                 --title '测试预览服务' --ttl 24
```

可选参数：`--account <id>`（不填自动取第一个账号）、`--script tmp-preview`、`--proxy http://172.17.0.1:20172`（国内网络必需）。

`setup.sh` 会：建 KV 命名空间 → 通过 REST API 部署 Worker → 配 cron → 写本地凭据到 `~/.openclaw/credentials/tmp-preview.json`。幂等。

**执行前必须向用户索取**：Cloudflare API Token（权限见 references/cloudflare-token.md）。**不要**收 Global API Key。

部署后 `curl <地址>/api/projects` 应返回 `{"ok":true,...}`，打开门户确认倒计时在跳。

### 访问地址

- **本实例固定用 `https://tmp.allfather.top/`**（2026-10-08 起为默认，微信里可直接打开）。所有子项目链接都用这个域名，配置已写入 `~/.openclaw/credentials/tmp-preview.json` 的 `url`，`deploy.py`/`admin.py` 自动读取。
- 自动启用 `<script>.<账号workers.dev子域>.workers.dev`，无需域名即可用。
- 换/加自定义域名：控制台 Workers → tmp-preview → Settings → **Domains & Routes** 添加；或 CF API `PUT /accounts/<acc>/workers/domains`（body `{zone_id,hostname,service:"tmp-preview",environment:"production"}`）。绑完后把 `LOCAL_SITE_URL` 改成 `https://<新域名>` 重跑 `cf_deploy.py`（**只改这个变量不会让域名生效**，它只管错误页返回链接）。

## 日常使用

上传（`--ttl` 单位小时，支持小数；`--forever` 永久；省略用服务端默认 24h）：

```bash
scripts/deploy.py ./my-project --slug demo --name "演示项目" --desc "客户验收" --ttl 24 --zip
scripts/deploy.py ./long-term --slug docs --name "长期文档" --forever         # 永久
scripts/deploy.py ./temp --slug tmp --name "临时" --ttl 6 --expire-action delete  # 到期即删
```

**下载默认关闭**：`--zip` 只生成整包（供管理员以后按需开放），门户不会自动出现下载按钮。
要上传时就开放下载，加 `--allow-download`。之后也能在管理页/CLI 随时开关。

**外链卡片（只登记一个 URL，不传文件）**：

```bash
scripts/deploy.py --link umami-three-taupe.vercel.app --slug umami --name "umami 统计面板" --forever
```

门户里这类卡片显示「外链」徽标，点击在新标签打开外部站点。后台「新增项目」面板也有「外部链接 URL」输入框 + 「创建外链」按钮。适合把外部部署（如 Vercel 项目）统一收进门户。

**到期行为**（`--expire-action`）：
- `block`（默认）——到期后停止访问，但**文件保留**，管理页可手动删除或续期
- `delete`——到期后连同文件一起删除

`deploy.py` 自动跳过 `.git`/`node_modules`/`__pycache__`，保留子目录结构，要求根目录有 `index.html`（否则加 `--no-index`）。输出预览链接 + 下载链接 + 到期时间。同名 slug 重传即覆盖，用户刷新见新版。

管理：

```bash
scripts/admin.py list                # 所有项目 + 剩余时间 + 下载/到期行为状态
scripts/admin.py ttl demo 48         # 改成 48 小时后到期
scripts/admin.py ttl demo 0          # 设为永久
scripts/admin.py ttl-all 6          # 全部重设为 6 小时
scripts/admin.py action demo delete  # 到期后删除（默认 block=停访保留）
scripts/admin.py download demo on    # 开放下载
scripts/admin.py download demo off   # 关闭下载
scripts/admin.py delete demo         # 立即删除
scripts/admin.py views demo          # 查看访问次数
scripts/admin.py views demo 0        # 访问次数清零
scripts/admin.py flush-views         # 把待写入增量合并落库（同 cron 逻辑）
scripts/admin.py open demo           # 打印预览链接
```

`deploy.py` / `admin.py` 支持 `--url` / `--token` 或环境变量 `TMP_PREVIEW_URL` / `TMP_PREVIEW_TOKEN`。

## 关键约束

- **zip 只在 `--zip` 时生成**；**下载按钮默认不显示**，必须在管理页打开「下载开关」或 `admin.py download <slug> on` 才出现。没生成 zip 的项目开了开关也没得下。
- 门户卡片整张可点，点击**新窗口/新标签**打开 `/<slug>/`；卡片带 **📋 复制**按钮（一键复制子项目绝对链接）与下载按钮，两者独立，点它们不会触发跳转。
- KV 单值上限 25MB；脚本按 18MB 原始字节分片，单文件理论上限较大，但**总站建议 < 100MB**，否则上传慢且耗 KV 写额度（免费 1000 写/天）。
- 重新上传同名 slug 会先清空旧分片再写新的。
- **改 TTL 只影响倒计时和到期时间，不删已传文件**。
- **永久项目**（`--forever` / `ttl 0`）不会被 cron 动，需手动删除。
- `/admin` 口令即 `ADMIN_TOKEN`；用 `?token=<口令>` 访问一次会种 HttpOnly Cookie，之后免输。上传接口 `/upload` 需要 `x-admin-token` 头，别把口令写进前端。
- cron 是 `*/10 * * * *`，到期后最多延迟 10 分钟被清理。
- **根路径鉴权**：`/` 与 `/api/projects` 需要密码（= `ADMIN_TOKEN`）。未登录访问 `/` 出密码页，`/api/projects` 返回 401。登录方式：① 密码页表单 POST `/api/portal/login`；② `GET /?token=<口令>`（302 种 `pp_token` Cookie，30 天）。退出：`GET /?logout=1`。**`/<slug>/` 与 `/download/<slug>` 不受影响，保持公开直连**。改这块只动 `assets/worker.js`，改完必须用 `cf_deploy.py` 重 PUT Worker 才生效。

## 排查

| 现象 | 原因 / 处理 |
|---|---|
| 部署 `Authentication error` | Token 权限不足或 `--account` 错误 |
| 上传后门户已列出但页面 404 | 根目录没有 `index.html`，或 slug 输错 |
| `Missing chunk` | 上传中断过，重新 `deploy.py` 覆盖 |
| 访问次数不涨 | 只有项目首页文档（`index.html` 的 HTML GET）计入：直接开 `/<slug>/` 才算，子资源/接口不计；且计数是**抽样+最终一致**（约 1/20 抽样、每 10 分钟落库），不精确及时是设计如此。免费额度 1000 写/天，超出会被拒写（增量保留不丢） |
| 到期没删 | cron 延迟最多 10 分钟；另外默认是 `block`（停访保留），只有设了 `delete` 才物理删 |
| 访问地址打不开 | 用 workers.dev 地址试；自定义域名需先绑定 |
| wrangler 报 fetch failed | 别用 wrangler，`setup.sh` 走 REST API 更稳 |

## 本地验证（不碰线上）

```bash
cd <临时目录> && npm i wrangler@3
cp assets/worker.js assets/admin.js .
# 按 assets/wrangler.toml.tpl 生成 wrangler.toml（kv id 随便填，本地模拟）
npx wrangler dev --local --port 8790 --test-scheduled
# 另开终端:
TMP_PREVIEW_URL=http://127.0.0.1:8790 TMP_PREVIEW_TOKEN=<ADMIN_TOKEN> \
  python3 scripts/deploy.py ./demo --zip --ttl 0.01
curl "http://127.0.0.1:8790/__scheduled?cron=*/10+*+*+*+*"   # 手动触发清理
```
