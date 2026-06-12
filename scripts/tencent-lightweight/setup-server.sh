#!/usr/bin/env bash
# 腾讯云 2C4G 轻量 Ubuntu：安装 PostgreSQL 15 + Redis 7
# 用法（root）：bash setup-server.sh
# 安装前请在腾讯云安全组放行：22（SSH）、80/443（Nginx）、7000（frp，按需）
# 5432 / 6379 仅放行你本地宽带公网 IP，勿对 0.0.0.0/0 开放
set -euo pipefail

DB_NAME="${DB_NAME:-tiktok_monitor}"
DB_USER="${DB_USER:-tiktok_monitor}"
DB_PASS="${DB_PASS:-}"
REDIS_PASS="${REDIS_PASS:-}"
LOCAL_CLIENT_IP="${LOCAL_CLIENT_IP:-}"
CLIENT_IPS="${CLIENT_IPS:-$LOCAL_CLIENT_IP}"

if [[ $EUID -ne 0 ]]; then
  echo "请使用 root 运行" >&2
  exit 1
fi

if [[ -z "$DB_PASS" || -z "$REDIS_PASS" || -z "$CLIENT_IPS" ]]; then
  echo "请先设置环境变量：" >&2
  echo "  export DB_PASS='强密码'" >&2
  echo "  export REDIS_PASS='强密码'" >&2
  echo "  export CLIENT_IPS='本地公网IP/32,轻量2公网IP/32'" >&2
  echo "  （兼容旧写法：export LOCAL_CLIENT_IP='单IP/32'）" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y curl gnupg lsb-release

# PostgreSQL 15
if ! command -v psql >/dev/null 2>&1; then
  sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list'
  curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /etc/apt/trusted.gpg.d/postgresql.gpg
  apt-get update -y
  apt-get install -y postgresql-15 postgresql-contrib-15
fi

# Redis
if ! command -v redis-server >/dev/null 2>&1; then
  apt-get install -y redis-server
fi

sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASS}';"
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};"

PG_CONF="$(find /etc/postgresql -name postgresql.conf | head -1)"
PG_HBA="$(find /etc/postgresql -name pg_hba.conf | head -1)"
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

# Redis 密码 + 仅本地与指定 IP（通过 bind 0.0.0.0 + 安全组限制）
REDIS_CONF="/etc/redis/redis.conf"
sed -i 's/^# requirepass .*/requirepass '"${REDIS_PASS}"'/' "$REDIS_CONF" || true
grep -q '^requirepass ' "$REDIS_CONF" || echo "requirepass ${REDIS_PASS}" >> "$REDIS_CONF"
sed -i 's/^bind .*/bind 0.0.0.0/' "$REDIS_CONF" || echo "bind 0.0.0.0" >> "$REDIS_CONF"
systemctl restart redis-server

# 基础工具（备份脚本需要 pg_dump、python venv 可选）
apt-get install -y python3 python3-venv python3-pip gzip

mkdir -p /opt/tiktok-monitor/data/backups/postgres

echo ""
echo "=== 安装完成 ==="
echo "PostgreSQL: ${DB_USER}@${DB_NAME}  监听 5432"
echo "Redis:      密码已设置，监听 6379"
echo ""
echo "请确认腾讯云安全组："
echo "  - 5432、6379 仅对你的本地公网 IP 放行"
echo "  - 80/443 对公网（Nginx）"
echo ""
echo "本地 .env.hybrid 连接串示例："
echo "  DATABASE_URL=postgresql+asyncpg://${DB_USER}:密码@$(curl -s ifconfig.me):5432/${DB_NAME}"
echo "  REDIS_URL=redis://:密码@$(curl -s ifconfig.me):6379/0"
echo ""
echo "下一步："
echo "  1. 控制台创建 COS 桶 + CAM 子账号"
echo "  2. 本地复制 .env.hybrid.tencent.example → .env.hybrid 并填写"
echo "  3. 本地运行 init-hybrid-db.ps1 与 start-hybrid.ps1"
echo "  4. 将项目 scripts/tencent-lightweight 拷到轻量，配置 env.server 后运行 setup-cron.sh"
