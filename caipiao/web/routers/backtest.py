"""回测路由（简化版）：以最新一期开奖为基准统计生成号码重合数。

说明：严格走查式回测需要策略支持「仅使用截止某期的数据生成」，当前核心策略
以最新数据生成，故此处提供简化评估，用于演示接口能力；完整回测见路线图 P5.A。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...core.profile import get_profile as _get_profile
from ...data.repository import DrawRepository
from ..config import DATA_ROOT
from ..db import get_db
from ..deps import get_current_principal
from ..engine import get_profile_engine
from ..schemas import BacktestRequest, BacktestResponse, BacktestResultItem

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.post("", response_model=BacktestResponse)
def backtest(req: BacktestRequest, principal=Depends(get_current_principal), db: Session = Depends(get_db)) -> BacktestResponse:
    try:
        profile = _get_profile(req.profile_key)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    repo = DrawRepository(DATA_ROOT / profile.storage_file, profile)
    latest = repo.get_latest()
    if latest is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "本地无开奖数据，无法回测")

    options = dict(req.options or {})
    options["history"] = repo.get_recent(300)

    engine = get_profile_engine(req.profile_key)
    try:
        tickets = engine.generate(req.strategy_id, req.count, options)
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"生成失败：{exc}") from exc

    results = [
        BacktestResultItem(
            ticket=t.to_dict(),
            matches={
                g: len(set(t.groups.get(g, [])) & set(latest.groups.get(g, [])))
                for g in latest.groups
            },
        )
        for t in tickets
    ]

    return BacktestResponse(
        profile_key=req.profile_key,
        strategy_id=req.strategy_id,
        latest_draw=latest.to_dict(),
        results=results,
        note="简化回测：以最新一期开奖为基准统计生成号码重合数；非严格走查式回测。",
    )
