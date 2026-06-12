#!/usr/bin/env bash
# 加载 deploy.conf（若存在）。用法：source "$(dirname "$0")/load-deploy-conf.sh"
set -euo pipefail

_TLW_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_CONF="${DEPLOY_CONF:-$_TLW_DIR/deploy.conf}"

if [[ -f "$DEPLOY_CONF" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$DEPLOY_CONF"
  set +a
  echo ">> 已加载配置: $DEPLOY_CONF"
fi

prompt_if_empty() {
  local var_name="$1"
  local prompt_text="$2"
  local is_secret="${3:-false}"
  local current="${!var_name:-}"
  if [[ -n "$current" ]]; then
    return 0
  fi
  if [[ "$is_secret" == "true" ]]; then
    read -rsp "$prompt_text: " current
    echo ""
  else
    read -rp "$prompt_text: " current
  fi
  if [[ -z "$current" ]]; then
    echo "未填写: $prompt_text" >&2
    exit 1
  fi
  printf -v "$var_name" '%s' "$current"
}

gen_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 24
  else
    python3 -c "import secrets; print(secrets.token_hex(24))"
  fi
}
