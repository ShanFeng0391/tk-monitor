# TikTok Monitor 部署指南

## 部署方式对照

| 方式 | 脚本 | 数据库 | 适用 |
|------|------|--------|------|
| **混合（腾讯云轻量，推荐）** | `start-hybrid.ps1` | 轻量自建 PG + Redis + **COS** | 本地 24 Worker，见 `docs/TENCENT-LIGHTWEIGHT.md` |
| **混合（云 RDS 版）** | `start-hybrid.ps1` | 云 RDS + 云 Redis + OSS | 本地 24 Worker + 全云数据层 |
| **生产（单机）** | `deploy-production.ps1` | SQLite `data/` | Windows 单机上线 |
| **开发** | `start-local.ps1` | SQLite | 热重载，`.env.local` |
| **Docker** | `docker compose up` | PostgreSQL + Redis | 多机/全栈，与 SQLite 生产**勿混用** |

配置文件对应关系：

| 文件 | 用途 |
|------|------|
| `.env.production` | 生产真实配置（含密钥，已在 `.gitignore`） |
| `.env.production.example` | 无密钥模板，新环境复制后填写 |
| `.env.hybrid` | 混合部署真实配置（云 RDS/Redis/OSS） |
| `.env.hybrid.tencent.example` | **腾讯云 2C4G 轻量 + COS** 模板（推荐） |
| `.env.hybrid.example` | 混合部署模板（云 RDS / 独立 Redis） |
| `.env` | 运行时文件，由部署脚本从 production/local 复制生成 |

---

## 方式零：混合部署（最终版，推荐规模化）

**拓扑（一次定死）**

| 位置 | 进程 | 说明 |
|------|------|------|
| 本地 Windows | Nginx（可选） | 443/80 → `127.0.0.1:8000` |
| 本地 | API（uvicorn） | Web + 管理接口，**不跑** APScheduler |
| 本地 | Beat | `app.tasks.beat_runner`，Daily / A 线闹钟 + B 线协调 |
| 本地 | Celery Worker ×**24** | 队列 `scrape`，执行采集 |
| 本地 | sing-box | 代理网关 |
| 云 | 轻量自建 **PostgreSQL** + **Redis**（或 RDS/Redis 版） | 主库 / 队列 |
| 云 | **COS**（或 OSS） | 封面图 + PG 备份 |

### 步骤

**腾讯云 2C4G 轻量（推荐）**：完整清单见 **[docs/TENCENT-LIGHTWEIGHT.md](docs/TENCENT-LIGHTWEIGHT.md)**，环境模板用 `.env.hybrid.tencent.example`。

**云 RDS 版**：

1. **创建云资源**（见下文「云资源创建指南」）
2. 复制 `.env.hybrid.example` → `.env.hybrid`，填写连接串与密钥
3. 初始化数据库：`.\scripts\init-hybrid-db.ps1`
4. 启动：`.\scripts\start-hybrid.ps1`
5. （公网）配置 `nginx\nginx.hybrid.conf` 并设置 `CORS_ORIGINS`

### 必改项（`.env.hybrid`）

| 变量 | 说明 |
|------|------|
| `LOCAL_MODE=false` | **必须**，启用 Postgres + Redis 代理池 |
| `DATABASE_URL` / `DATABASE_URL_SYNC` | 云 RDS 连接串（含 SSL） |
| `REDIS_URL` | 云 Redis（`rediss://` 若开启 TLS） |
| `MINIO_*` | OSS 桶与 RAM 子账号 AK/SK |
| `CELERY_WORKER_CONCURRENCY=24` | Worker 并发（脚本已默认 24） |
| `PROXY_POOL_LOCAL_ENV_FALLBACK=false` | 混合模式勿回退本地 env 代理 |

### 停止

```powershell
.\scripts\stop-hybrid.ps1
```

### 规模化必做三项（已内置）

| 项 | 实现 | 说明 |
|----|------|------|
| **Worker 池采集** | `task_dispatch.py` + Celery chord | 混合模式禁止 API/Beat 串行扫全库；A/B 线按博主拆分 |
| **快照 90 天归档** | `snapshot_archive.py` | Beat 每天 **03:30** 清理 `video_snapshots`（`SNAPSHOT_RETENTION_DAYS`） |
| **PG 每日备份** | `postgres_backup.py` | 轻量云 cron **04:00**（本地设 `POSTGRES_BACKUP_ENABLED=false`） |

轻量云 crontab 备选（Beat 未跑时）：

```bash
0 4 * * * cd /path/to/tiktok-monitor && ./scripts/backup-postgres.sh >> data/logs/backup.log 2>&1
```

Windows 需安装 PostgreSQL 客户端，确保 `pg_dump` 在 PATH 中。

### SQLite 迁移到 RDS

单机 SQLite 数据**不会自动同步**。可选：

1. 新环境：直接 `init-hybrid-db.ps1` 建空库，重新导入博主
2. 需保留数据：用 `pgloader` 或导出 SQL 再导入 RDS（表结构以 Alembic 为准）

---

## 云资源创建指南（阿里 / 腾讯 / 火山）

创建前请先查本机**公网出口 IP**（百度搜「IP」），白名单只放行该 IP。

### 1. PostgreSQL（RDS）

| 参数 | 建议值 |
|------|--------|
| 引擎 | **PostgreSQL 15** 或 16 |
| 规格 | **2 核 4 GB** 起步（可后升配） |
| 存储 | **100 GB** SSD，自动扩容开 |
| 库名 | `tiktok_monitor` |
| 账号 | `tiktok_monitor`（自定义密码，≥16 位） |
| 网络 | 与 Redis 同地域；**公网访问**开（仅白名单 IP） |
| SSL | **开启** |

**连接串示例（阿里云 RDS）**

```env
DATABASE_URL=postgresql+asyncpg://tiktok_monitor:你的密码@pgm-xxx.pg.rds.aliyuncs.com:5432/tiktok_monitor?ssl=require
DATABASE_URL_SYNC=postgresql://tiktok_monitor:你的密码@pgm-xxx.pg.rds.aliyuncs.com:5432/tiktok_monitor?sslmode=require
```

| 厂商 | 产品名 | 控制台关键词 |
|------|--------|--------------|
| 阿里云 | RDS PostgreSQL | 云数据库 RDS → PostgreSQL |
| 腾讯云 | TencentDB for PostgreSQL | 云数据库 PostgreSQL |
| 火山引擎 | 云数据库 RDS PostgreSQL | RDS → 创建 PostgreSQL 实例 |

### 2. Redis

| 参数 | 建议值 |
|------|--------|
| 版本 | **Redis 6.0 / 7.0** |
| 规格 | **1 GB** 标准版起步 |
| 架构 | 主从或单机标准版即可 |
| 密码 | 开启 **访问密码** |
| TLS | 建议开启（用 `rediss://`） |
| DB 规划 | **DB0** Celery broker/backend；**DB1** 代理池（`PROXY_POOL_REDIS_DB=1`） |

**连接串示例**

```env
# 无 TLS
REDIS_URL=redis://:你的密码@r-xxx.redis.rds.aliyuncs.com:6379/0
# 有 TLS
REDIS_URL=rediss://:你的密码@r-xxx.redis.rds.aliyuncs.com:6379/0
```

| 厂商 | 产品名 |
|------|--------|
| 阿里云 | 云数据库 Redis 版 |
| 腾讯云 | 云数据库 Redis |
| 火山引擎 | 缓存数据库 Redis 版 |

### 3. 对象存储 OSS（封面）

| 参数 | 建议值 |
|------|--------|
| 桶名 | `tiktok-monitor-covers`（全局唯一） |
| 地域 | 与 RDS 同区域（如 `cn-hangzhou`） |
| 权限 | **私有**；通过 RAM 子账号 AK/SK 读写 |
| 兼容 | MinIO SDK **S3 兼容**，填 **Endpoint 域名** |

**`.env` 示例（阿里云 OSS）**

```env
MINIO_ENDPOINT=oss-cn-hangzhou.aliyuncs.com
MINIO_ACCESS_KEY=LTAI...
MINIO_SECRET_KEY=...
MINIO_BUCKET=tiktok-monitor-covers
MINIO_SECURE=true
```

| 厂商 | 产品 | Endpoint 形式 |
|------|------|----------------|
| 阿里云 | OSS | `oss-cn-区域.aliyuncs.com` |
| 腾讯云 | COS | `cos.区域.myqcloud.com` |
| 火山引擎 | TOS | `tos-s3-区域.volces.com` |

RAM 子账号策略：仅该桶 `PutObject/GetObject/ListBucket`。

### 4. 安全组 / 白名单 checklist

- [ ] RDS：仅允许你的公网 IP `:5432`
- [ ] Redis：仅允许你的公网 IP `:6379`
- [ ] OSS：不开放公共读；仅 AK/SK 访问
- [ ] 密钥写入 `.env.hybrid`，**勿提交 Git**

---

## 方式一：生产部署（单端口 8000）

### 前置条件

- Python 3.11+、Node.js 18+
- 已填写 `.env.production`（可从 `.env.production.example` 复制）

### 一键部署

```powershell
cd C:\Users\Administrator\Projects\tiktok-monitor
.\scripts\deploy-production.ps1
```

脚本会自动：复制环境 → **备份数据库** → **轮转日志** → 构建前端 → 启动服务。

### 必改配置（`.env.production`）

| 变量 | 说明 |
|------|------|
| `SECRET_KEY` / `JWT_SECRET_KEY` | 随机长字符串，勿用占位符 |
| `ADMIN_PASSWORD` | 强密码，与开发环境分开 |
| `ARK_API_KEY` | 豆包粘贴识别 |
| `TMDB_API_KEY` / `BANGUMI_*` | 影视元数据 |
| `SCRAPE_PROXY_URL` | 可选兜底，代理池稳定时可暂缓 |

### 访问

- 首页：http://localhost:8000/
- 健康检查：http://127.0.0.1:8000/api/v1/system/health
- 账号：`.env.production` 中的 `ADMIN_USERNAME` / `ADMIN_PASSWORD`
- **生产默认不开放** `/docs`（`ENABLE_API_DOCS=true` 可开启）

### 停止

```powershell
.\scripts\stop-production.ps1
```

---

## 二、安全（公网暴露前）

| 项 | 现状 / 操作 |
|----|-------------|
| Swagger 文档 | `APP_ENV=production` + `DEBUG=false` 时自动关闭 |
| CORS | 生产默认不放宽；公网填 `CORS_ORIGINS=https://你的域名` |
| HTTPS | 公网必须经 Nginx/Caddy 终结 TLS，勿裸奔 8000 |
| 注册控制 | 超级管理员后台配置 **访问密钥**（access gate） |
| 密钥文件 | 勿提交 `.env.production`；已加入 `.gitignore` |

---

## 三、运维脚本

| 脚本 | 作用 |
|------|------|
| `backup-database.ps1` | 备份 `data/tiktok_monitor.db` 到 `data/backups/`，默认保留 14 份 |
| `rotate-logs.ps1` | `server.log` 超过 10MB 归档到 `data/logs/archive/` |
| `watch-production.ps1` | 每 60s 健康检查，失败则自动重新部署 |
| `deploy-production.ps1` | 部署前已自动执行备份 + 日志轮转 |
| **`update.ps1`** | **上线后日常更新**（拉代码 / 构建 / 重启 / 健康检查） |
| `start-hybrid.ps1` | 混合部署：API + Beat + Worker×24 |
| `stop-hybrid.ps1` | 停止混合部署进程 |
| `init-hybrid-db.ps1` | 在云 RDS 上执行 Alembic 迁移 |
| `backup-postgres.ps1` / `backup-postgres.sh` | PostgreSQL 逻辑备份 → 本地 + OSS |

手动备份：

```powershell
.\scripts\backup-database.ps1
.\scripts\backup-database.ps1 -Keep 30
```

长期运行建议：用 Windows **任务计划程序** 每天执行 `backup-database.ps1`；可选常驻 `watch-production.ps1`。

---

## 五、上线后更新代码（推荐）

改完代码或 `git pull` 之后，**不用重新走完整 deploy**，一条命令即可：

### Windows（本地 / 单机生产）

```powershell
cd C:\Users\Administrator\Projects\tiktok-monitor
.\scripts\update.ps1
```

脚本会自动：**拉代码 → 备份（生产 SQLite）→ pip → npm build → 重启 → 健康检查**。

| 场景 | 命令 |
|------|------|
| 日常全量更新 | `.\scripts\update.ps1` |
| 只改了 Python 后端 | `.\scripts\update.ps1 -BackendOnly` |
| 只改了 Vue 前端 | `.\scripts\update.ps1 -FrontendOnly` |
| 赶时间、跳过备份 | `.\scripts\update.ps1 -Quick` |
| 代码已手动更新、不 pull | `.\scripts\update.ps1 -SkipGitPull` |
| 单机混合（API+Beat+Worker 全在本机） | `.\scripts\update.ps1 -Mode hybrid-all` |
| 双节点之**本地**（仅 API+Worker） | `.\scripts\update.ps1`（`.env.hybrid` 含 `BEAT_ENABLED_ON_NODE=false` 时自动识别） |

### 腾讯云轻量 #2（公网 API + Beat + Worker）

SSH 登录轻量 #2 后：

```bash
cd /opt/tiktok-monitor   # 你的项目路径
bash scripts/tencent-lightweight/update-code.sh
```

仅后端改动：`bash scripts/tencent-lightweight/update-code.sh --backend-only`

### 双节点更新顺序（建议）

1. **轻量 #1**（PG/Redis）：一般**不用**更新应用代码，只维护数据库与 Nginx。
2. **轻量 #2**：`update-code.sh`（公网入口 API 与 Beat）。
3. **本地 Windows**：`.\scripts\update.ps1`（Worker×24）。

若本次改动涉及 **数据库表结构**，在任意一台能连 PG 的机器先执行：

```powershell
.\scripts\init-hybrid-db.ps1
```

再按上面顺序更新各节点。

### 与「完整部署」的区别

| | `update.ps1` | `deploy-production.ps1` |
|--|----------------|---------------------------|
| 用途 | **日常发版** | 首次上线 / 重大变更 |
| 速度 | 较快（可 `-Quick`） | 较慢（必备份+全量） |
| 适用 | 改 bug、小功能 | 新环境初始化 |

### Web 界面一键更新（最省事，推荐给超级管理员）

在 **集群监控** 页点击 **「一键更新本节点」**（需先在 `.env` 开启）：

```env
WEB_DEPLOY_UPDATE_ENABLED=true
```

改 `.env` 后需 **重启 API 一次**；之后日常发版在网页点按钮即可，无需 SSH / 双击 bat。

| 说明 | 内容 |
|------|------|
| 更新范围 | **仅当前浏览器所连的那台 API**（本地或轻量#2 各点一次） |
| 双节点 | 先轻量#2 页点更新 → 再本地页点更新 |
| 安全 | 默认 **关闭**；仅超级管理员；需二次确认 |
| 日志 | `data/logs/deploy-update.log` |

GitHub Actions / 双击 bat 适合「无人值守自动发版」；日常你一个人维护，**Web 按钮通常最简单**。

### Git 仓库（上线前必做）

项目已支持 `git pull` 一键更新。首次请完成：

**1. 本机设置 Git 身份（只需一次，把邮箱改成你的）**

```powershell
cd C:\Users\Administrator\Projects\tiktok-monitor
git config user.name "你的名字"
git config user.email "你的邮箱@example.com"
```

**2. 在 GitHub 或 Gitee 创建空仓库**（不要勾选 README）

**3. 关联并推送**

```powershell
git remote add origin https://github.com/你的用户名/tiktok-monitor.git
git push -u origin main
```

**4. 云服务器首次拉代码**

```bash
git clone https://github.com/你的用户名/tiktok-monitor.git
cd tiktok-monitor
cp .env.hybrid.tencent.example .env.hybrid   # 填好密钥
```

**5. 日常发版（开发电脑）**

```powershell
git add .
git commit -m "说明这次改了什么"
git push
```

然后在 **轻量#2 / 本地** 管理后台 → 集群监控 → **一键更新本节点**（会自动 `git pull`）。

已忽略、**不会上传**的内容：`.env`、`.env.hybrid`、`data/` 数据库与封面、`.venv`、`node_modules`。

---

## 四、冒烟测试清单

1. 登录管理员
2. 监控管理 → 添加博主 → 采集（A/B 线 / Daily）
3. 视频详情 → 豆包粘贴 → AI 提取并填写
4. 仪表盘 → 近 3 天爆款预测
5. 我的收藏 → 批量取消收藏
6. 代理池 → 健康检查（若使用 vmess/vless）

> `SCRAPE_ALLOW_MOCK=false` 时采集失败不会造假数据。

---

## 方式二：Docker 全栈

```powershell
copy .env.example .env
docker compose up -d --build
```

访问 http://localhost/ — 含 PostgreSQL、Redis、MinIO、Celery。**与 SQLite 生产数据不互通。**

---

## 方式三：开发模式

```powershell
.\scripts\start-local.ps1
```

- 前端 http://localhost:5173
- 后端 http://localhost:8000
- 配置来自 `.env.local`
