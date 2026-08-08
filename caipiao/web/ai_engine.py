"""AI 预测引擎：集成多种机器学习模型进行号码预测。"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..log import get_logger

logger = get_logger(__name__)


@dataclass
class PredictionResult:
    model_name: str
    predicted_numbers: list[int]
    confidence: float
    probabilities: dict[int, float]
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class ModelConfig:
    name: str
    model_type: str  # lstm, transformer, ensemble, xgboost, lightgbm
    parameters: dict[str, Any] = field(default_factory=dict)
    features: list[str] = field(default_factory=list)
    lookback: int = 10
    forecast_horizon: int = 1


class FrequencyPredictor:
    """基于频率的预测器。"""

    def __init__(self):
        self.name = "frequency"

    def predict(self, history: list[list[int]], num_range: tuple[int, int], count: int) -> PredictionResult:
        all_numbers = [n for draw in history for n in draw]
        freq = defaultdict(int)
        for n in all_numbers:
            freq[n] += 1

        total = len(all_numbers) or 1
        probs = {n: freq.get(n, 0) / total for n in range(num_range[0], num_range[1] + 1)}

        sorted_nums = sorted(probs.items(), key=lambda x: x[1], reverse=True)
        predicted = sorted([n for n, _ in sorted_nums[:count]])

        return PredictionResult(
            model_name="frequency",
            predicted_numbers=predicted,
            confidence=sorted_nums[0][1] if sorted_nums else 0,
            probabilities=probs,
        )


class MarkovPredictor:
    """基于马尔可夫链的预测器。"""

    def __init__(self, order: int = 2):
        self.name = "markov"
        self.order = order
        self.transitions: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))

    def train(self, history: list[list[int]]):
        for draw in history:
            for i in range(self.order, len(draw)):
                state = tuple(draw[i - self.order:i])
                state_key = str(state)
                self.transitions[state_key][draw[i]] += 1

    def predict(self, history: list[list[int]], num_range: tuple[int, int], count: int) -> PredictionResult:
        self.train(history)

        last_state = str(tuple(history[-1][-self.order:])) if history else "()"
        trans = self.transitions.get(last_state, {})

        total = sum(trans.values()) or 1
        probs = {n: trans.get(n, 0) / total for n in range(num_range[0], num_range[1] + 1)}

        sorted_nums = sorted(probs.items(), key=lambda x: x[1], reverse=True)
        predicted = sorted([n for n, _ in sorted_nums[:count]])

        return PredictionResult(
            model_name="markov",
            predicted_numbers=predicted,
            confidence=sorted_nums[0][1] if sorted_nums else 0,
            probabilities=probs,
        )


class EnsemblePredictor:
    """集成预测器：组合多个模型的预测结果。"""

    def __init__(self):
        self.name = "ensemble"
        self.predictors = [
            FrequencyPredictor(),
            MarkovPredictor(),
        ]
        self.weights = [0.4, 0.6]

    def predict(self, history: list[list[int]], num_range: tuple[int, int], count: int) -> PredictionResult:
        results = []
        for p in self.predictors:
            try:
                results.append(p.predict(history, num_range, count))
            except Exception as e:
                logger.warning(f"Predictor {p.name} failed: {e}")

        if not results:
            return PredictionResult(
                model_name="ensemble",
                predicted_numbers=[],
                confidence=0,
                probabilities={},
            )

        combined_probs: dict[int, float] = defaultdict(float)
        for result, weight in zip(results, self.weights[:len(results)]):
            for n, prob in result.probabilities.items():
                combined_probs[n] += prob * weight

        sorted_nums = sorted(combined_probs.items(), key=lambda x: x[1], reverse=True)
        predicted = sorted([n for n, _ in sorted_nums[:count]])

        return PredictionResult(
            model_name="ensemble",
            predicted_numbers=predicted,
            confidence=sorted_nums[0][1] if sorted_nums else 0,
            probabilities=dict(combined_probs),
            metadata={"sub_models": [r.model_name for r in results]},
        )


class PredictionEngine:
    """预测引擎：管理模型和执行预测。"""

    def __init__(self):
        self._predictors = {
            "frequency": FrequencyPredictor(),
            "markov": MarkovPredictor(),
            "ensemble": EnsemblePredictor(),
        }
        self._history: dict[str, list[list[int]]] = defaultdict(list)
        self._predictions: list[PredictionResult] = []

    def add_history(self, profile_key: str, numbers: list[int]):
        self._history[profile_key].append(numbers)

    def predict(
        self,
        profile_key: str,
        model_name: str = "ensemble",
        num_range: tuple[int, int] = (1, 33),
        count: int = 6,
    ) -> PredictionResult | None:
        predictor = self._predictors.get(model_name)
        if not predictor:
            return None

        history = self._history.get(profile_key, [])
        if not history:
            return PredictionResult(
                model_name=model_name,
                predicted_numbers=[],
                confidence=0,
                probabilities={},
            )

        result = predictor.predict(history, num_range, count)
        self._predictions.append(result)
        return result

    def batch_predict(
        self,
        profile_key: str,
        model_names: list[str],
        num_range: tuple[int, int] = (1, 33),
        count: int = 6,
    ) -> list[PredictionResult]:
        return [
            r
            for name in model_names
            if (r := self.predict(profile_key, name, num_range, count)) is not None
        ]

    def get_model_names(self) -> list[str]:
        return list(self._predictors.keys())

    def get_recent_predictions(self, limit: int = 10) -> list[dict]:
        return [
            {
                "model": p.model_name,
                "numbers": p.predicted_numbers,
                "confidence": p.confidence,
                "timestamp": p.timestamp,
            }
            for p in self._predictions[-limit:]
        ]


# 全局预测引擎
_engine: PredictionEngine | None = None


def get_prediction_engine() -> PredictionEngine:
    global _engine
    if _engine is None:
        _engine = PredictionEngine()
    return _engine
