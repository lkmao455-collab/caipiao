# Phase 5 规划：企业级（Web / 多用户 / 开放 API / 实时推送）

> 状态：规划已批准，垂直切片实现中。本文件为完整架构设计 + 分阶段路线图。

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
- **P5.0（本次）**：计划 + 垂直切片（后端骨架 + 认证 + profiles/generate/backtest + 最小前端 + 测试）。
- **P5.A**：完整前端（回测 UI、统计图表、过滤规则编辑器）。
- **P5.B**：开放平台限流（slowapi）、用量计量、公开 Swagger 分层。
- **P5.C**：实时推送生产化（后台定时拉取开奖 + Redis 持久化事件总线）。
- **P5.D**：Docker 多阶段 web 目标（剥离 PySide6/Qt 系统库）、`docker-compose` 增 web 服务、CI。
- **P5.E**：多用户权限分级、管理员后台。

## 9. 风险与注意
- **核心层零侵入**：web 包只 import 核心层，绝不动 `caipiao/ui`/`caipiao/app`；若发现核心层隐式依赖 PySide，单独隔离（已确认 core/data/persistence 不依赖 ui）。
- **ML 层排除**：回测/预测若触发 ML 层，按既定约定排除在覆盖率统计外（torch/sklearn 环境差异）。
- **安全**：JWT 密钥来自配置/环境变量，不硬编码；密码 bcrypt 哈希；所有入参经 Pydantic 校验。
- **数据可用性**：`/generate` 依赖本地开奖数据（`.caipiao/`），无数据时策略会报错——切片阶段返回 4xx 友好提示；后续阶段加 `/fetch` 拉取。
