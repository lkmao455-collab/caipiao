"""数据拉取路由：触发从数据源抓取最新开奖并写入本地仓库。

- ``POST /profiles/{key}/fetch``：单彩种拉取（mode=latest|all）
- ``POST /fetch``：遍历全部彩种拉取
两条路由均复用核心层 ``LotteryDataFetcher`` / ``DrawRepository``，**零侵入**，
并对新增记录通过事件总线发布 ``draw_update``（供 WebSocket 实时推送）。
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ...core.profile import get_profile as _get_profile, list_profiles
from ...data.fetcher import LotteryDataFetcher
from ...data.models import DrawRecord
from ...data.repository import DrawRepository
from ..config import DATA_ROOT
from ..deps import get_current_user
from ..eventbus import bus
from ..models import User
from ..ratelimit import limiter
from ..schemas import FetchRequest, FetchResult

logger = logging.getLogger(__name__)

router = APIRouter(tags=["fetch"])


def _fetch_one(profile, mode: str) -> tuple[list[DrawRecord], int, int, Optional[dict]]:
    """抓取并写入单彩种数据，返回 (记录列表, 新增数, 总数, 最新记录 dict)。"""
    fetcher = LotteryDataFetcher(profile)
    if mode == "latest":
        rec = fetcher.fetch_latest()
        records = [rec] if rec is not None else []
    else:
        records = fetcher.fetch_all()

    if not records:
        return [], 0, 0, None

    repo = DrawRepository(DATA_ROOT / profile.storage_file, profile)
    before = {r.issue for r in repo.get_all()}
    added = repo.update(records)
    after = repo.get_all()
    # 仓库会对期号做归一化（如 20990002 -> 2099002），新增判定以归一化后的期号为准，
    # 发布的事件也使用归一化期号，与后台 poller 的 draw_update 保持一致。
    new_issues = {r.issue for r in after} - before
    total = len(after)

    for r in after:
        if r.issue not in new_issues:
            continue
        try:
            bus.publish(
                {
                    "type": "draw_update",
                    "profile": profile.key,
                    "draw_date": str(r.draw_date),
                    "issue": r.issue,
                    "draw": r.to_dict(),
                }
            )
        except Exception:  # 发布失败不影响写入结果
            logger.warning("发布 draw_update 事件失败: %s", r.issue)

    latest = repo.get_latest()
    return records, added, total, (latest.to_dict() if latest is not None else None)


@router.post("/profiles/{key}/fetch", response_model=FetchResult)
@limiter.limit("10/minute")
def fetch_profile(
    request: Request,
    key: str,
    body: Optional[FetchRequest] = None,
    current: User = Depends(get_current_user),
) -> FetchResult:
    """拉取指定彩种最新开奖（或全量）并写入本地仓库。"""
    body = body or FetchRequest()
    try:
        profile = _get_profile(key)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    try:
        records, added, total, latest = _fetch_one(profile, body.mode)
    except HTTPException:
        raise
    except Exception as exc:  # 网络/解析失败
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"抓取失败：{exc}") from exc
    return FetchResult(
        profile_key=key,
        mode=body.mode,
        fetched=len(records),
        added=added,
        total=total,
        latest=latest,
    )


@router.post("/fetch", response_model=list[FetchResult])
@limiter.limit("5/minute")
def fetch_all(
    request: Request,
    body: Optional[FetchRequest] = None,
    current: User = Depends(get_current_user),
) -> list[FetchResult]:
    """遍历全部彩种拉取数据（单彩种失败不影响其余）。"""
    body = body or FetchRequest()
    results: list[FetchResult] = []
    for profile in list_profiles():
        try:
            records, added, total, latest = _fetch_one(profile, body.mode)
            results.append(
                FetchResult(
                    profile_key=profile.key,
                    mode=body.mode,
                    fetched=len(records),
                    added=added,
                    total=total,
                    latest=latest,
                )
            )
        except Exception as exc:
            logger.warning("彩种 %s 拉取失败：%s", profile.key, exc)
            continue
    return results
