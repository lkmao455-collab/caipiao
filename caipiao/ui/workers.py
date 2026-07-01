"""后台工作线程."""

from __future__ import annotations

from typing import Any, Dict

from PySide6.QtCore import QThread, Signal

from ..core.engine import GenerationEngine
from ..data.fetcher import LotteryDataFetcher


class FetchAllDataThread(QThread):
    """抓取全部历史数据的后台线程."""

    result_ready = Signal(object, object)

    def __init__(self, parent=None, timeout: int = 60) -> None:
        super().__init__(parent)
        self.timeout = timeout

    def run(self) -> None:
        try:
            fetcher = LotteryDataFetcher(timeout=self.timeout)
            records = fetcher.fetch_all()
            self.result_ready.emit(records, None)
        except Exception as exc:  # noqa: BLE001
            self.result_ready.emit(None, exc)


class FetchLatestDataThread(QThread):
    """抓取最新一期数据的后台线程."""

    result_ready = Signal(object, object)

    def __init__(self, parent=None, timeout: int = 15) -> None:
        super().__init__(parent)
        self.timeout = timeout

    def run(self) -> None:
        try:
            fetcher = LotteryDataFetcher(timeout=self.timeout)
            latest = fetcher.fetch_latest()
            self.result_ready.emit(latest, None)
        except Exception as exc:  # noqa: BLE001
            self.result_ready.emit(None, exc)


class GenerateTicketsThread(QThread):
    """生成号码的后台线程（避免 XGBoost 训练冻结 UI）."""

    result_ready = Signal(object, object)

    def __init__(
        self,
        engine: GenerationEngine,
        strategy_id: str,
        count: int,
        options: Dict[str, Any],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.engine = engine
        self.strategy_id = strategy_id
        self.count = count
        self.options = options

    def run(self) -> None:
        try:
            tickets = self.engine.generate(
                self.strategy_id, count=self.count, options=self.options
            )
            self.result_ready.emit(tickets, None)
        except Exception as exc:  # noqa: BLE001
            self.result_ready.emit(None, exc)
