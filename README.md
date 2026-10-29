# tmp-preview-deploy

把一个本地项目目录（HTML / JS / 静态站 / WebGL 作品等）**一键部署成临时预览 + 下载站**：带实时倒计时、默认 24 小时到期自动清理、管理员可随时改存活时长。

整套跑在 **Cloudflare Workers + KV** 上——一个 Worker + 一个 KV 命名空间，无需服务器、无需证书、无需绑卡开通 R2。

## 能干什么

- **门户首页**：项目卡片列表（整张卡片可点击），每秒刷新的实时倒计时（前端按服务端时间校准）
- **门户密码**：根路径需密码（复用 `ADMIN_TOKEN`，与 `/admin` 同一套 Cookie，登录一次通用）；子页面 `/<slug>/` 免密直连
- **项目本体**：`/<slug>/` 直接访问（HTML / JS / 图片 / 模型文件都行）
- **打包下载**：`/download/<slug>` 下载 zip，**默认关闭**，需管理员显式开启
- **到期策略**：默认 24 小时，可设具体小时或永久；到期行为可选 `block`（停访问保留文件）或 `delete`（删项目及文件），cron `*/10 * * * *` 执行
- **访问计数**：只统计项目首页 HTML 访问，采用抽样写入 + 每 10 分钟批量落库，规避 KV 免费额度 1000 写/天 的限制

## 目录结构

```
SKILL.md                     技能说明（完整使用手册）
assets/
  worker.js                  Worker 主程序（门户 / 子页面 / 上传 / 下载 / cron 清理）
  admin.js                   管理页前端
  wrangler.toml.tpl          wrangler 配置模板
references/
  architecture.md            架构设计说明
  cloudflare-token.md        Cloudflare API Token 权限清单
scripts/
  setup.sh                   首次搭建（建 KV、写配置、部署）
  deploy.py                  部署 / 新建项目到预览站
  admin.py                   管理已有项目（改时长、开关下载、查剩余）
  cf_deploy.py               底层 Cloudflare API 封装
```

## 快速开始

```bash
export CLOUDFLARE_API_TOKEN=xxx
export CLOUDFLARE_ACCOUNT_ID=xxx

bash scripts/setup.sh                 # 首次：建 KV + 部署 Worker
python scripts/deploy.py <目录>       # 部署一个新项目，默认 24 小时
python scripts/admin.py list          # 查看现有项目与剩余时长
```

详细参数与运维说明见 [SKILL.md](SKILL.md)，Token 权限见 [references/cloudflare-token.md](references/cloudflare-token.md)。

## 安全提示

`ADMIN_TOKEN`、`CLOUDFLARE_API_TOKEN` 等敏感值一律通过环境变量 / Worker secrets 注入，**不要**写进仓库。
