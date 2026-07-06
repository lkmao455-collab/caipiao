"""彩种上下文.

``LotteryContext`` 为单个彩种封装该彩种运行所需的全部对象：
档案（Profile）、生成引擎、数据仓库、分析器、历史管理器、抓取器。

双色球（ssq）使用原有的类/策略/分析器以保持 100% 兼容，
其它彩种使用通用（Profile 驱动）实现。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal

from ..core.engine import GenerationEngine
from ..core.profile import DEFAULT_KEY, LotteryProfile, SSQ, get_profile
from ..core.strategies import (
    BalancedStrategy,
    BayesianStrategy,
    MarkovChainStrategy,
    MLStrategy,
    OddEvenStrategy,
)
from ..core.strategies.generic import build_strategies as build_generic_strategies
from ..data.analyzer import DrawAnalyzer, LotteryAnalyzer
from ..data.fetcher import LotteryDataFetcher
from ..data.models import DrawRecord
from ..data.repository import DrawRepository
from ..persistence.history import HistoryManager


class LotteryContext(QObject):
    """单个彩种的运行时上下文."""

    data_changed = Signal()

    def __init__(
        self,
        profile: LotteryProfile,
        data_dir: Path,
        history_manager: HistoryManager | None = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.profile = profile
        self.data_dir = data_dir
        self.engine = GenerationEngine()
        self._register_strategies()

        self.data_repository = DrawRepository(
            data_dir / profile.storage_file, profile=profile
        )
        self.data_fetcher = LotteryDataFetcher(profile=profile)
        if profile.key == "ssq":
            self.data_analyzer: DrawAnalyzer = LotteryAnalyzer(
                self.data_repository.get_all()
            )
        else:
            self.data_analyzer = DrawAnalyzer(
                self.data_repository.get_all(), profile
            )

        # 历史记录所有彩种共用一份文件（按 Ticket.to_dict 中的 profile 区分）
        self.history_manager = history_manager or HistoryManager(
            data_dir / "history.json"
        )

    def register_builtin_strategies(self) -> None:
        if self.profile.key == "ssq":
            self.engine.register(BalancedStrategy())
            self.engine.register(OddEvenStrategy())
            self.engine.register(MLStrategy("xgboost"))
            self.engine.register(BayesianStrategy())
            self.engine.register(MarkovChainStrategy())
        elif self.profile.key == "3d":
            # 福彩3D：仅保留核心策略
            from ..core.strategies.generic import (
                GenericSmartHotColdStrategy,
                GenericMissingNumberStrategy,
                GenericXGBoostStrategy,
                GenericBalancedStrategy,
            )
            self.engine.register(GenericSmartHotColdStrategy(self.profile))
            self.engine.register(GenericMissingNumberStrategy(self.profile))
            self.engine.register(GenericXGBoostStrategy(self.profile))
            self.engine.register(GenericBalancedStrategy(self.profile))
        elif self.profile.key == "dlt":
            # 大乐透：仅保留XGBoost
            from ..core.strategies.generic import GenericXGBoostStrategy
            self.engine.register(GenericXGBoostStrategy(self.profile))
        elif self.profile.key == "pl3":
            # 排列3：智能冷热号、遗漏号追踪、历史均衡、XGBoost
            from ..core.strategies.generic import (
                GenericSmartHotColdStrategy,
                GenericMissingNumberStrategy,
                GenericBalancedStrategy,
                GenericXGBoostStrategy,
            )
            self.engine.register(GenericSmartHotColdStrategy(self.profile))
            self.engine.register(GenericMissingNumberStrategy(self.profile))
            self.engine.register(GenericBalancedStrategy(self.profile))
            self.engine.register(GenericXGBoostStrategy(self.profile))
        else:
            from ..core.strategies.generic import (
                GenericRandomStrategy, GenericExcludeIncludeStrategy,
                GenericLightGBMStrategy, GenericCatBoostStrategy,
            )
            for strategy in build_generic_strategies(self.profile):
                if isinstance(strategy, (GenericRandomStrategy, GenericExcludeIncludeStrategy,
                                         GenericLightGBMStrategy, GenericCatBoostStrategy)):
                    continue
                self.engine.register(strategy)

    def _register_strategies(self) -> None:
        self.register_builtin_strategies()

    def refresh_analyzer(self) -> None:
        records = self.data_repository.get_all()
        if self.profile.key == "ssq":
            self.data_analyzer = LotteryAnalyzer(records)
        else:
            self.data_analyzer = DrawAnalyzer(records, self.profile)
        self.data_changed.emit()

    def update_data(self, records: list[DrawRecord]) -> int:
        added = self.data_repository.update(records)
        self.refresh_analyzer()
        return added

    def clear_data(self) -> None:
        self.data_repository.clear()
        self.refresh_analyzer()


class ContextManager:
    """管理全部彩种上下文，按 key 懒加载."""

    def __init__(self, data_dir: Path, history_manager: HistoryManager) -> None:
        self.data_dir = data_dir
        self.history_manager = history_manager
        self._contexts: dict[str, LotteryContext] = {}

    def get(self, key: str) -> LotteryContext:
        if key not in self._contexts:
            profile = get_profile(key)
            self._contexts[key] = LotteryContext(
                profile, self.data_dir, history_manager=self.history_manager
            )
        return self._contexts[key]

    @property
    def ssq(self) -> LotteryContext:
        return self.get("ssq")

    def current(self, key: str | None = None) -> LotteryContext:
        return self.get(key or DEFAULT_KEY)

    def all_contexts(self) -> list[LotteryContext]:
        from ..core.profile import list_profiles

        return [self.get(p.key) for p in list_profiles()]
