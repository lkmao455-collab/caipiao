"""QXC 专属 ML 预测器（当前委托通用实现，保留隔离边界）."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ....core.profile import QXC
from ....data.models import DrawRecord
from ...generic_predictor import GenericMLPredictor


class QXCPredictor(GenericMLPredictor):
    """基于历史数据的 QXC 专属机器学习号码推荐器."""

    def __init__(
        self,
        records: list[DrawRecord],
        lookback: int = 50,
        model_path: Optional[Path] = None,
        backend: str = "xgboost",
        temp_dir: Optional[str] = None,
    ) -> None:
        super().__init__(
            records=records,
            profile=QXC,
            lookback=lookback,
            model_path=model_path,
            backend=backend,
            temp_dir=temp_dir,
        )
