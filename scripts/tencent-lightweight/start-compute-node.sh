#!/usr/bin/env bash
# 腾讯云轻量 #2：API + Beat + Worker + sing-box（7×24 兜底 + 调度）
# 用法：复制 .env.hybrid 到本机后 bash scripts/tencent-lightweight/start-compute-node.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if [[ ! -f .env.hybrid ]]; then
  echo "缺少 .env.hybrid" >&2
  exit 1
fi
cp .env.hybrid .env

# 计算节点标识（可在外部 env 覆盖）
export COMPUTE_NODE_ID="${COMPUTE_NODE_ID:-cloud2}"
export COMPUTE_NODE_LABEL="${COMPUTE_NODE_LABEL:-轻量云 #2}"
export BEAT_ENABLED_ON_NODE="${BEAT_ENABLED_ON_NODE:-true}"
export CELERY_WORKER_NODE_PREFIX="${CELERY_WORKER_NODE_PREFIX:-cloud2}"
export POSTGRES_BACKUP_ENABLED="${POSTGRES_BACKUP_ENABLED:-false}"

grep -q "^COMPUTE_NODE_ID=" .env || echo "COMPUTE_NODE_ID=cloud2" >> .env
grep -q "^BEAT_ENABLED_ON_NODE=" .env || echo "BEAT_ENABLED_ON_NODE=true" >> .env

cd "$ROOT/backend"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt -q
fi

mkdir -p "$ROOT/data/logs" "$ROOT/data/hybrid"

stop() {
  for f in api beat worker; do
    pf="$ROOT/data/hybrid/$f.pid"
    if [[ -f "$pf" ]]; then
      kill "$(cat "$pf")" 2>/dev/null || true
      rm -f "$pf"
    fi
  done
}
stop

PY="$ROOT/backend/.venv/bin/python"
CELERY="$ROOT/backend/.venv/bin/celery"
LOG="$ROOT/data/logs"
CONCURRENCY="${CELERY_WORKER_CONCURRENCY:-10}"
if grep -q "^CELERY_WORKER_CONCURRENCY=" "$ROOT/.env"; then
  CONCURRENCY="$(grep "^CELERY_WORKER_CONCURRENCY=" "$ROOT/.env" | cut -d= -f2)"
fi
API_WORKERS="${API_UVICORN_WORKERS:-2}"
if grep -q "^API_UVICORN_WORKERS=" "$ROOT/.env"; then
  API_WORKERS="$(grep "^API_UVICORN_WORKERS=" "$ROOT/.env" | cut -d= -f2)"
fi

nohup "$PY" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "$API_WORKERS" \
  >"$LOG/cloud2-api.log" 2>"$LOG/cloud2-api.err.log" &
echo $! > "$ROOT/data/hybrid/api.pid"

if [[ "${BEAT_ENABLED_ON_NODE}" == "true" ]]; then
  nohup "$PY" -m app.tasks.beat_runner \
    >"$LOG/cloud2-beat.log" 2>"$LOG/cloud2-beat.err.log" &
  echo $! > "$ROOT/data/hybrid/beat.pid"
fi

nohup "$CELERY" -A app.tasks.celery_app worker -Q scrape --pool=prefork -c "$CONCURRENCY" \
  --loglevel=info -n "cloud2@%h" \
  >"$LOG/cloud2-worker.log" 2>"$LOG/cloud2-worker.err.log" &
echo $! > "$ROOT/data/hybrid/worker.pid"

echo "轻量#2 已启动 API+Beat+Worker(concurrency=$CONCURRENCY)"
echo "健康检查: curl -s http://127.0.0.1:8000/api/v1/system/health"
