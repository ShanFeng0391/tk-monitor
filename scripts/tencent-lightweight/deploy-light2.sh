#!/usr/bin/env bash
# 轻量 #2 一键部署：克隆 → 依赖 → 前端 → 迁移 → API+Beat+Worker
# 在宝塔 #2 终端粘贴一条命令即可
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/load-deploy-conf.sh"

GIT_REPO="${GIT_REPO:-https://github.com/ShanFeng0391/tk-monitor.git}"
APP_ROOT="${APP_ROOT_LIGHT2:-/www/wwwroot/tk-monitor}"
NODE_MAJOR="${NODE_MAJOR:-20}"
SINGBOX_VER="${SINGBOX_VER:-1.12.0}"

echo "=== 轻量 #2 一键部署 (API + Beat + Worker) ==="
echo "目录: $APP_ROOT"

if command -v apt-get >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y git curl ca-certificates python3 python3-venv python3-pip gzip build-essential
elif command -v yum >/dev/null 2>&1; then
  yum install -y git curl ca-certificates python3 python3-pip gzip gcc
fi

if ! command -v node >/dev/null 2>&1; then
  echo ">> 安装 Node.js ${NODE_MAJOR} ..."
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

# sing-box
BIN_DIR="$APP_ROOT/data/bin"
mkdir -p "$BIN_DIR"
if [[ ! -x "$BIN_DIR/sing-box" ]]; then
  ARCH="$(uname -m)"
  case "$ARCH" in
    x86_64) SB_ARCH=amd64 ;;
    aarch64) SB_ARCH=arm64 ;;
    *) echo "不支持的架构: $ARCH"; exit 1 ;;
  esac
  ZIP="sing-box-${SINGBOX_VER}-linux-${SB_ARCH}.tar.gz"
  URL="https://github.com/SagerNet/sing-box/releases/download/v${SINGBOX_VER}/${ZIP}"
  echo ">> 下载 sing-box ..."
  curl -fsSL "$URL" -o "/tmp/${ZIP}"
  TMP="/tmp/sing-box-extract-$$"
  mkdir -p "$TMP"
  tar -xzf "/tmp/${ZIP}" -C "$TMP"
  SB_BIN="$(find "$TMP" -name sing-box -type f | head -1)"
  cp "$SB_BIN" "$BIN_DIR/sing-box"
  chmod +x "$BIN_DIR/sing-box"
  rm -rf "$TMP" "/tmp/${ZIP}"
  "$BIN_DIR/sing-box" version | head -1
fi

echo ">> 生成 .env.hybrid ..."
bash "$SCRIPT_DIR/render-env-hybrid.sh" "$APP_ROOT/.env.hybrid" cloud2

echo ">> 安装 Python 依赖 ..."
cd "$APP_ROOT/backend"
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -q

echo ">> 数据库迁移 ..."
bash "$APP_ROOT/scripts/tencent-lightweight/init-hybrid-db.sh"

echo ">> 构建前端 ..."
cd "$APP_ROOT/frontend"
if [[ ! -d node_modules ]]; then
  npm install --silent
fi
npm run build
if [[ ! -f dist/index.html ]]; then
  echo "前端构建失败" >&2
  exit 1
fi

echo ">> 启动 API + Beat + Worker ..."
bash "$APP_ROOT/scripts/tencent-lightweight/start-compute-node.sh"

sleep 5
echo ""
if curl -sf "http://127.0.0.1:8000/api/v1/system/health"; then
  echo ""
  echo "=== 部署成功 ==="
  echo "浏览器访问: http://${LIGHT2_IP:-120.53.91.39}:8000"
  echo "管理员: ${ADMIN_USERNAME:-admin} / （你设置的 ADMIN_PASSWORD）"
else
  echo "=== 进程已启动，但健康检查未通过 ===" >&2
  echo "请查看: $APP_ROOT/data/logs/cloud2-*.log" >&2
  exit 1
fi
