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

## 九、宝塔面板 + 两台腾讯云轻量（你当前场景）

### 一键部署（推荐，每台粘贴一条命令）

**我无法直接登录你的宝塔**，但项目已提供交互式脚本：按提示输入密码即可，无需手工编辑 `.env`。

| 顺序 | 机器 | 宝塔 → 终端，粘贴执行 |
|------|------|------------------------|
| 1 | **轻量 #1** `81.70.169.128` | 见下方「#1 一条命令」 |
| 2 | **轻量 #2** `120.53.91.39` | 见下方「#2 一条命令」 |

**#1 一条命令**（装 PostgreSQL + Redis）：

```bash
git clone https://github.com/ShanFeng0391/tk-monitor.git /opt/tk-monitor && cd /opt/tk-monitor && bash scripts/tencent-lightweight/deploy-light1.sh
```

按提示输入 **PG 密码、Redis 密码**（请记下来，#2 要用同一套）。若已创建 CAM 子账号，可先 `cp scripts/tencent-lightweight/deploy.conf.example scripts/tencent-lightweight/deploy.conf` 填好 `COS_SECRET_*`，则 #1 会顺带配置 **PG 备份 cron → COS**。

**#2 一条命令**（API + Beat + Worker + 前端 + 数据库迁移）：

```bash
git clone https://github.com/ShanFeng0391/tk-monitor.git /www/wwwroot/tk-monitor && cd /www/wwwroot/tk-monitor && bash scripts/tencent-lightweight/deploy-light2.sh
```

按提示输入：**PG/Redis 密码（与 #1 相同）**、**COS SecretId/SecretKey**、**后台管理员密码**。成功后浏览器打开 **http://120.53.91.39:8000**。

可选：把密码预先写入 `scripts/tencent-lightweight/deploy.conf`（从 `deploy.conf.example` 复制，已含你的 IP 与桶 `tk-monitor888-1333628464`），则脚本 **全程无交互**。

**部署前检查**：腾讯云安全组 + 宝塔防火墙 — #1 放行 5432/6379（`120.53.91.39`）；#2 放行 **8000**；宝塔端口 **6688 / 6689** 已改好。

---

与 `docs/ALIYUN-BAOTA.md` 流程相同，只是 **对象存储用 COS**、脚本用 **`scripts/tencent-lightweight/`**。

| 机器 | 角色 | 在宝塔终端执行 |
|------|------|----------------|
| **轻量 #1** | PG + Redis | 见下方「#1 命令块」 |
| **轻量 #2** | API + Beat + Worker + 公网 | 见下方「#2 命令块」 |
| **本地 Windows** | Worker×24 | `.env.hybrid.tencent.example` → `init-hybrid-db.ps1` → `start-local-node.ps1` |

### 安全组 + 宝塔防火墙（两台都要）

| 端口 | 轻量 #1 | 轻量 #2 |
|------|---------|---------|
| 5432 / 6379 | **仅** 本地 IP + 轻量#2 IP | 不开放 |
| 8000 | 不开放 | **0.0.0.0/0**（暂用 IP 访问）或仅你的 IP |
| 80 / 443 | 可选 | 有域名后再开 |

### 轻量 #1 — 宝塔 → 终端

```bash
git clone https://github.com/ShanFeng0391/tk-monitor.git
cd tk-monitor/scripts/tencent-lightweight

export DB_PASS='你的PG强密码'
export REDIS_PASS='你的Redis强密码'
export CLIENT_IPS='你的本地公网IP/32,轻量2公网IP/32'

bash setup-server.sh
```

### 轻量 #2 — 宝塔 → 终端

```bash
git clone https://github.com/ShanFeng0391/tk-monitor.git /www/wwwroot/tk-monitor
cd /www/wwwroot/tk-monitor
cp .env.hybrid.tencent.example .env.hybrid
nano .env.hybrid
# 改：轻量1 PG/Redis、COS、SECRET_KEY、ADMIN_PASSWORD、CLUSTER 等
# 并把 COMPUTE_NODE_ID=cloud2、BEAT_ENABLED_ON_NODE=true 等按文件内注释改好

bash scripts/tencent-lightweight/start-compute-node.sh
curl http://127.0.0.1:8000/api/v1/system/health
```

浏览器访问：**http://轻量2公网IP:8000**（你暂无域名，这样即可）。

有域名后：宝塔添加站点 → SSL → 反代片段见 `scripts/aliyun-baota/nginx-baota.conf`（与腾讯云通用）。

### 环境模板

- 本地：`.env.hybrid.tencent.example`
- 轻量 #2：同上文件，按注释改为 `cloud2` + Beat 开启

> 之前误写的 `docs/ALIYUN-BAOTA.md` / `.env.hybrid.aliyun.*` 可忽略，**以本节 + `.env.hybrid.tencent.example` 为准**。

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
