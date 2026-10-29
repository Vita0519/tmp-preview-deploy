# 由 tmp-preview-deploy skill 生成
name = "tmp-preview"
main = "worker.js"
compatibility_date = "2024-11-01"

[vars]
SITE_TITLE = "临时预览服务"
DEFAULT_TTL_H = "24"
LOCAL_SITE_URL = "https://__DOMAIN__"
ADMIN_TOKEN = "__ADMIN_TOKEN__"

[[kv_namespaces]]
binding = "KV"
id = "__KV_ID__"

[triggers]
crons = ["*/10 * * * *"]

[observability]
enabled = true
