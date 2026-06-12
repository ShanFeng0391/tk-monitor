#!/usr/bin/env bash
# 在腾讯云轻量上配置 PG 每日备份 cron（上传 COS）
# 前置：已 clone 或拷贝本项目到 /opt/tiktok-monitor，并已配置 .env.server
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/tiktok-monitor}"
ENV_FILE="${APP_ROOT}/.env.server"
LOG_DIR="${APP_ROOT}/data/logs"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "缺少 ${ENV_FILE}，请从 scripts/tencent-lightweight/env.server.example 复制并填写" >&2
  exit 1
fi

mkdir -p "$LOG_DIR"
cp "$ENV_FILE" "${APP_ROOT}/.env"

cd "${APP_ROOT}/backend"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt -q
fi

CRON_LINE="0 4 * * * cd ${APP_ROOT}/backend && set -a && . ${ENV_FILE} && set +a && ${APP_ROOT}/backend/.venv/bin/python -m app.services.postgres_backup >> ${LOG_DIR}/backup.log 2>&1"
(crontab -l 2>/dev/null | grep -v "app.services.postgres_backup" || true; echo "$CRON_LINE") | crontab -

echo "已添加 crontab：每天 04:00 PG 备份 → COS"
echo "日志：${LOG_DIR}/backup.log"
echo "手动测试：cd ${APP_ROOT}/backend && set -a && . ${ENV_FILE} && set +a && .venv/bin/python -m app.services.postgres_backup"
