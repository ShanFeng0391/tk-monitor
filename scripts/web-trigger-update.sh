#!/usr/bin/env bash
# Web 后台触发的更新包装（Linux 轻量 #2）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATUS="$ROOT/data/deploy-update-status.json"
LOG="$ROOT/data/logs/deploy-update.log"
BACKEND_ONLY=false
SKIP_GIT=false
for arg in "$@"; do
  case "$arg" in
    --backend-only) BACKEND_ONLY=true ;;
    --skip-git) SKIP_GIT=true ;;
  esac
done

mkdir -p "$(dirname "$LOG")"

set_status() {
  local state="$1"
  local message="$2"
  python3 - "$state" "$message" "$STATUS" <<'PY'
import json
import sys
from datetime import datetime
from pathlib import Path

state, message, path = sys.argv[1], sys.argv[2], Path(sys.argv[3])
data = {}
if path.is_file():
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
data["state"] = state
data["message"] = message
data["finished_at"] = datetime.utcnow().isoformat()
if not data.get("started_at"):
    data["started_at"] = datetime.utcnow().isoformat()
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
PY
}

echo "--- web update $(date -u +%Y-%m-%dT%H:%M:%SZ) ---" >>"$LOG"
ARGS=()
[[ "$BACKEND_ONLY" == true ]] && ARGS+=(--backend-only)
[[ "$SKIP_GIT" == true ]] && ARGS+=(--skip-git)

if bash "$ROOT/scripts/tencent-lightweight/update-code.sh" "${ARGS[@]}" >>"$LOG" 2>&1; then
  set_status success "更新完成，服务已重启"
else
  set_status failed "update-code.sh 执行失败，见 deploy-update.log"
  exit 1
fi
