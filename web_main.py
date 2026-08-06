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
from caipiao.web.ratelimit import limiter
from caipiao.web.routers import (
    admin,
    api_keys,
    auth,
    backtest,
    filters,
    generate,
    profiles,
    stats,
    user,
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
    # 启动实时推送：Redis 总线监听（若有）+ 后台开奖拉取
    bg_tasks: list[asyncio.Task] = []
    start_fn = getattr(bus, "start", None)
    if callable(start_fn):
        try:
            bg_tasks.append(start_fn())
        except Exception:
            pass
    bg_tasks.append(asyncio.create_task(_draw_poller()))
    try:
        yield
    finally:
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

app.include_router(auth.router, tags=["auth"])
app.include_router(profiles.router, tags=["profiles"])
app.include_router(generate.router, tags=["generate"])
app.include_router(backtest.router, tags=["backtest"])
app.include_router(stats.router, tags=["stats"])
app.include_router(filters.router, tags=["filters"])
app.include_router(user.router, tags=["user"])
app.include_router(api_keys.router, tags=["api_keys"])
app.include_router(admin.router, tags=["admin"])
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
