#!/usr/bin/env bash
# 阿里云轻量 #2（宝塔）：克隆代码、装依赖、构建前端、启动 API+Beat+Worker
# 用法（root 或 www 用户，建议目录 /www/wwwroot/tk-monitor）：
#   export GIT_REPO='https://github.com/ShanFeng0391/tk-monitor.git'
#   export APP_ROOT='/www/wwwroot/tk-monitor'
#   bash bootstrap-compute-node.sh
set -euo pipefail

GIT_REPO="${GIT_REPO:-https://github.com/ShanFeng0391/tk-monitor.git}"
APP_ROOT="${APP_ROOT:-/www/wwwroot/tk-monitor}"
NODE_MAJOR="${NODE_MAJOR:-20}"

echo "=== 轻量 #2 应用 bootstrap ==="
echo "目录: $APP_ROOT"

if command -v apt-get >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y git curl ca-certificates python3 python3-venv python3-pip gzip build-essential
elif command -v yum >/dev/null 2>&1; then
  yum install -y git curl ca-certificates python3 python3-pip gzip gcc
fi

# Node.js（构建前端）
if ! command -v node >/dev/null 2>&1; then
  curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash - 2>/dev/null || true
  if command -v apt-get >/dev/null 2>&1; then
    apt-get install -y nodejs || apt-get install -y nodejs npm
  fi
fi
node --version
npm --version

mkdir -p "$(dirname "$APP_ROOT")"
if [[ ! -d "$APP_ROOT/.git" ]]; then
  git clone "$GIT_REPO" "$APP_ROOT"
else
  cd "$APP_ROOT"
  git pull --ff-only || true
fi

cd "$APP_ROOT"

# sing-box（Linux amd64）
SINGBOX_VER="${SINGBOX_VER:-1.12.0}"
BIN_DIR="$APP_ROOT/data/bin"
mkdir -p "$BIN_DIR"
if [[ ! -x "$BIN_DIR/sing-box" ]]; then
  ARCH="$(uname -m)"
  case "$ARCH" in
    x86_64) SB_ARCH=amd64 ;;
    aarch64) SB_ARCH=arm64 ;;
    *) echo "不支持的架构: $ARCH"; exit 1 ;;
  esac
  TMP="/tmp/sing-box-${SINGBOX_VER}"
  ZIP="sing-box-${SINGBOX_VER}-linux-${SB_ARCH}.tar.gz"
  URL="https://github.com/SagerNet/sing-box/releases/download/v${SINGBOX_VER}/${ZIP}"
  curl -fsSL "$URL" -o "/tmp/${ZIP}"
  rm -rf "$TMP"
  mkdir -p "$TMP"
  tar -xzf "/tmp/${ZIP}" -C "$TMP"
  SB_BIN="$(find "$TMP" -name sing-box -type f | head -1)"
  cp "$SB_BIN" "$BIN_DIR/sing-box"
  chmod +x "$BIN_DIR/sing-box"
  echo "sing-box: $($BIN_DIR/sing-box version | head -1)"
fi

cd "$APP_ROOT/backend"
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -q

cd "$APP_ROOT/frontend"
if [[ ! -d node_modules ]]; then
  npm install --silent
fi
npm run build

if [[ ! -f "$APP_ROOT/.env.hybrid" ]]; then
  if [[ -f "$APP_ROOT/.env.hybrid.aliyun.server2.example" ]]; then
    cp "$APP_ROOT/.env.hybrid.aliyun.server2.example" "$APP_ROOT/.env.hybrid"
    echo ""
    echo "!!! 请编辑 $APP_ROOT/.env.hybrid 填写 PG/Redis/OSS/密钥 后再启动 !!!"
    echo "    nano $APP_ROOT/.env.hybrid"
    exit 0
  fi
fi

bash "$APP_ROOT/scripts/tencent-lightweight/start-compute-node.sh"
sleep 4
curl -sf "http://127.0.0.1:8000/api/v1/system/health" && echo "" && echo "健康检查 OK" || echo "请查看 data/logs/cloud2-*.log"
