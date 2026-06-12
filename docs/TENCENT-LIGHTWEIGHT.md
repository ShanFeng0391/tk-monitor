# 腾讯云 2C4G 轻量部署指南（推荐省钱方案）

本方案对应你的选择：

| 组件 | 位置 | 规格 |
|------|------|------|
| 轻量应用服务器 | 腾讯云 | **2C4G，系统盘 80～100GB** |
| PostgreSQL + Redis | 轻量云 **自建** | 同机部署 |
| 封面 + PG 备份 | **腾讯云 COS** | 私有桶，月费很低 |
| API + Beat + Worker×24 | **本地 Windows** | 12400F + 32G |
| 公网入口 | 轻量云 | Nginx + HTTPS + frp → 本地 API |

---

## 一、购买清单（控制台）

### 1. 轻量应用服务器

- **地域**：离本地近（华南广州 / 华东上海 等）
- **规格**：2 核 4G
- **系统盘**：**80GB 起，建议 100GB**（PostgreSQL + 少量本地备份）
- **系统**：Ubuntu 22.04 LTS
- **带宽**：按套餐（1M 起步即可，主要走 frp 隧道）

### 2. 安全组

| 端口 | 放行对象 | 用途 |
|------|----------|------|
| 22 | 你的 IP | SSH |
| 80 / 443 | 0.0.0.0/0 | Nginx 公网访问 |
| 7000 | 0.0.0.0/0 或按需 | frp 服务端（若用） |
| **5432** | **仅本地宽带公网 IP** | PostgreSQL（本地 Worker 连库） |
| **6379** | **仅本地宽带公网 IP** | Redis |

### 3. 对象存储 COS

- **存储桶**：如 `tiktok-monitor-covers-1250000000`（名称-APPID）
- **地域**：与轻量云 **相同**
- **权限**：私有读写
- **CAM 子账号**：仅该桶 `PutObject/GetObject/ListBucket/DeleteObject`
- 记录：**SecretId、SecretKey、Endpoint**（如 `cos.ap-guangzhou.myqcloud.com`）

---

## 二、轻量云安装 PostgreSQL + Redis

SSH 登录轻量云后：

```bash
export DB_PASS='你的PG强密码'
export REDIS_PASS='你的Redis强密码'
export LOCAL_CLIENT_IP='你的本地公网IP/32'   # 例：123.45.67.89/32

cd /path/to/tiktok-monitor/scripts/tencent-lightweight
bash setup-server.sh
```

安装完成后，用本地 `.env.hybrid` 中的连接串测试连通（见下文模板）。

---

## 三、轻量云配置 PG 备份（cron → COS）

将项目放到轻量云 `/opt/tiktok-monitor`，复制并填写：

```bash
cp scripts/tencent-lightweight/env.server.example /opt/tiktok-monitor/.env.server
# 编辑 .env.server：127.0.0.1 的 PG + COS 密钥

bash /opt/tiktok-monitor/scripts/tencent-lightweight/setup-cron.sh
```

每天 **04:00** 自动 `pg_dump` → 压缩 → 上传 COS `backups/postgres/`。

本地 Windows **不需要** 安装 `pg_dump`（`.env.hybrid` 中 `POSTGRES_BACKUP_ENABLED=false`）。

---

## 四、本地 Windows 配置

```powershell
cd C:\Users\Administrator\Projects\tiktok-monitor
copy .env.hybrid.tencent.example .env.hybrid
# 编辑 .env.hybrid：轻量公网 IP、PG/Redis 密码、COS 密钥、豆包等

.\scripts\init-hybrid-db.ps1
.\scripts\start-hybrid.ps1
```

### 必改项对照

| 变量 | 填什么 |
|------|--------|
| `DATABASE_URL` | `postgresql+asyncpg://tiktok_monitor:密码@轻量公网IP:5432/tiktok_monitor` |
| `DATABASE_URL_SYNC` | `postgresql://tiktok_monitor:密码@轻量公网IP:5432/tiktok_monitor` |
| `REDIS_URL` | `redis://:Redis密码@轻量公网IP:6379/0` |
| `MINIO_ENDPOINT` | `cos.ap-地域.myqcloud.com` |
| `MINIO_BUCKET` | `桶名-APPID` |
| `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | CAM 子账号 |
| `POSTGRES_BACKUP_ENABLED` | **`false`**（备份在轻量 cron） |
| `CELERY_WORKER_CONCURRENCY` | `24` |

可从 `.env.production` 复制 `ARK_*`、`TMDB_*`、`BANGUMI_*`、`ADMIN_*`。

---

## 五、公网访问（方案 A：frp）

轻量云只做「门面」，API 仍在本地：

```
用户 → https://你的域名 → 轻量 Nginx → frp → 本地 127.0.0.1:8000
```

1. 轻量云安装 Nginx + 申请 SSL（腾讯云免费证书）
2. 轻量云 frps，本地 frpc 连上（指向本地 8000）
3. `.env.hybrid` 设置 `CORS_ORIGINS=https://你的域名`

Nginx 反代示例见 `nginx/nginx.hybrid.conf`。

---

## 六、磁盘够用吗？

| 内容 | 在哪 | 大约占用 |
|------|------|----------|
| PostgreSQL 元数据 | 轻量 100GB 盘 | 起步几 GB，规模化后 20～60GB（有 90 天快照归档） |
| 封面图片 | **COS** | 不占轻量盘 |
| PG 备份副本 | COS 为主，轻量留 3 份 | 可控 |
| Redis | 内存 | 几乎不占盘 |
| 采集 / Worker | 本地 500G SSD | 日志等 |

**100GB 系统盘 + COS 封面** 对该方案足够；后期可在控制台扩容系统盘。

---

## 七、检查清单

- [ ] 轻量 2C4G + 100GB 已购买
- [ ] COS 桶 + CAM 子账号已创建
- [ ] 安全组 5432/6379 仅本地 IP
- [ ] `setup-server.sh` 已执行
- [ ] 本地 `.env.hybrid` 已填写并 `init-hybrid-db.ps1` 成功
- [ ] `start-hybrid.ps1` 健康检查 database/redis/celery 均为 ok
- [ ] 轻量 `setup-cron.sh` 备份测试通过
- [ ] frp + Nginx + 域名（公网访问）

---

## 八、双计算节点（本地 + 轻量 #2）

| 机器 | 启动脚本 | Worker | Beat |
|------|----------|--------|------|
| 本地 Windows | `scripts/start-local-node.ps1` | 24 | **不启动** |
| 轻量 #2 | `scripts/tencent-lightweight/start-compute-node.sh` | 10 | **唯一 Beat** |

Web 管理后台 → **集群监控**（超级管理员）：查看两节点在线、Worker 数量、代理池建议。

公网 Nginx 建议 **默认反代到轻量 #2:8000**（7×24）；本地可选 frp 备用。

### 上线后更新代码

| 机器 | 一条命令 |
|------|----------|
| 本地 Windows | `.\scripts\update.ps1` |
| 轻量 #2 | `bash scripts/tencent-lightweight/update-code.sh` |

建议顺序：先更新 **轻量 #2**（公网 API + Beat），再更新 **本地**（Worker）。若有数据库迁移，先跑 `.\scripts\init-hybrid-db.ps1`。

---

## 相关文件

| 文件 | 说明 |
|------|------|
| `.env.hybrid.tencent.example` | 本地 Windows 环境模板 |
| `scripts/tencent-lightweight/setup-server.sh` | 轻量安装 PG + Redis |
| `scripts/start-local-node.ps1` | 本地计算节点（无 Beat） |
| `scripts/tencent-lightweight/start-compute-node.sh` | 轻量 #2（API+Beat+Worker） |
| `scripts/tencent-lightweight/update-code.sh` | 轻量 #2 **日常更新** |
| `scripts/update.ps1` | 本地 / 单机 **日常更新** |
| `scripts/tencent-lightweight/env.server.example` | 轻量备份用 env |
| `DEPLOY.md` | 通用混合部署说明 |
