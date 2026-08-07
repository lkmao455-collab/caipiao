"""后过滤规则端点：列出某彩种可用过滤函数及其参数 schema。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from starlette.requests import Request

from ...core.profile import get_profile as _get_profile
from ..db import get_db
from ..filters_registry import get_profile_filter
from ..ratelimit import default_limit, limiter

router = APIRouter(prefix="/profiles", tags=["filters"])


@router.get("/{key}/filters")
@limiter.limit(default_limit)
def list_filters(request: Request, key: str, db: Session = Depends(get_db)) -> dict:
    """返回某彩种可用后过滤函数名与参数 schema（前端用于动态渲染编辑器）。"""
    try:
        _get_profile(key)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    prof = get_profile_filter(key)
    if prof is None:
        return {"profile_key": key, "available": False, "params": []}

    params = [
        {
            "name": p.name,
            "type": p.type,
            "default": p.default,
            "min": p.min,
            "max": p.max,
            "description": p.description,
        }
        for p in prof.params
    ]
    return {"profile_key": key, "available": True, "params": params}
