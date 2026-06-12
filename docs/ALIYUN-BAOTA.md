# 阿里云双轻量 + 宝塔面板 上线指南

适用于：**2 台阿里云轻量应用服务器 + 宝塔**，与项目混合架构一致。

| 机器 | 角色 | 安装内容 |
|------|------|----------|
| **轻量 #1** | 数据层 | PostgreSQL + Redis +（可选）PG 备份 cron |
| **轻量 #2** | 计算 + 公网 | API + Beat + Worker + sing-box + **宝塔 Nginx** |
| **本地 Windows**（可选） | 算力 | API + Worker×24（不跑 Beat） |

对象存储：阿里云 **OSS**（封面图 + 数据库备份）。

---

## 我能自动帮你做什么 / 不能做什么

| 操作 | 说明 |
|------|------|
| ✅ 本仓库已准备好脚本、环境模板、Nginx 片段 | 你 `git pull` 即可 |
| ✅ 本地 Windows 初始化数据库、启动 Worker | 你在本机执行命令 |
| ❌ **无法直接登录你的阿里云** | 需要你在宝塔「终端」或 SSH 里粘贴命令，或提供 SSH 信息 |

---

## 第 0 步：购买与网络（控制台）

### 安全组（两台都要配）

| 端口 | 轻量 #1 | 轻量 #2 |
|------|---------|---------|
| 22 | 你的 IP | 你的 IP |
| 80 / 443 | 可不开放 | **0.0.0.0/0**（网站） |
| 5432 | **仅 #2 IP + 本地 IP** | 不开放 |
| 6379 | **仅 #2 IP + 本地 IP** | 不开放 |
| 8000 | 不开放 | 仅 127.0.0.1（由 Nginx 反代） |

### 宝塔防火墙

与安全组一致：在 **宝塔 → 安全** 里同样放行，否则外网仍连不上。

### OSS

1. 阿里云控制台 → 对象存储 OSS → 创建 Bucket（私有、与轻量同地域）
2. RAM → 创建子账号 → 仅授权该 Bucket 读写
3. 记录：`Endpoint`（如 `oss-cn-hangzhou.aliyuncs.com`）、`AccessKeyId`、`AccessKeySecret`、桶名

---

## 第 1 步：轻量 #1（数据层）

### 1.1 宝塔终端执行

```bash
cd /root
git clone https://github.com/ShanFeng0391/tk-monitor.git
cd tk-monitor/scripts/aliyun-baota

export DB_PASS='你的PG强密码'
export REDIS_PASS='你的Redis强密码'
# 逗号分隔：本地宽带公网IP/32 与 轻量#2公网IP/32
export CLIENT_IPS='123.45.67.89/32,111.222.333.444/32'

bash setup-data-node.sh
```

记下脚本输出的 **轻量 #1 公网 IP** 和连接串。

### 1.2（可选）PG 每日备份到 OSS

```bash
cp /root/tk-monitor/scripts/aliyun-baota/env.server.example /root/tk-monitor/.env.server
nano /root/tk-monitor/.env.server   # 填 PG 与 OSS

# 宝塔 → 计划任务 → Shell → 每天 4:00
# bash /root/tk-monitor/scripts/backup-postgres.sh >> /www/backup/tiktok-monitor/backup.log 2>&1
```

---

## 第 2 步：轻量 #2（API + Beat + Worker）

### 2.1 克隆与构建

私有仓库需先登录 GitHub（浏览器或 Token）。在宝塔终端：

```bash
export GIT_REPO='https://github.com/ShanFeng0391/tk-monitor.git'
export APP_ROOT='/www/wwwroot/tk-monitor'
bash /root/tk-monitor/scripts/aliyun-baota/bootstrap-compute-node.sh
```

若 `#2` 上还没有代码，可先 clone 再执行：

```bash
git clone https://github.com/ShanFeng0391/tk-monitor.git /www/wwwroot/tk-monitor
cd /www/wwwroot/tk-monitor/scripts/aliyun-baota
export APP_ROOT='/www/wwwroot/tk-monitor'
bash bootstrap-compute-node.sh
```

### 2.2 填写环境变量

```bash
cp /www/wwwroot/tk-monitor/.env.hybrid.aliyun.server2.example \
   /www/wwwroot/tk-monitor/.env.hybrid
nano /www/wwwroot/tk-monitor/.env.hybrid
```

**必改**：轻量 #1 的 PG/Redis 地址与密码、OSS、`SECRET_KEY`、`JWT_SECRET_KEY`、`ADMIN_PASSWORD`、`ARK_API_KEY`、`CORS_ORIGINS`（你的域名）。

### 2.3 启动服务

```bash
cd /www/wwwroot/tk-monitor
bash scripts/tencent-lightweight/start-compute-node.sh
curl http://127.0.0.1:8000/api/v1/system/health
```

### 2.4 宝塔网站 + HTTPS

1. **网站 → 添加站点**（你的域名，PHP 选「纯静态」或不用 PHP）
2. **设置 → 配置文件**，在 `server { }` 内粘贴 `scripts/aliyun-baota/nginx-baota.conf` 内容
3. **SSL → Let's Encrypt** 申请证书并开启强制 HTTPS
4. 重载 Nginx

浏览器访问：`https://你的域名/` → 应出现登录页。

---

## 第 3 步：本地 Windows（Worker×24，可选）

```powershell
cd C:\Users\Administrator\Projects\tiktok-monitor
copy .env.hybrid.aliyun.example .env.hybrid
# 用记事本填：轻量1 PG/Redis、OSS、CLUSTER_PEER_API_URL=轻量2地址

.\scripts\init-hybrid-db.ps1
.\scripts\start-local-node.ps1
```

`init-hybrid-db` 只需成功执行 **一次**（建表）。

---

## 第 4 步：验收

1. 登录超级管理员 → **集群监控**：轻量 #2 在线、Beat 运行、Worker 有数字
2. 若开了本地节点：本地卡片也应在线
3. **代理池** → 健康检查
4. **监控管理** → 试添加博主 / 采集

---

## 日常更新

| 位置 | 操作 |
|------|------|
| 开发电脑 | `git add` → `git commit` → `git push` |
| 轻量 #2 | 管理后台 → **集群监控 → 一键更新本节点** |
| 本地 | 同上 |

---

## 常见问题

| 现象 | 处理 |
|------|------|
| 集群 Redis error | #2 的 `.env.hybrid` 里 Redis 地址/密码错，或 #1 未放行 #2 IP |
| 节点离线 | `start-compute-node` / `start-local-node` 未运行 |
| 网站 502 | API 未启动或 Nginx 未反代到 127.0.0.1:8000 |
| git clone 私有库失败 | 用 GitHub Token 或 SSH Deploy Key |

---

## 相关文件

| 文件 | 用途 |
|------|------|
| `scripts/aliyun-baota/setup-data-node.sh` | 轻量 #1 装 PG+Redis |
| `scripts/aliyun-baota/bootstrap-compute-node.sh` | 轻量 #2 装依赖+构建 |
| `scripts/aliyun-baota/nginx-baota.conf` | 宝塔 Nginx 反代片段 |
| `.env.hybrid.aliyun.example` | 本地 Windows 模板 |
| `.env.hybrid.aliyun.server2.example` | 轻量 #2 模板 |
