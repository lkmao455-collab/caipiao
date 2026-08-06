"""Web 后端 uvicorn 入口。

启动：``uvicorn web_main:app --reload``
该模块只组装 FastAPI 应用，不依赖 PySide/桌面 UI，可与桌面应用并行运行。
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from caipiao.web.config import CORS_ORIGINS
from caipiao.web.db import init_db
from caipiao.web.routers import (
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # 创建用户 / API Key 表（幂等）
    yield


app = FastAPI(title="彩票号码生成器 Web API", version="0.1.0", lifespan=lifespan)

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
app.include_router(ws_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("web_main:app", host="0.0.0.0", port=8000, reload=False)
