"""AI 预测路由。

通过 ``DrawRepository`` 加载某彩种的开奖历史并注入 ``PredictionEngine``，
使 /ai/predict 基于真实历史给出预测（此前历史从未注入，预测恒为空）。
号码范围与个数默认取自该彩种主号组（NumberGroup.lo/hi/count），
也可在请求中显式覆盖。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from starlette.requests import Request

from ...core.profile import get_profile as _get_profile
from ...data.repository import DrawRepository
from ..ai_engine import get_prediction_engine
from ..config import DATA_ROOT
from ..deps import get_current_principal
from ..ratelimit import default_limit, limiter

router = APIRouter(prefix="/ai", tags=["ai"])


class PredictRequest(BaseModel):
    profile_key: str
    model_name: str = "ensemble"
    num_range: list[int] | None = None
    count: int | None = None


class BatchPredictRequest(BaseModel):
    profile_key: str
    model_names: list[str] = ["frequency", "markov", "ensemble"]
    num_range: list[int] | None = None
    count: int | None = None


def _load_history(profile_key: str) -> list[list[int]]:
    """从开奖数据加载某彩种主号组历史（供预测引擎使用）。"""
    profile = _get_profile(profile_key)
    group = profile.primary_group
    repo = DrawRepository(DATA_ROOT / profile.storage_file, profile)
    records = repo.get_all()
    return [r.groups.get(group.key, []) for r in records if r.groups.get(group.key)]


@router.post("/predict")
@limiter.limit(default_limit)
def predict(
    request: Request,
    req: PredictRequest,
    principal=Depends(get_current_principal),
):
    profile = _get_profile(req.profile_key)
    group = profile.primary_group
    num_range = tuple(req.num_range) if req.num_range else (group.lo, group.hi)
    count = req.count or group.count

    engine = get_prediction_engine()
    engine.set_history(req.profile_key, _load_history(req.profile_key))
    result = engine.predict(
        profile_key=req.profile_key,
        model_name=req.model_name,
        num_range=num_range,
        count=count,
    )
    if not result:
        return {"error": "模型不存在"}
    return {
        "model": result.model_name,
        "numbers": result.predicted_numbers,
        "confidence": result.confidence,
        "probabilities": dict(
            sorted(result.probabilities.items(), key=lambda x: x[1], reverse=True)[:20]
        ),
    }


@router.post("/batch-predict")
@limiter.limit(default_limit)
def batch_predict(
    request: Request,
    req: BatchPredictRequest,
    principal=Depends(get_current_principal),
):
    profile = _get_profile(req.profile_key)
    group = profile.primary_group
    num_range = tuple(req.num_range) if req.num_range else (group.lo, group.hi)
    count = req.count or group.count

    engine = get_prediction_engine()
    engine.set_history(req.profile_key, _load_history(req.profile_key))
    results = engine.batch_predict(
        profile_key=req.profile_key,
        model_names=req.model_names,
        num_range=num_range,
        count=count,
    )
    return {
        "predictions": [
            {
                "model": r.model_name,
                "numbers": r.predicted_numbers,
                "confidence": r.confidence,
            }
            for r in results
        ]
    }


@router.get("/models")
@limiter.limit(default_limit)
def list_models(
    request: Request,
    principal=Depends(get_current_principal),
):
    engine = get_prediction_engine()
    return {"models": engine.get_model_names()}


@router.get("/history")
@limiter.limit(default_limit)
def get_prediction_history(
    request: Request,
    limit: int = 10,
    principal=Depends(get_current_principal),
):
    engine = get_prediction_engine()
    return {"predictions": engine.get_recent_predictions(limit)}
