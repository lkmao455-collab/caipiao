"""后台工作线程."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QThread, Signal

from ..core.engine import (
    GenerationEngine,
    apply_fc3d_experience_filter,
    apply_qlc_experience_filter,
    fc3d_filtered_gen_count,
    filter_ssq_by_history,
    qlc_filtered_gen_count,
)
from ..core.profile import LotteryProfile, SSQ
from ..data.fetcher import LotteryDataFetcher
from ..utils import app_data_dir

logger = logging.getLogger(__name__)


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
        self.setObjectName("FetchAllDataThread")
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
        self.setObjectName("FetchLatestDataThread")
        self.profile = profile or SSQ
        self.timeout = timeout
        self._finished = False

    def run(self) -> None:
        try:
            fetcher = LotteryDataFetcher(profile=self.profile, timeout=self.timeout)
            latest = fetcher.fetch_latest()
            if self.isInterruptionRequested():
                return
            self.result_ready.emit(latest, None)
        except Exception as exc:  # noqa: BLE001
            self.result_ready.emit(None, exc)
        finally:
            self._finished = True

    def is_finished(self) -> bool:
        return self._finished

    def quit_safely(self) -> None:
        """请求中断并等待线程结束，返回是否成功结束。"""
        if not self.isRunning():
            return True
        self.requestInterruption()
        return self.wait(5000)

    def delete_when_finished(self) -> None:
        """在线程已结束时安全 deleteLater。"""
        if self.isRunning():
            self.quit_safely()
        self.deleteLater()


class GenerateTicketsThread(QThread):
    """生成号码的后台线程（避免 XGBoost 训练冻结 UI）."""

    result_ready = Signal(object, object)
    progress = Signal(str)

    def __init__(
        self,
        engine: GenerationEngine,
        strategy_id: str,
        count: int,
        options: Dict[str, Any],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("GenerateTicketsThread")
        self.engine = engine
        self.strategy_id = strategy_id
        self.count = count
        self.options = options

    def run(self) -> None:
        try:
            profile_key = self.options.get("_profile_key")
            has_records = bool(self.options.get("_draw_records"))
            # 双色球：仅智能冷热号策略启用过滤，历史均衡不过滤
            strategy_id = self.options.get("_strategy_id", "")
            need_filter = has_records and profile_key == "ssq" and strategy_id != "balanced"
            need_3d_filter = (
                has_records
                and profile_key == "3d"
                and bool(self.options.get("_fc3d_filter_enabled", False))
            )
            need_qlc_filter = (
                has_records
                and profile_key == "qlc"
                and bool(self.options.get("_qlc_filter_enabled", False))
            )

            # 计算候选生成数量：
            # - 3D/七乐彩 经验策略过滤：按理论通过率自适应放大，避免过滤后候选不足
            # - 双色球过滤：固定 3 倍
            cp = mo = pass_count = None
            min_sum = max_sum = None
            qlc_pass_ratio = None
            if need_3d_filter:
                cp = int(self.options.get("_fc3d_filter_compare_periods", 5))
                mo = int(self.options.get("_fc3d_filter_max_overlap", 1))
                min_sum = int(self.options.get("_fc3d_filter_min_sum", 0))
                max_sum = int(self.options.get("_fc3d_filter_max_sum", 27))
                gen_count, pass_count = fc3d_filtered_gen_count(
                    self.count, self.options["_draw_records"], cp, mo,
                    min_sum, max_sum,
                )
            elif need_qlc_filter:
                cp = int(self.options.get("_qlc_filter_compare_periods", 5))
                mo = int(self.options.get("_qlc_filter_max_overlap", 2))
                min_sum = int(self.options.get("_qlc_filter_min_sum", 0))
                max_sum = int(self.options.get("_qlc_filter_max_sum", 210))
                gen_count, qlc_pass_ratio = qlc_filtered_gen_count(
                    self.count, self.options["_draw_records"], cp, mo,
                    min_sum, max_sum,
                )
            elif need_filter:
                gen_count = self.count * 3
            else:
                gen_count = self.count

            # 传递进度回调给策略
            self.options["_progress_callback"] = lambda msg: self.progress.emit(msg)

            tickets = self.engine.generate(
                self.strategy_id, count=gen_count, options=self.options
            )

            # 最后一层过滤（仅双色球）
            if need_filter and profile_key == "ssq":
                if tickets:
                    tickets = filter_ssq_by_history(
                        tickets,
                        self.options["_draw_records"],
                        compare_periods=self.options.get("_ssq_compare_periods", 7),
                        max_red_overlap=self.options.get("_ssq_max_red_overlap", 3),
                        block_blue_match=self.options.get("_ssq_block_blue", False),
                        blue_compare_periods=self.options.get("_ssq_blue_periods", 1),
                    )
                tickets = tickets[:self.count]

            # 最后一层过滤（福彩3D 经验策略）
            if need_3d_filter and profile_key == "3d":
                tickets = apply_fc3d_experience_filter(
                    tickets,
                    self.options["_draw_records"],
                    self.count,
                    cp,
                    mo,
                    pass_count=pass_count,
                    min_sum=min_sum,
                    max_sum=max_sum,
                )

            # 最后一层过滤（七乐彩 经验策略）
            if need_qlc_filter and profile_key == "qlc":
                tickets = apply_qlc_experience_filter(
                    tickets,
                    self.options["_draw_records"],
                    self.count,
                    cp,
                    mo,
                    pass_ratio=qlc_pass_ratio,
                    min_sum=min_sum,
                    max_sum=max_sum,
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
    支持增量训练：当 ``incremental=True`` 时，仅使用新数据更新已有模型。
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
        incremental: bool = False,
        new_count: int = 0,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("TrainModelThread")
        self.records = records
        self.lookback = lookback
        self.model_path = model_path
        self.model_class = model_class
        self.prefix = prefix
        self.profile = profile
        self.backend = backend
        self.incremental = incremental
        self.new_count = new_count

    def run(self) -> None:
        try:
            if self.profile is not None and self.profile.key != "ssq":
                from ..ml.common.predictor import BaseMLPredictor as GenericMLPredictor

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
                    model_dir = app_data_dir() / "models"
                    model_dir.mkdir(parents=True, exist_ok=True)
                    self.model_path = model_dir / f"{self.prefix}_lookback{self.lookback}.pkl"

                kwargs = {"lookback": self.lookback, "model_path": self.model_path}
                if self.model_class is not None:
                    kwargs["model_class"] = self.model_class
                predictor = MLPredictor(self.records, **kwargs)

            if self.incremental and self.new_count > 0:
                success = predictor.train_incremental(
                    new_count=self.new_count,
                    progress_callback=self._emit_progress,
                )
                if not success:
                    # 增量训练失败，回退到全量训练
                    predictor.train(progress_callback=self._emit_progress)
            else:
                predictor.train(progress_callback=self._emit_progress)

            if self.isInterruptionRequested():
                return
            self.result_ready.emit(True, None)
        except Exception as exc:  # noqa: BLE001
            self.result_ready.emit(None, exc)

    def _emit_progress(self, current: int, total: int) -> None:
        self.progress.emit(current, total)
