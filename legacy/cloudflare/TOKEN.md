# Cloudflare API Token 权限清单

去 Dash → My Profile → API Tokens → Create Token → **Custom token**。
**不要**用 Global API Key。

## 必需权限

| 范围 (Scope) | 资源 (Resource) | 级别 | 用途 |
|---|---|---|---|
| Account | Workers Scripts | Edit | 部署 Worker、配置 cron |
| Account | Workers KV Storage | Edit | 建命名空间、读写清单与文件分片 |
| Zone | Workers Routes | Edit | 绑定自定义域名（可选） |
| Zone | DNS | Edit | 建自定义域名记录（可选） |

只用 workers.dev 地址的话，只需前两项。
资源范围选 **Include → 指定账号**（最小授权，不要给 All accounts）。

**不需要** R2 Storage 权限——本方案存 KV，无需绑卡。

## 需要的账号信息

- **Account ID**：URL `dash.cloudflare.com/<account_id>/...` 里那段，
  或 API：`GET /accounts`。`setup.sh` 不带 `--account` 时会自动取第一个。

## 验证 Token

```bash
curl -x http://172.17.0.1:20172 \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  https://api.cloudflare.com/client/v4/accounts
```

返回账号列表即有效。（`/user/tokens/verify` 在走代理时可能误报 Invalid，以 `/accounts` 为准。）

## 交付方式

用户通过**私聊**发 Token（不要发群里）。拿到后：

1. 不写进任何前端页面或仓库。
2. 建议用临时 Token，部署完删除。
3. 本地凭据（url + 口令 + account + kv_id）写到 `~/.openclaw/credentials/tmp-preview.json`，
   权限 600，不进 git。
