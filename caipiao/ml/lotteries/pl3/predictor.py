"""PL3 专属 ML 预测器（当前委托通用实现，保留隔离边界）."""

from __future__ import annotations

from pathlib import Path

from ....core.profile import PL3
from ....data.models import DrawRecord
from ...common.predictor import BaseMLPredictor as GenericMLPredictor


class PL3Predictor(GenericMLPredictor):
    """基于历史数据的 PL3 专属机器学习号码推荐器."""

    def __init__(
        self,
        records: list[DrawRecord],
        lookback: int = 50,
        model_path: Path | None = None,
        backend: str = "xgboost",
        temp_dir: str | None = None,
    ) -> None:
        super().__init__(
            records=records,
            profile=PL3,
            lookback=lookback,
            model_path=model_path,
            backend=backend,
            temp_dir=temp_dir,
        )
