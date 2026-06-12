#!/usr/bin/env bash
# 在云 PostgreSQL 上执行数据库迁移（与 init-hybrid-db.ps1 等价）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if [[ ! -f .env.hybrid ]]; then
  echo "缺少 .env.hybrid" >&2
  exit 1
fi
cp .env.hybrid .env

if grep -qE '^LOCAL_MODE\s*=\s*true' .env; then
  echo "init-hybrid-db 需要 LOCAL_MODE=false" >&2
  exit 1
fi

cd "$ROOT/backend"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -r requirements.txt -q

echo ">> 连接 PostgreSQL 并执行迁移..."
.venv/bin/python -c "
import asyncio
from app.database_migrate import run_migrations
asyncio.run(run_migrations())
print('数据库迁移完成')
"
