"""生成路由：调用核心层引擎产出号码。支持 JWT 或 API Key 鉴权。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...core.profile import get_profile as _get_profile
from ...data.repository import DrawRepository
from ..config import DATA_ROOT
from ..db import get_db
from ..deps import get_current_principal
from ..engine import get_profile_engine
from ..eventbus import bus
from ..filters_registry import apply_filters
from ..metering import record_usage
from ..ratelimit import limiter
from ..schemas import GenerateRequest, GenerateResponse
from starlette.requests import Request

router = APIRouter(prefix="/generate", tags=["generate"])


def _load_history(profile, limit: int = 300) -> list:
    """从本地开奖数据加载历史（复用桌面端 .caipiao 数据）。"""
    storage_path = DATA_ROOT / profile.storage_file
    repo = DrawRepository(storage_path, profile)
    return repo.get_recent(limit)


@router.post("", response_model=GenerateResponse)
@limiter.limit("60/minute")
def generate(request: Request, req: GenerateRequest, principal=Depends(get_current_principal), db: Session = Depends(get_db)) -> GenerateResponse:
    try:
        profile = _get_profile(req.profile_key)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    options = dict(req.options or {})
    options["history"] = _load_history(profile)

    engine = get_profile_engine(req.profile_key)
    try:
        tickets = engine.generate(req.strategy_id, req.count, options)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except Exception as exc:  # 数据缺失等运行期问题，对用户友好返回
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"生成失败：{exc}") from exc

    # 后过滤：核心层过滤函数由 web 侧引用并调用，零侵入
    filtered = apply_filters(req.profile_key, tickets, options["history"], [p.model_dump() for p in req.post_filters])

    bus.publish(
        {
            "type": "generate",
            "user": principal.username,
            "profile": req.profile_key,
            "strategy": req.strategy_id,
            "count": len(tickets),
            "filtered_count": len(filtered),
        }
    )

    record_usage(db, principal, "generate", 1)

    return GenerateResponse(
        profile_key=req.profile_key,
        strategy_id=req.strategy_id,
        count=len(tickets),
        filtered_count=len(filtered),
        tickets=[t.to_dict() for t in filtered],
    )

