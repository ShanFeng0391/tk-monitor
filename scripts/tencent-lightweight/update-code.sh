#!/usr/bin/env bash
# 腾讯云轻量 #2：拉代码 → 依赖 → 前端构建 → 重启 API+Beat+Worker
# 用法（在项目根目录）:
#   bash scripts/tencent-lightweight/update-code.sh
#   bash scripts/tencent-lightweight/update-code.sh --backend-only
#   bash scripts/tencent-lightweight/update-code.sh --skip-git
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

BACKEND_ONLY=false
SKIP_GIT=false
for arg in "$@"; do
  case "$arg" in
    --backend-only) BACKEND_ONLY=true ;;
    --skip-git) SKIP_GIT=true ;;
    -h|--help)
      echo "用法: bash scripts/tencent-lightweight/update-code.sh [--backend-only] [--skip-git]"
      exit 0
      ;;
  esac
done

if [[ ! -f .env.hybrid ]]; then
  echo "缺少 .env.hybrid" >&2
  exit 1
fi

echo "=== 轻量#2 代码更新 ==="

if [[ "$SKIP_GIT" != true ]] && [[ -d .git ]]; then
  branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
  echo ">> git pull origin $branch"
  git fetch origin "$branch"
  git pull --ff-only origin "$branch"
elif [[ "$SKIP_GIT" == true ]]; then
  echo ">> 跳过 git pull"
else
  echo ">> 非 Git 目录，跳过 pull"
fi

echo ">> 安装后端依赖"
cd "$ROOT/backend"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -r requirements.txt -q

if [[ "$BACKEND_ONLY" != true ]]; then
  echo ">> 构建前端"
  cd "$ROOT/frontend"
  if [[ ! -d node_modules ]]; then
    npm install --silent
  fi
  npm run build
  if [[ ! -f dist/index.html ]]; then
    echo "前端构建失败" >&2
    exit 1
  fi
else
  echo ">> 跳过后端构建（--backend-only）"
fi

echo ">> 重启 API + Beat + Worker"
bash "$ROOT/scripts/tencent-lightweight/start-compute-node.sh"

sleep 4
for i in 1 2 3 4 5; do
  if curl -sf "http://127.0.0.1:8000/api/v1/system/health" | grep -q healthy; then
    echo "=== 更新完成，健康检查通过 ==="
    exit 0
  fi
  echo ">> 等待 API 就绪 (${i}/5)..."
  sleep 3
done
echo "=== 进程已重启，但健康检查未通过，请查看 data/logs/cloud2-*.log ===" >&2
exit 1
