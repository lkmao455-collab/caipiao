"""AI 预测路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..ai_engine import get_prediction_engine
from ..deps import get_current_principal

router = APIRouter(prefix="/ai", tags=["ai"])


class PredictRequest(BaseModel):
    profile_key: str
    model_name: str = "ensemble"
    num_range: list[int] = [1, 33]
    count: int = 6


class BatchPredictRequest(BaseModel):
    profile_key: str
    model_names: list[str] = ["frequency", "markov", "ensemble"]
    num_range: list[int] = [1, 33]
    count: int = 6


@router.post("/predict")
def predict(
    req: PredictRequest,
    principal=Depends(get_current_principal),
):
    engine = get_prediction_engine()
    result = engine.predict(
        profile_key=req.profile_key,
        model_name=req.model_name,
        num_range=tuple(req.num_range),
        count=req.count,
    )
    if not result:
        return {"error": "模型不存在"}
    return {
        "model": result.model_name,
        "numbers": result.predicted_numbers,
        "confidence": result.confidence,
        "probabilities": dict(sorted(result.probabilities.items(), key=lambda x: x[1], reverse=True)[:20]),
    }


@router.post("/batch-predict")
def batch_predict(
    req: BatchPredictRequest,
    principal=Depends(get_current_principal),
):
    engine = get_prediction_engine()
    results = engine.batch_predict(
        profile_key=req.profile_key,
        model_names=req.model_names,
        num_range=tuple(req.num_range),
        count=req.count,
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
def list_models(
    principal=Depends(get_current_principal),
):
    engine = get_prediction_engine()
    return {"models": engine.get_model_names()}


@router.get("/history")
def get_prediction_history(
    limit: int = 10,
    principal=Depends(get_current_principal),
):
    engine = get_prediction_engine()
    return {"predictions": engine.get_recent_predictions(limit)}
