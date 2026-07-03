"""后台工作线程."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QThread, Signal

from ..core.engine import GenerationEngine
from ..core.profile import LotteryProfile, SSQ
from ..data.fetcher import LotteryDataFetcher


class FetchAllDataThread(QThread):
    """抓取全部历史数据的后台线程."""

    result_ready = Signal(object, object)

    def __init__(
        self,
        parent=None,
        profile: LotteryProfile | None = None,
        timeout: int = 60,
    ) -> None:
        super().__init__(parent)
        self.profile = profile or SSQ
        self.timeout = timeout

    def run(self) -> None:
        try:
            fetcher = LotteryDataFetcher(profile=self.profile, timeout=self.timeout)
            records = fetcher.fetch_all()
            if self.isInterruptionRequested():
                return
            self.result_ready.emit(records, None)
        except Exception as exc:  # noqa: BLE001
            self.result_ready.emit(None, exc)


class FetchLatestDataThread(QThread):
    """抓取最新一期数据的后台线程."""

    result_ready = Signal(object, object)

    def __init__(
        self,
        parent=None,
        profile: LotteryProfile | None = None,
        timeout: int = 15,
    ) -> None:
        super().__init__(parent)
        self.profile = profile or SSQ
        self.timeout = timeout

    def run(self) -> None:
        try:
            fetcher = LotteryDataFetcher(profile=self.profile, timeout=self.timeout)
            latest = fetcher.fetch_latest()
            if self.isInterruptionRequested():
                return
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
            if self.isInterruptionRequested():
                return
            self.result_ready.emit(tickets, None)
        except Exception as exc:  # noqa: BLE001
            self.result_ready.emit(None, exc)


class TrainModelThread(QThread):
    """后台训练机器学习模型的线程.

    支持双色球（使用 ``MLPredictor``）和新增的通用彩种（使用 ``GenericMLPredictor``）。
    通过 ``profile`` 与 ``backend`` 参数指定通用彩种；不传则保持原有双色球行为。
    """

    result_ready = Signal(object, object)
    progress = Signal(int, int)

    def __init__(
        self,
        records: List[Any],
        lookback: int = 50,
        model_path: Optional[Path] = None,
        model_class: Optional[type] = None,
        prefix: str = "xgboost",
        profile: Optional[LotteryProfile] = None,
        backend: str = "xgboost",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.records = records
        self.lookback = lookback
        self.model_path = model_path
        self.model_class = model_class
        self.prefix = prefix
        self.profile = profile
        self.backend = backend

    def run(self) -> None:
        try:
            if self.profile is not None and self.profile.key != "ssq":
                from ..ml.generic_predictor import GenericMLPredictor

                predictor = GenericMLPredictor(
                    self.records,
                    profile=self.profile,
                    lookback=self.lookback,
                    model_path=self.model_path,
                    backend=self.backend,
                )
            else:
                from ..ml.predictor import MLPredictor

                if self.model_path is None:
                    model_dir = Path.home() / ".caipiao" / "models"
                    model_dir.mkdir(parents=True, exist_ok=True)
                    self.model_path = model_dir / f"{self.prefix}_lookback{self.lookback}.pkl"

                kwargs = {"lookback": self.lookback, "model_path": self.model_path}
                if self.model_class is not None:
                    kwargs["model_class"] = self.model_class
                predictor = MLPredictor(self.records, **kwargs)

            predictor.train(progress_callback=self._emit_progress)
            if self.isInterruptionRequested():
                return
            self.result_ready.emit(True, None)
        except Exception as exc:  # noqa: BLE001
            self.result_ready.emit(None, exc)

    def _emit_progress(self, current: int, total: int) -> None:
        self.progress.emit(current, total)
