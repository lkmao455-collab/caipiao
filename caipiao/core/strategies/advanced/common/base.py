"""高级策略公共接口（仅含真正通用工具）."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from .....data.models import DrawRecord
from ....strategy import GenerationStrategy, StrategyMetadata


class UnsupportedLotteryError(NotImplementedError):
    """该彩种尚未实现此高级策略。"""


class AdvancedStrategy(GenerationStrategy):
    """高级策略基类：只提供历史记录处理和 metadata 模板。"""

    _id: str = ""
    _name: str = ""
    _description: str = ""
    is_ml: bool = False

    def _records_from_options(self, options: Dict[str, Any]) -> List[DrawRecord]:
        from ...common.records import records_from_options
        return records_from_options(options)

    def _get_history(self, options: Dict[str, Any]) -> List[DrawRecord]:
        history = options.get("history", [])
        history_count = options.get("history_count", -1)
        records = self._records_from_options(options)
        if isinstance(history_count, int) and history_count > 0 and len(records) > history_count:
            records = records[-history_count:]
        return records

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id=self._id,
            name=self._name,
            description=self._description,
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "history_count": {
                "type": "int",
                "label": "使用历史记录期数",
                "default": -1,
                "min": -1,
                "max": 10000,
            },
            "seed": {
                "type": "int",
                "label": "随机种子（可选）",
                "default": None,
                "min": 0,
                "max": 999999999,
            },
        }

    def validate_options(self, options: Dict[str, Any]) -> None:
        history = options.get("history", [])
        if len(history) < 30:
            raise ValueError(f"{self.metadata.name} 策略需要至少 30 期历史数据")
