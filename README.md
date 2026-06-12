# TikTok 流量监控与爆款视频采集系统

TikTok 博主流量增速监控、爆款视频采集与豆包 AI 影视剧识别的 Web 应用。

## 技术栈

- **后端**: FastAPI + PostgreSQL + Redis + Celery + APScheduler
- **前端**: Vue 3 + Element Plus + ECharts
- **采集**: httpx + Playwright
- **AI**: 火山引擎方舟（豆包视觉理解）
- **部署**: Docker Compose + Nginx

## 快速启动

### Windows 一键启动（推荐）

```powershell
# 1. 首次：安装环境（Node.js + Docker Desktop）
.\scripts\install-prerequisites.ps1

# 2. 打开 Docker Desktop，等托盘图标变绿

# 3. 启动项目
.\scripts\start.ps1
```

### 本地模式（无需 Docker，适合无法开启虚拟化的环境）

```powershell
.\scripts\start-local.ps1
```

- 前端: http://localhost:5173/
- API: http://localhost:8000/docs（开发环境开放）
- 配置: `.env.local` → 复制为 `.env`
- 数据: `data/tiktok_monitor.db`（SQLite）

### 生产单机部署（上线推荐）

```powershell
copy .env.production.example .env.production   # 首次
# 编辑 .env.production 填写密钥与密码
.\scripts\deploy-production.ps1
```

- 访问: http://localhost:8000/（前后端一体）
- 配置: `.env.production`（勿与 `.env.local` 混用）
- 文档: 见 [DEPLOY.md](./DEPLOY.md)（安全、备份、运维脚本）

### Docker 手动启动

```bash
cp .env.example .env
docker compose up -d --build
```

- 前端: http://localhost
- API 文档: http://localhost/api/docs（Docker 环境）
- 默认管理员见 `.env` 中 `ADMIN_USERNAME` / `ADMIN_PASSWORD`

## 项目结构

```
tiktok-monitor/
├── backend/          # FastAPI 后端
├── frontend/         # Vue 3 前端
├── nginx/            # 反向代理配置
├── docker-compose.yml
└── .env.example
```

## 功能模块

- F1 博主流量增速监控
- F2 爆款视频采集与留存
- F3/F4 用户权限（普通/管理员）
- F5 收藏功能
- F6 后台定时任务
- F7 豆包 AI 影视剧识别
