"""Web 后端 uvicorn 入口。

启动：``uvicorn web_main:app --reload``
该模块只组装 FastAPI 应用，不依赖 PySide/桌面 UI，可与桌面应用并行运行。
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from caipiao.web.config import CORS_ORIGINS, DATA_ROOT
from caipiao.web.db import init_db
from caipiao.web.eventbus import bus
from caipiao.web.monitoring import MonitoringMiddleware
from caipiao.web.ratelimit import limiter
from caipiao.web.realtime_monitor import get_monitor
from caipiao.web.routers import (
    admin,
    ai_analysis,
    ai_predict,
    analytics,
    api_keys,
    audit,
    auth,
    backtest,
    behavior,
    backup,
    chatbot,
    collaboration,
    community,
    config,
    developer,
    devops,
    distributed,
    favorites,
    fetch,
    filters,
    generate,
    governance,
    i18n,
    logs,
    message_queue,
    monitoring,
    plugins,
    profiles,
    qa,
    realtime,
    release,
    reports,
    scheduler,
    services,
    stats,
    tasks,
    tenants,
    user,
    user_profile,
    visualization,
    workflows,
)
from caipiao.web.ws import router as ws_router


async def _draw_poller() -> None:
    """后台定时拉取各彩种最新开奖并发布到事件总线（实时推送生产化）。"""
    import asyncio
    import os

    from caipiao.core.profile import list_profiles
    from caipiao.data.repository import DrawRepository

    interval = int(os.getenv("CAIPIAO_WEB_PULL_INTERVAL", "60"))
    if interval <= 0:
        return
    seen: dict[str, str] = {}
    while True:
        await asyncio.sleep(interval)
        try:
            for profile in list_profiles():
                repo = DrawRepository(DATA_ROOT / profile.storage_file, profile)
                latest = repo.get_latest()
                if latest is None:
                    continue
                key = f"{profile.key}:{latest.draw_date}:{latest.issue}"
                if seen.get(profile.key) == key:
                    continue
                seen[profile.key] = key
                bus.publish(
                    {
                        "type": "draw_update",
                        "profile": profile.key,
                        "draw_date": str(latest.draw_date),
                        "issue": latest.issue,
                        "draw": latest.to_dict(),
                    }
                )
        except Exception:
            # 单轮失败不影响后续轮次
            continue


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # 创建用户 / API Key / 用量表（幂等）
    # 启动实时推送：Redis 总线监听（若有）+ 后台开奖拉取 + 实时指标采集
    bg_tasks: list[asyncio.Task] = []
    start_fn = getattr(bus, "start", None)
    if callable(start_fn):
        try:
            bg_tasks.append(start_fn())
        except Exception:
            pass
    bg_tasks.append(asyncio.create_task(_draw_poller()))
    rt = get_monitor()
    try:
        await rt.start()
    except Exception:
        pass
    try:
        yield
    finally:
        try:
            await rt.stop()
        except Exception:
            pass
        for t in bg_tasks:
            t.cancel()


# Swagger 分层：默认关闭公开文档，提供 /docs-private 展示完整 schema（见下方路由）
app = FastAPI(
    title="彩票号码生成器 Web API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_exception_handler(
    RateLimitExceeded,
    lambda request, exc: __import__("starlette").responses.JSONResponse(
        status_code=429, content={"detail": "请求过于频繁，请稍后再试"}
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 监控中间件：统计每个 HTTP 请求的耗时 / 状态码 / 5xx 错误（需在路由器注册前挂载）
app.add_middleware(MonitoringMiddleware)

app.include_router(auth.router, tags=["auth"])
# stats 必须先于 profiles 注册：stats 里的静态路径 /profiles/compare-lotteries
# 否则会被 profiles 的动态段 /profiles/{key} 抢先匹配（FastAPI 按注册顺序匹配）。
app.include_router(stats.router, tags=["stats"])
app.include_router(profiles.router, tags=["profiles"])
app.include_router(generate.router, tags=["generate"])
app.include_router(backtest.router, tags=["backtest"])
app.include_router(filters.router, tags=["filters"])
app.include_router(favorites.router, tags=["favorites"])
app.include_router(tasks.router, tags=["tasks"])
app.include_router(audit.router, tags=["audit"])
app.include_router(community.router, tags=["community"])
app.include_router(ai_analysis.router, tags=["ai_analysis"])
app.include_router(monitoring.router, tags=["monitoring"])
app.include_router(chatbot.router, tags=["chatbot"])
app.include_router(plugins.router, tags=["plugins"])
app.include_router(realtime.router, tags=["realtime"])
app.include_router(collaboration.router, tags=["collaboration"])
app.include_router(reports.router, tags=["reports"])
app.include_router(analytics.router, tags=["analytics"])
app.include_router(ai_predict.router, tags=["ai_predict"])
app.include_router(workflows.router, tags=["workflows"])
app.include_router(visualization.router, tags=["visualization"])
app.include_router(scheduler.router, tags=["scheduler"])
app.include_router(developer.router, tags=["developer"])
app.include_router(behavior.router, tags=["behavior"])
app.include_router(i18n.router, tags=["i18n"])
app.include_router(message_queue.router, tags=["message_queue"])
app.include_router(config.router, tags=["config"])
app.include_router(user_profile.router, tags=["user_profile"])
app.include_router(backup.router, tags=["backup"])
app.include_router(tenants.router, tags=["tenants"])
app.include_router(logs.router, tags=["logs"])
app.include_router(services.router, tags=["services"])
app.include_router(distributed.router, tags=["distributed"])
app.include_router(release.router, tags=["release"])
app.include_router(governance.router, tags=["governance"])
app.include_router(qa.router, tags=["qa"])
app.include_router(devops.router, tags=["devops"])
app.include_router(user.router, tags=["user"])
app.include_router(api_keys.router, tags=["api_keys"])
app.include_router(admin.router, tags=["admin"])
app.include_router(fetch.router, tags=["fetch"])
app.include_router(ws_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# --------------------------------------------------------------------------- #
# Swagger 分层：公开子集（无需鉴权）+ 私有完整文档（需 Bearer）
# --------------------------------------------------------------------------- #
_PUBLIC_PATHS = {"/health", "/profiles", "/auth/register", "/auth/login"}


@app.get("/openapi-public.json", include_in_schema=False)
def openapi_public():
    """公开 OpenAPI 子集：仅暴露无需鉴权的端点（健康检查 / 彩种 / 认证）。"""
    full = app.openapi()
    paths = {
        p: methods
        for p, methods in full["paths"].items()
        if any(p == pub or p.startswith(pub + "/") for pub in _PUBLIC_PATHS)
    }
    return {**full, "paths": paths}


@app.get("/docs-public", include_in_schema=False)
def docs_public():
    """公开文档页（Swagger UI，仅含公开端点）。"""
    from fastapi.openapi.docs import get_swagger_ui_html

    return get_swagger_ui_html("/openapi-public.json", title="公开 API 文档")


@app.get("/openapi-private.json", include_in_schema=False)
def openapi_private():
    """完整 OpenAPI 文档（含全部端点，供已登录用户/管理员查看）。"""
    return app.openapi()


@app.get("/docs-private", include_in_schema=False)
def docs_private():
    """完整文档页（Swagger UI，需鉴权后访问，含全部端点）。"""
    from fastapi.openapi.docs import get_swagger_ui_html

    return get_swagger_ui_html("/openapi-private.json", title="完整 API 文档（需登录）")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("web_main:app", host="0.0.0.0", port=8000, reload=False)
