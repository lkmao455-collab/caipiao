"""彩种与策略路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from starlette.requests import Request

from ...core.profile import get_profile as _get_profile
from ..db import get_db
from ..engine import available_profiles, list_profile_strategies
from ..ratelimit import default_limit, limiter
from ..schemas import ProfileOut, StrategyOut

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("", response_model=list[ProfileOut])
@limiter.limit(default_limit)
def list_profiles(request: Request) -> list[ProfileOut]:
    return [
        ProfileOut(
            key=p.key,
            name=p.name,
            category=p.category,
            subtitle=p.subtitle,
            group_keys=p.group_keys,
        )
        for p in available_profiles()
    ]


@router.get("/{key}", response_model=ProfileOut)
def get_profile(key: str) -> ProfileOut:
    try:
        p = _get_profile(key)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return ProfileOut(
        key=p.key,
        name=p.name,
        category=p.category,
        subtitle=p.subtitle,
        group_keys=p.group_keys,
    )


@router.get("/{key}/strategies", response_model=list[StrategyOut])
def strategies(key: str) -> list[StrategyOut]:
    try:
        _get_profile(key)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    out: list[StrategyOut] = []
    for strategy in list_profile_strategies(key):
        meta = strategy.metadata
        out.append(
            StrategyOut(
                id=meta.id,
                name=meta.name,
                description=meta.description,
                configurable=meta.configurable,
                config_schema=strategy.get_config_schema(),
            )
        )
    return out
