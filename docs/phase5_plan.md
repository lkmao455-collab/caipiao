# Phase 5 规划：企业级（Web / 多用户 / 开放 API / 实时推送）

> 状态：规划已批准。**P5.0 垂直切片已完成（commit 9379f9c）；P5.A 已完成（commit 2085e4b）；P5.B 已完成；P5.C 已完成；P5.D 已完成；P5.E 已完成**。全阶段路线图已交付。本文件为完整架构设计 + 分阶段路线图。

## 1. 目标与原则
- **复用核心层**：`caipiao/core`、`caipiao/data`、`caipiao/persistence`、`caipiao/ml`、`caipiao/calendar`、`caipiao/divination`、`caipiao/utils`、`caipiao/plugins` 已与 UI 解耦，**零侵入**复用，不修改其核心逻辑。
- **桌面并行**：现有 PyQt/PySide 桌面应用（`caipiao/app.py` + `main.py`）保留不动；Web 后端是等价服务化封装。
- **本次交付**：计划文档 + 可运行**垂直切片**（FastAPI 后端 + 最小 Vue 前端，打通「登录 → 彩种 → 生成」端到端链路）。

## 2. 现状资产（已确认）
| 资产 | 用途 |
|------|------|
| `core.engine.GenerationEngine` | 空引擎，需 `register(strategy)` 后 `generate(strategy_id, count, options) -> list[Ticket]` |
| `core.strategies.factory.build_strategies(profile)` | 返回某彩种的全部策略实例 |
| `core.strategies.registry.STRATEGY_REGISTRY` | 彩种 → 策略类列表 |
| `core.profile.get_profile / list_profiles / list_profiles_by_category / profile_keys` | 彩种注册表 |
| `core.strategy.GenerationStrategy` | ABC：`metadata`（`id`/`name`/`description`/`configurable`）、`generate`、`get_config_schema`、`validate_options` |
| `core.ticket.Ticket.to_dict()` | 投注单序列化 |
| `data.repository.DrawRepository(path, profile)` | 本地开奖数据（默认 `.caipiao/draws.json`，按 `profile.storage_file`） |
| `data.models.DrawRecord.to_dict()/from_dict()` | 开奖记录序列化 |
| `persistence.OptimalParamStore / ParameterGroupStore / AppSettings` | 全局文件存储（非用户隔离） |
| `ml.predictor.MLPredictor.train/predict` | ML 预测 |
| `Dockerfile` / `docker-compose.yml` / `deploy.py` | 桌面向，需新增独立 web 目标 |
| `tests/` + `pytest.ini`（`slow` marker）+ `conftest.py`（`QT_QPA_PLATFORM=offscreen`） | 测试基础设施 |

**约束**：仓库当前**无任何** web/websocket/API 代码，无 fastapi/uvicorn/pydantic/jose/passlib 依赖。

## 3. 技术选型
- 后端：FastAPI + Uvicorn，Pydantic v2。
- 鉴权：JWT（python-jose + passlib[bcrypt]），后续 API Key。
- 存储：SQLite（SQLAlchemy + aiosqlite）存用户/密钥；业务数据沿用现有文件存储（按用户命名空间隔离）。
- 前端：Vue 3 + Vite + TypeScript。
- 实时：WebSocket（`/ws/draws`），`asyncio.Queue` 内存事件总线（生产化留待后续阶段）。

## 4. 目录结构
```
caipiao/
  web/                        # 新增：纯服务端包，不 import caipiao.ui / caipiao.app
    __init__.py
    config.py                 # SECRET_KEY / CORS / DB URL / 数据根目录
    db.py                     # SQLAlchemy engine/session/Base/get_db
    security.py               # bcrypt 哈希 + JWT 签发/校验 + API Key 生成
    models.py                 # User, ApiKey ORM
    schemas.py                # Pydantic 请求/响应
    deps.py                   # get_current_user / API Key 依赖
    engine.py                 # build_engine() 复用 core 策略注册
    eventbus.py               # asyncio.Queue 广播总线
    routers/
      auth.py                 # /auth/register, /auth/login
      profiles.py            # /profiles, /profiles/{key}, /profiles/{key}/strategies
      generate.py            # /generate
      backtest.py            # /backtest
      user.py                # /me（参数组/设置，用户命名空间隔离）
      api_keys.py            # /me/apikeys CRUD
    ws.py                     # /ws/draws
  web_main.py                 # 仓库根：uvicorn 入口 `uvicorn web_main:app`
frontend/                     # 新增：Vue 3 + Vite + TS
  package.json, vite.config.ts, index.html, src/...
  src/api/client.ts           # /auth/login, /profiles, /generate
  src/views/Login.vue, Profiles.vue, Generate.vue
```

## 5. 后端接口（垂直切片）
| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| GET | `/health` | 健康检查 | 无 |
| POST | `/auth/register` | 注册用户（bcrypt + 写库） | 无 |
| POST | `/auth/login` | 登录，返回 JWT | 无 |
| GET | `/profiles` | 彩种列表（key/name/category/group_keys） | JWT |
| GET | `/profiles/{key}` | 彩种详情 | JWT |
| GET | `/profiles/{key}/strategies` | 该彩种可用策略（id/name/description/config_schema） | JWT |
| POST | `/generate` | `{profile_key, strategy_id, count, options}` → `list[Ticket.to_dict()]`（调 `build_engine().generate`） | JWT 或 API Key |
| POST | `/backtest` | 触发核心回测（复用 `core` 回测入口） | JWT |
| GET/PUT | `/me` | 当前用户参数组/设置（按 user 命名空间隔离） | JWT |
| GET/POST/DELETE | `/me/apikeys` | API Key 签发/列表/吊销 | JWT |
| WS | `/ws/draws` | 实时推送开奖/生成事件 | JWT |
| GET | `/me` | 当前用户信息（含 `role`） | JWT |
| GET | `/admin/stats` | 管理概览统计 | 管理员 |
| GET | `/admin/users` | 用户列表 | 管理员 |
| PATCH | `/admin/users/{id}/role` | 修改用户角色（admin/user） | 管理员 |
| DELETE | `/admin/users/{id}` | 删除用户（禁止操作自身） | 管理员 |

`build_engine()` 实现（参考 `factory.build_strategies` + 桌面注册方式）：
```python
def build_engine() -> GenerationEngine:
    engine = GenerationEngine()
    for profile in list_profiles():
        for strategy in build_strategies(profile):
            engine.register(strategy)
    return engine
```
> 注：桌面按「当前彩种」构建 engine；web 构建全局 engine（策略 id 在 `STRATEGY_REGISTRY` 内唯一）。

## 6. 用户隔离策略（最小改造）
- `AppSettings` 为全局单例（读 `CAIPIAO_HOME` 或 cwd），**不改动**其语义。
- 用户私有数据（`ParameterGroupStore` / `OptimalParamStore`）通过**路径命名空间**隔离：如 `<data_root>/users/<user_id>/parameter_groups/<profile>.json`，在 `routers/user.py` 中按 `current_user.id` 构造 store 实例，核心层不用改。

## 7. 前端垂直切片（端到端一条链路）
1. `Login.vue`：调用 `/auth/login` 拿 JWT，存 localStorage。
2. `Profiles.vue`：调 `/profiles` 展示彩种；选一个后调 `/profiles/{key}/strategies`。
3. `Generate.vue`：选策略 + count + options，调 `/generate`，展示 `Ticket` 列表（按 `profile.group_keys` 分组渲染号码）。

## 8. 分阶段路线图
- **P5.0（完成）**：计划 + 垂直切片（后端骨架 + 认证 + profiles/generate/backtest + 最小前端 + 测试）。commit 9379f9c。
- **P5.A（完成）**：完整前端与支撑后端。新增 `/profiles/{key}/stats`（复用 `DrawAnalyzer`）、`/profiles/{key}/filters`（动态后过滤编辑）、`/backtest` 升级为走查式回测并持久化（`BacktestDatabase` 显式路径 + 列表/详情/删除）；`GenerateRequest.post_filters` 生成后调用核心层 `filter_*_by_history`；前端新增 Stats/Backtest/FilterRules 视图与导航。commit 2085e4b。核心层零改动，覆盖指标隔离不变。
- **P5.B（完成）**：开放平台限流（slowapi，按 Token/API Key/IP 限流；重接口 /generate 60/min、/backtest 30/min，其余动态默认 600/min）、用量计量（`UsageRecord` + `GET /me/usage`）、Swagger 公开/私有分层（默认关闭 `/docs`，提供 `/docs-public` 子集与 `/docs-private` 完整 schema）。
- **P5.C（完成）**：实时推送生产化。`eventbus.py` 提供 `EventBus` 协议 + `InMemoryEventBus`（开发回退）与 `RedisEventBus`（Redis pub/sub，设置 `CAIPIAO_WEB_REDIS_URL` 时启用）；同步 `redis.Redis` 发布端 + 异步 `redis.asyncio` 监听端分离，livespan 启动监听任务。`web_main.py` 新增 `_draw_poller` 后台定时拉取各彩种最新开奖并 `bus.publish` 到 `draw_update`（间隔由 `CAIPIAO_WEB_PULL_INTERVAL` 控制，0 则禁用）。`ws.py` 增加 30s 心跳保活并清理全部任务。测试 `test_eventbus_ws.py`：内存总线 `test_ws_receives_draw_update` 与 fakeredis 共享 `FakeServer` 的 `test_redis_eventbus_pubsub` 均通过。
- **P5.D（完成）**：Docker 多阶段 web 目标 + compose + CI。新增 `requirements-web.txt`（剥离 PySide6/Qt/Pillow/matplotlib/openpyxl/Pygments/markdown，保留 numpy+ML 栈+web 依赖+redis——因策略模块顶层导入 `caipiao.ml`，ML 栈不可省，受核心层零侵入约束）；`Dockerfile.web` 多阶段（build 阶段装 torch CPU-only wheel，runtime 仅 venv+代码，无 Qt 库，EXPOSE 8000）；`frontend/Dockerfile`（node 构建→nginx:1.27-alpine）+ `frontend/nginx.conf`（同源托管 SPA，反向代理 `/auth /profiles /generate /backtest /stats /filters /me /apikeys /openapi /docs` 与 `/ws` 到 `web:8000`，含 SPA history 回退）；`docker-compose.yml` 编排 `web`+`frontend`+`redis`（web 经 `CAIPIAO_WEB_REDIS_URL` 启用 Redis 总线）；新增 `.dockerignore`；CI 增加 `web` job（`requirements-web.txt`+torch CPU+pytest+redis+fakeredis，跑 `tests/web`）；新增 `docs/phase5_deploy.md`。
- **P5.E（完成）**：多用户权限分级 + 管理员后台。`User.role` 列（默认 `user`，`init_db` 对旧表做 `ALTER TABLE` 轻量迁移补齐 `role` 列）；`deps.require_admin` 依赖（非管理员 403）；注册时首个用户自动成为管理员（初始化引导）；新增 `routers/admin.py`：`GET /admin/stats`（用户数/管理员数/API Key 数/累计调用）、`GET /admin/users`、`PATCH /admin/users/{id}/role`（admin/user，正则校验）、`DELETE /admin/users/{id}`（禁止操作自身，级联删 API Key）；`UserOut` 增加 `role` 及 `RoleUpdate`/`UserAdminOut`/`AdminStats` schema；前端新增 `Admin.vue`（仅 `role==admin` 显示「管理」标签，调 `/me` 取角色）、`client.ts` 新增 `getMe/getAdminStats/listAdminUsers/setUserRole/deleteUser`；测试 `test_admin.py` 5 例全过。核心层零侵入。

## 9.1 后期增强（回测接入真实奖级）
- 原 P5.A 回测采用「轻量近似」（主号组全中即记为命中，不计算奖金）。已升级为调用核心层
  `core.prize.calculate_prize`（双色球/大乐透/福彩3D/排列3/排列5/7星彩/快乐8/广东36选7 的真实奖级表）：
  每注按各号组命中数判定奖级与固定奖金，浮动奖（一/二等奖等）单独计数（不计入盈亏）；
  汇总返回 `float_prize_count` 与 `tier_breakdown`（各奖级命中注数分布）。前端回测视图展示
  每期「最佳奖级 / 固定奖金 / 浮动奖数」及全局奖级分布。`save_single` 已支持的逐注
  `prize_name`/`prize_amount` 明细一并持久化。核心层零侵入。

- 回测历史「单期明细钻取」：`GET /backtest/{id}?kind=single` 现在解析 `groups`/`hits`
  JSON 并返回结构化 `tickets` 列表（`BacktestTicketOut`：ticket_index/groups/hits/
  prize_name/prize_amount/is_first）；前端新增「详情」操作，单期展示每注号码、命中数、
  奖级与奖金（浮动奖标“浮动”），批量为汇总（total_rounds/first_ticket_hit_count/
  ticket_index_hits）。core 零侵入。

## 9. 风险与注意
- **核心层零侵入**：web 包只 import 核心层，绝不动 `caipiao/ui`/`caipiao/app`；若发现核心层隐式依赖 PySide，单独隔离（已确认 core/data/persistence 不依赖 ui）。
- **ML 层排除**：回测/预测若触发 ML 层，按既定约定排除在覆盖率统计外（torch/sklearn 环境差异）。
- **安全**：JWT 密钥来自配置/环境变量，不硬编码；密码 bcrypt 哈希；所有入参经 Pydantic 校验。
- **数据可用性**：`/generate` 依赖本地开奖数据（`.caipiao/`），无数据时策略会报错——切片阶段返回 4xx 友好提示；后续阶段加 `/fetch` 拉取。
