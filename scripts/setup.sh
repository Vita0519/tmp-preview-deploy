#!/usr/bin/env bash
# tmp-preview-deploy —— 一次性部署（KV 存储，无需绑卡）
#
# 用法:
#   export CLOUDFLARE_API_TOKEN=xxx
#   ./setup.sh --domain <预览域名> --admin-token '<强口令>'
#              [--account <id>] [--title '临时预览服务'] [--ttl 24]
#              [--proxy http://172.17.0.1:20172]
#
# --domain 只影响门户里显示的项目绝对地址；实际访问地址由
#   * workers.dev 子域（自动启用），或
#   * 控制台绑定的自定义域名
# 决定。R2 未开通也不影响。
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$HERE/.." && pwd)"

DOMAIN=""
ADMIN_TOKEN=""
ACCOUNT=""
TITLE="临时预览服务"
TTL="24"
SCRIPT="tmp-preview"
PROXY="${HTTPS_PROXY:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain) DOMAIN="$2"; shift 2;;
    --account) ACCOUNT="$2"; shift 2;;
    --admin-token) ADMIN_TOKEN="$2"; shift 2;;
    --title) TITLE="$2"; shift 2;;
    --ttl) TTL="$2"; shift 2;;
    --script) SCRIPT="$2"; shift 2;;
    --proxy) PROXY="$2"; shift 2;;
    *) echo "未知参数: $1" >&2; exit 2;;
  esac
done

: "${CLOUDFLARE_API_TOKEN:?请设置 CLOUDFLARE_API_TOKEN}"

api() { # method path [--data d]
  local m="$1" p="$2"; shift 2
  local args=(-s -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN")
  [[ -n "$PROXY" ]] && args+=(-x "$PROXY")
  if [[ "${1:-}" == "--data" ]]; then
    args+=(-H 'content-type: application/json' -d "$2" -X "$m")
  else
    args+=(-X "$m")
  fi
  curl "${args[@]}" "https://api.cloudflare.com/client/v4$p"
}

if [[ -z "$ACCOUNT" ]]; then
  ACCOUNT=$(api GET /accounts | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['result'][0]['id'] if d.get('result') else '')")
fi
: "${ACCOUNT:?无法获取 account id，请用 --account 指定}"

if [[ -z "$ADMIN_TOKEN" ]]; then
  ADMIN_TOKEN=$(python3 -c "import secrets;print(secrets.token_urlsafe(18))")
  echo "⚠️  未指定 --admin-token，已生成：$ADMIN_TOKEN"
fi

echo "==> 1/4 准备 KV 命名空间"
KV_ID=$(api GET "/accounts/$ACCOUNT/storage/kv/namespaces" | python3 -c "
import sys,json
d=json.load(sys.stdin)
for n in d.get('result',[]):
    if n['title']=='tmp-preview-registry': print(n['id']); break
")
if [[ -z "$KV_ID" ]]; then
  KV_ID=$(api POST "/accounts/$ACCOUNT/storage/kv/namespaces" --data '{"title":"tmp-preview-registry"}' \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['result']['id'] if d.get('success') else '')")
fi
[[ -z "$KV_ID" ]] && { echo "❌ 创建 KV 失败" >&2; exit 1; }
echo "   KV id: $KV_ID"

echo "==> 2/4 生成 wrangler.toml（本地留档）"
WORK="$HERE/.deploy"
mkdir -p "$WORK"
sed -e "s|__DOMAIN__|${DOMAIN:-localhost}|g" \
    -e "s|__ADMIN_TOKEN__|$ADMIN_TOKEN|g" \
    -e "s|__KV_ID__|$KV_ID|g" \
    -e "s|SITE_TITLE = .*|SITE_TITLE = \"$TITLE\"|" \
    -e "s|DEFAULT_TTL_H = .*|DEFAULT_TTL_H = \"$TTL\"|" \
    -e "s|name = \"tmp-preview\"|name = \"$SCRIPT\"|" \
    "$SKILL_DIR/assets/wrangler.toml.tpl" > "$WORK/wrangler.toml"

echo "==> 3/4 通过 REST API 部署 Worker"
SITE_URL=""
[[ -n "$DOMAIN" ]] && SITE_URL="https://$DOMAIN"
python3 "$HERE/cf_deploy.py" \
  --account "$ACCOUNT" --script "$SCRIPT" --admin-token "$ADMIN_TOKEN" \
  --kv-id "$KV_ID" --title "$TITLE" --ttl "$TTL" --site-url "$SITE_URL" \
  ${PROXY:+--proxy "$PROXY"}

echo "==> 4/4 写入本地凭据"
CRED_DIR="$HOME/.openclaw/credentials"
mkdir -p "$CRED_DIR"
URL="${SITE_URL:-}"
if [[ -z "$URL" ]]; then
  SUB=$(api GET "/accounts/$ACCOUNT/workers/subdomain" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['result']['subdomain'] if d.get('success') and d.get('result') else '')")
  [[ -n "$SUB" ]] && URL="https://$SCRIPT.$SUB.workers.dev"
fi
cat > "$CRED_DIR/tmp-preview.json" <<EOF
{"url": "$URL", "token": "$ADMIN_TOKEN", "account": "$ACCOUNT", "kv_id": "$KV_ID", "script": "$SCRIPT", "proxy": "$PROXY"}
EOF
cat > "$HERE/preview.json" <<EOF
{"url": "$URL", "token": "$ADMIN_TOKEN", "proxy": "$PROXY"}
EOF
chmod 600 "$CRED_DIR/tmp-preview.json" "$HERE/preview.json"

echo
echo "✅ 部署完成"
echo "   访问地址: ${URL:-（请到控制台绑定自定义域名后填写）}"
echo "   管理页  : ${URL:-}<域名>/admin"
echo "   管理员口令: $ADMIN_TOKEN"
echo "   本地凭据: $CRED_DIR/tmp-preview.json"
echo "   上传    : python3 $SKILL_DIR/scripts/deploy.py <目录> --zip --ttl 24"
