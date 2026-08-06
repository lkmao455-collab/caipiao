# Phase 5 部署指南（P5.D）

Web 全栈容器化：后端（FastAPI + Uvicorn）、前端（Vue 3 + Vite → nginx）、
Redis 事件总线。所有服务由 `docker-compose.yml` 编排。

## 1. 镜像与服务

| 服务 | 镜像 | 说明 |
|------|------|------|
| `web` | `Dockerfile.web`（多阶段） | FastAPI 后端，监听 8000。剥离 PySide6/Qt 桌面栈，仅保留 Web + 核心策略运行时（含 numpy/ML 栈，因策略模块顶层导入 `caipiao.ml`）。|
| `frontend` | `frontend/Dockerfile`（多阶段） | Node 构建 → nginx:1.27-alpine 静态托管 SPA，并反向代理 API/WebSocket 到 `web:8000`。监听 80。|
| `redis` | `redis:7-alpine` | 事件总线（pub/sub）。不设置 `CAIPIAO_WEB_REDIS_URL` 时后端回退内存总线（仅单副本有效）。|

## 2. 快速开始

```bash
# 构建并启动全部服务
docker compose up --build

# 访问前端（nginx 代理 API/WS）
open http://localhost

# 直接访问后端文档
open http://localhost:8000/docs-public     # 公开子集
open http://localhost:8000/docs-private    # 完整 schema（需登录）
```

## 3. 环境变量（web 服务）

| 变量 | 默认 | 说明 |
|------|------|------|
| `CAIPIAO_WEB_DATA` | `/data` | 数据根目录（开奖数据 / 用户库 / 回测库）。compose 中持久化到卷 `caipiao_data`。|
| `CAIPIAO_WEB_DB` | 内存 SQLite | 用户/密钥/用量库，如 `sqlite:////data/web.db`。|
| `CAIPIAO_WEB_SECRET` | `change-me-in-prod` | JWT 签名密钥，**生产必须覆盖**。|
| `CAIPIAO_WEB_PULL_INTERVAL` | `60` | 后台开奖拉取间隔（秒），`0` 禁用。|
| `CAIPIAO_WEB_REDIS_URL` | 未设置 | Redis 连接串（`redis://redis:6379`）。设置后启用 Redis 事件总线。|
| `CAIPIAO_WEB_RATE_LIMIT` | `60/minute` | 默认接口速率上限（/generate、/backtest 有更严格独立限制）。|

## 4. 单独构建镜像

```bash
# 后端
docker build -f Dockerfile.web -t caipiao-web .

# 前端
docker build -f frontend/Dockerfile -t caipiao-frontend ./frontend
```

> `Dockerfile.web` 在 build 阶段用 CPU-only 索引安装 `torch` 以减小体积：
> `pip install torch --index-url https://download.pytorch.org/whl/cpu`。

## 5. 生产注意事项

- **密钥**：务必通过 `.env` 或编排平台注入 `CAIPIAO_WEB_SECRET`，不要使用默认值。
- **反向代理**：示例 nginx 已处理 WebSocket Upgrade 与 SPA history 回退；若前置 CLB/Ingress，需同样放行 `/ws` 的 `Upgrade` 头。
- **多副本**：事件总线依赖 Redis；纯内存总线跨副本不互通，生产必须设置 `CAIPIAO_WEB_REDIS_URL`。
- **数据持久化**：`caipiao_data` 与 `redis_data` 为命名卷，删除容器不丢数据。
- **HTTPS**：前端 nginx 仅提供 HTTP，TLS 终止建议放在前置网关/Ingress。

## 6. 本地开发（非容器）

```bash
pip install -r requirements-web.txt
pip install torch            # 或 CPU-only 索引
export CAIPIAO_WEB_SECRET=dev
uvicorn web_main:app --reload --port 8000

# 前端（另开终端）
cd frontend && npm install && npm run dev   # 5173，vite proxy 转发到 8000
```
