#!/usr/bin/env bash
# PostgreSQL 备份到本地 + OSS（轻量云 / Linux）
# Usage: ./scripts/backup-postgres.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .env.hybrid ]]; then
  cp .env.hybrid .env
elif [[ ! -f .env ]]; then
  echo "缺少 .env 或 .env.hybrid" >&2
  exit 1
fi

cd "$ROOT/backend"
if [[ ! -d .venv ]]; then
  echo "请先创建 venv 并安装 requirements.txt" >&2
  exit 1
fi

./.venv/bin/python -m app.services.postgres_backup
