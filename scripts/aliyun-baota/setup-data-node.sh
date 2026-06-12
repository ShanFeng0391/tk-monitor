#!/usr/bin/env bash
# 阿里云轻量 #1（宝塔）：安装 PostgreSQL 15 + Redis
# 用法（root SSH 或宝塔终端）：
#   export DB_PASS='PG强密码'
#   export REDIS_PASS='Redis强密码'
#   export CLIENT_IPS='你的本地公网IP/32,轻量#2公网IP/32'
#   bash setup-data-node.sh
set -euo pipefail

DB_NAME="${DB_NAME:-tiktok_monitor}"
DB_USER="${DB_USER:-tiktok_monitor}"
DB_PASS="${DB_PASS:-}"
REDIS_PASS="${REDIS_PASS:-}"
CLIENT_IPS="${CLIENT_IPS:-}"

if [[ $EUID -ne 0 ]]; then
  echo "请使用 root 运行（宝塔 → 终端）" >&2
  exit 1
fi

if [[ -z "$DB_PASS" || -z "$REDIS_PASS" || -z "$CLIENT_IPS" ]]; then
  echo "请先设置：" >&2
  echo "  export DB_PASS='强密码'" >&2
  echo "  export REDIS_PASS='强密码'" >&2
  echo "  export CLIENT_IPS='IP1/32,IP2/32'   # 本地宽带 + 轻量#2 公网 IP" >&2
  exit 1
fi

if command -v apt-get >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y curl gnupg lsb-release ca-certificates
elif command -v yum >/dev/null 2>&1; then
  yum install -y curl ca-certificates
else
  echo "仅支持 Debian/Ubuntu 或 CentOS/RHEL 系" >&2
  exit 1
fi

# PostgreSQL 15（Ubuntu/Debian）
if ! command -v psql >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list'
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /etc/apt/trusted.gpg.d/postgresql.gpg
    apt-get update -y
    apt-get install -y postgresql-15 postgresql-contrib-15
  else
    echo "CentOS 建议在宝塔「软件商店」安装 PostgreSQL 15，或改用 Ubuntu 22.04 镜像" >&2
    exit 1
  fi
fi

if ! command -v redis-server >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    apt-get install -y redis-server
  else
    echo "CentOS 建议在宝塔「软件商店」安装 Redis" >&2
    exit 1
  fi
fi

sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASS}';"
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};"

PG_CONF="$(find /etc/postgresql -name postgresql.conf 2>/dev/null | head -1 || true)"
PG_HBA="$(find /etc/postgresql -name pg_hba.conf 2>/dev/null | head -1 || true)"
if [[ -n "$PG_CONF" && -n "$PG_HBA" ]]; then
  sed -i "s/^#*listen_addresses.*/listen_addresses = '*'/" "$PG_CONF"
  IFS=',' read -ra IPS <<< "$CLIENT_IPS"
  for cidr in "${IPS[@]}"; do
    cidr="$(echo "$cidr" | xargs)"
    [[ -z "$cidr" ]] && continue
    if ! grep -q "tiktok-monitor-${cidr}" "$PG_HBA" 2>/dev/null; then
      cat >> "$PG_HBA" <<EOF

# tiktok-monitor-${cidr}
host    ${DB_NAME}    ${DB_USER}    ${cidr}    scram-sha-256
EOF
    fi
  done
  systemctl restart postgresql
fi

REDIS_CONF="/etc/redis/redis.conf"
if [[ -f "$REDIS_CONF" ]]; then
  sed -i 's/^# requirepass .*/requirepass '"${REDIS_PASS}"'/' "$REDIS_CONF" || true
  grep -q '^requirepass ' "$REDIS_CONF" || echo "requirepass ${REDIS_PASS}" >> "$REDIS_CONF"
  sed -i 's/^bind .*/bind 0.0.0.0/' "$REDIS_CONF" || echo "bind 0.0.0.0" >> "$REDIS_CONF"
  systemctl restart redis-server || systemctl restart redis
fi

command -v apt-get >/dev/null 2>&1 && apt-get install -y python3 python3-venv python3-pip gzip git || true
mkdir -p /www/backup/tiktok-monitor/postgres

PUBLIC_IP="$(curl -fsSL --max-time 5 https://api.ipify.org 2>/dev/null || curl -fsSL --max-time 5 ifconfig.me 2>/dev/null || echo '你的轻量1公网IP')"

echo ""
echo "=== 轻量 #1 数据层安装完成 ==="
echo "PostgreSQL: ${DB_USER}@${DB_NAME}  端口 5432"
echo "Redis:      端口 6379（已设密码）"
echo "本机公网 IP: ${PUBLIC_IP}"
echo ""
echo "请务必在【阿里云安全组 + 宝塔防火墙】仅放行以下 IP 访问 5432/6379："
echo "  ${CLIENT_IPS}"
echo ""
echo "连接串（给轻量#2 / 本地 .env.hybrid 用）："
echo "  DATABASE_URL=postgresql+asyncpg://${DB_USER}:密码@${PUBLIC_IP}:5432/${DB_NAME}"
echo "  REDIS_URL=redis://:Redis密码@${PUBLIC_IP}:6379/0"
