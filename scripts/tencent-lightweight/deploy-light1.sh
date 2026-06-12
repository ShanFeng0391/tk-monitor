#!/usr/bin/env bash
# 轻量 #1 一键部署：PG + Redis +（可选）PG 备份 cron
# 在宝塔 #1 终端粘贴一条命令即可（见 docs/TENCENT-LIGHTWEIGHT.md）
#
# 用法：
#   bash scripts/tencent-lightweight/deploy-light1.sh
# 或先 cp deploy.conf.example deploy.conf 填好密码后无交互运行
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/load-deploy-conf.sh"

GIT_REPO="${GIT_REPO:-https://github.com/ShanFeng0391/tk-monitor.git}"
APP_ROOT="${APP_ROOT_LIGHT1:-/opt/tk-monitor}"
LIGHT1="${LIGHT1_IP:-81.70.169.128}"
LIGHT2="${LIGHT2_IP:-120.53.91.39}"

if [[ $EUID -ne 0 ]]; then
  echo "请用 root 运行（宝塔终端默认是 root）" >&2
  exit 1
fi

echo "=== 轻量 #1 一键部署 (PG + Redis) ==="
echo "目标目录: $APP_ROOT"
echo "本机 IP:  $LIGHT1"
echo "轻量 #2:  $LIGHT2"

prompt_if_empty DB_PASS "PostgreSQL 密码 (请记下来，#2 也要用)" true
prompt_if_empty REDIS_PASS "Redis 密码 (请记下来，#2 也要用)" true

CLIENT_IPS="${LIGHT2}/32"
if [[ -n "${LOCAL_CLIENT_IP:-}" ]]; then
  CLIENT_IPS="${LOCAL_CLIENT_IP}/32,${CLIENT_IPS}"
fi
echo ">> 数据库允许连接: $CLIENT_IPS"
echo "   （请确认腾讯云安全组 #1 已放行 5432/6379 → $CLIENT_IPS）"

mkdir -p "$(dirname "$APP_ROOT")"
if [[ ! -d "$APP_ROOT/.git" ]]; then
  echo ">> git clone ..."
  git clone "$GIT_REPO" "$APP_ROOT"
else
  echo ">> 更新代码 ..."
  cd "$APP_ROOT"
  git pull --ff-only || true
fi

export DB_PASS REDIS_PASS CLIENT_IPS
bash "$APP_ROOT/scripts/tencent-lightweight/setup-server.sh"

# 可选：PG 备份 cron → COS
if [[ -n "${COS_SECRET_ID:-}" && -n "${COS_SECRET_KEY:-}" ]]; then
  echo ">> 配置 PG 备份 cron → COS ..."
  ENV_SERVER="$APP_ROOT/.env.server"
  cat >"$ENV_SERVER" <<EOF
DATABASE_URL_SYNC=postgresql://tiktok_monitor:${DB_PASS}@127.0.0.1:5432/tiktok_monitor
MINIO_ENDPOINT=${COS_ENDPOINT:-cos.ap-beijing.myqcloud.com}
MINIO_ACCESS_KEY=${COS_SECRET_ID}
MINIO_SECRET_KEY=${COS_SECRET_KEY}
MINIO_BUCKET=${COS_BUCKET:-tk-monitor888-1333628464}
MINIO_SECURE=true
POSTGRES_BACKUP_ENABLED=true
POSTGRES_BACKUP_KEEP_LOCAL=3
POSTGRES_BACKUP_KEEP_REMOTE=14
POSTGRES_BACKUP_BUCKET_PREFIX=backups/postgres
LOCAL_MODE=false
DATA_DIR=${APP_ROOT}/data
EOF
  chmod 600 "$ENV_SERVER"
  APP_ROOT="$APP_ROOT" bash "$APP_ROOT/scripts/tencent-lightweight/setup-cron.sh"
else
  echo ""
  echo ">> 跳过 PG 备份 cron（deploy.conf 未填 COS_SECRET_ID/KEY，或交互模式未提供）"
  echo "   可在 #1 填好 deploy.conf 后重新运行本脚本，或手动 setup-cron.sh"
fi

echo ""
echo "=== 轻量 #1 部署完成 ==="
echo "PostgreSQL / Redis 已在 ${LIGHT1} 监听"
echo "下一步：在轻量 #2 运行 deploy-light2.sh"
echo "  git clone ${GIT_REPO} ${APP_ROOT_LIGHT2:-/www/wwwroot/tk-monitor}"
echo "  cd ${APP_ROOT_LIGHT2:-/www/wwwroot/tk-monitor} && bash scripts/tencent-lightweight/deploy-light2.sh"
