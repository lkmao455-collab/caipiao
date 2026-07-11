"""后台工作线程."""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QThread, Signal

from ..core.engine import (
    GenerationEngine,
    estimate_fc3d_pass_count,
    filter_fc3d_by_history,
    filter_ssq_by_history,
)
from ..core.profile import LotteryProfile, SSQ
from ..data.fetcher import LotteryDataFetcher
from ..utils import app_data_dir

logger = logging.getLogger(__name__)

# 3D 经验策略过滤自适应候选倍数相关常量
# 安全系数：补偿加权采样下实际通过率低于均匀理论值的情况（实测最低约理论的 0.48 倍）
_FC3D_FILTER_SAFETY = 2.5
# 候选生成数量上限：3D 直选全空间为 1000，再大也无意义
_FC3D_FILTER_MAX_CANDIDATES = 1000


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
            need_filter = has_records and profile_key == "ssq"
            need_3d_filter = (
                has_records
                and profile_key == "3d"
                and bool(self.options.get("_fc3d_filter_enabled", False))
            )

            # 计算候选生成数量：
            # - 3D 经验策略过滤：按理论通过率自适应放大，避免过滤后候选不足
            # - 双色球过滤：固定 3 倍
            cp = mo = pass_count = None
            if need_3d_filter:
                cp = int(self.options.get("_fc3d_filter_compare_periods", 5))
                mo = int(self.options.get("_fc3d_filter_max_overlap", 1))
                pass_count = estimate_fc3d_pass_count(
                    self.options["_draw_records"], cp, mo
                )
                # 通过率下限 0.05，避免极端严格参数导致除以过小值
                pass_ratio = max(pass_count / 1000.0, 0.05)
                gen_count = math.ceil(self.count / pass_ratio * _FC3D_FILTER_SAFETY)
                gen_count = max(
                    self.count * 3,
                    min(_FC3D_FILTER_MAX_CANDIDATES, gen_count),
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
                        blue_compare_periods=self.options.get("_ssq_blue_periods", 0),
                    )
                tickets = tickets[:self.count]

            # 最后一层过滤（福彩3D 经验策略）
            if need_3d_filter and profile_key == "3d":
                if tickets:
                    filtered = filter_fc3d_by_history(
                        tickets,
                        self.options["_draw_records"],
                        compare_periods=cp,
                        max_overlap=mo,
                    )
                    if len(filtered) < self.count:
                        logger.warning(
                            "3D经验策略过滤：生成 %d 候选，过滤后仅剩 %d，"
                            "不足 %d 注（理论通过 %d/1000，建议放宽过滤参数）",
                            len(tickets), len(filtered), self.count,
                            pass_count if pass_count is not None else 0,
                        )
                    tickets = filtered[:self.count]

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
        self.setObjectName("TrainModelThread")
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

            predictor.train(progress_callback=self._emit_progress)
            if self.isInterruptionRequested():
                return
            self.result_ready.emit(True, None)
        except Exception as exc:  # noqa: BLE001
            self.result_ready.emit(None, exc)

    def _emit_progress(self, current: int, total: int) -> None:
        self.progress.emit(current, total)
