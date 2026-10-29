# 从 Cloudflare 迁移到本地

旧版把清单和文件都放在 Workers KV 里（布局见 `legacy/cloudflare/worker.js` 顶部注释）。
`migrate/from_cloudflare.py` 直接读 KV，把文件拼回磁盘、把元数据写进本地 SQLite，
**保留原 slug**，所以旧链接 `/p/<slug>/` 的路径结构一致（只是域名从 workers.dev 换成本机）。

## 1. 准备凭据

Cloudflare Dashboard → My Profile → API Tokens → Create Token → Custom token：

| 权限 | 用途 |
|---|---|
| Account · Workers KV Storage · **Read** | 列出 key、读 meta / file / chunk |

还需要：

- **Account ID**：`dash.cloudflare.com/<account_id>/...` 里那段
- **KV Namespace ID**：Workers & Pages → KV → 对应命名空间，或 `wrangler kv:namespace list`

## 2. 备份旧数据（强烈建议）

```bash
# 本地已有 ./data 的话先备份
tar czf data-backup-$(date +%Y%m%d).tgz data 2>/dev/null || true
```

旧 Worker 不要删——迁移验证完再下线，随时可回滚。

## 3. 跑迁移

```bash
docker compose up -d          # 先启动一次，创建管理员账号和数据库
docker compose stop           # 再停掉，避免后台任务与迁移抢写

export CF_API_TOKEN=xxx
export CF_ACCOUNT_ID=xxx
export CF_KV_NAMESPACE_ID=xxx

python migrate/from_cloudflare.py --dry-run           # 只列清单，确认能读到项目
python migrate/from_cloudflare.py --agent admin       # 真正导入
python migrate/from_cloudflare.py --only landing-v2   # 只补一个项目

docker compose start
```

依赖：本机有 Python 3.10+ 即可（脚本只用标准库 + 本地 `backend/app`）。
若在容器里跑：`docker compose run --rm preview python migrate/from_cloudflare.py ...`
（需要把 KV 凭据传给容器）。

## 4. 字段映射

| Cloudflare KV | 本地 |
|---|---|
| `meta:<slug>.name` | `projects.title` |
| `.desc` | `description` |
| `.files` / `.size` | `file_count` / `size_bytes` |
| `.zipName` | `zip_name` + `has_zip` |
| `.allowDownload` | `allow_download` |
| `.expireAction` | `expire_action` |
| `.createdAt` / `.updatedAt` | `created_at` / `updated_at` |
| `.expireAt`（0=永久） | `expires_at`（NULL=永久） |
| `.link` | `link_url` + `kind='link'` |
| `file:<slug>:<hash>` + `chunk:*` | `data/projects/<slug>/<path>` |
| 特殊路径 `__zip__` | `data/zips/<slug>.zip` |
| `views:<slug>` + `pv:d:<slug>` | `projects.views` |

`pathHash` 在脚本里按 UTF-16 码元重算，和旧 Worker 的 FNV-1a 结果完全一致，
所以文件名含中文也不会找不到分片。

## 5. 验证

```bash
# 项目数、访问数
curl -s localhost:8080/api/meta

# 抽查预览（浏览器打开，确认样式与资源加载正常）
open http://localhost:8080/v/<slug>

# 抽查下载
curl -I localhost:8080/download/<slug>
```

管理台里对照一下：归属成员、标签（旧数据没有标签，需要重新打）、到期时间。

## 6. 已知差异

- **访问数**：旧版是 1/20 抽样计数，数值本身是估算，迁移后是精确计数，量级一致但不会完全相同。
- **标签**：旧版用名字关键词做"快捷标签"，没有持久化标签字段，迁移后标签为空，可在管理台批量补。
- **可见性**：旧版门户=全员可见 + 密码；迁移后默认 `visibility='link'`（持链接可见），
  需要进门户的项目改成「门户可见」，并决定是否开启 `/portal` 公开访问。
- **URL**：`/admin` 变为控制台首页 `/`；旧的 `/<slug>/` 变为 `/p/<slug>/` 与 `/v/<slug>`。

## 7. 回滚

本地验证不通过时：不用动旧 Worker，DNS / 分享链接继续指向 workers.dev 即可；
本地 `docker compose down` 后 `rm -rf data` 重新来一遍。
