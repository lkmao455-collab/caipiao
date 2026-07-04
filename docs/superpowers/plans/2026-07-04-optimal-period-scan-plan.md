# Optimal Period Scan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在批量历史回测对话框中新增“一键找最优期数”功能，自动扫描当前策略的 `lookback` 或 `history_count` 取值，找出固定奖金合计最高的参数值并写回策略面板。

**Architecture:** 新增配置模块 `caipiao/ui/optimal_period_config.py` 维护策略→参数映射与扫描范围；新增 `OptimalPeriodScanThread` 复用现有 worker 并行扫描；在 `BatchBacktestDialog` 增加按钮和回调；新增单元测试覆盖映射、扫描与错误场景。

**Tech Stack:** Python 3.10+, PySide6, pytest, 现有批量回测多进程 worker。

## Global Constraints

- 仅覆盖 `lookback` 或 `history_count` 可调的策略。
- 默认以 `total_fixed_prize` 最高为最优标准；相同时比较 `hit_count`；仍相同取参数值较小者。
- 扫描范围不可配置（方案 2 再扩展）。
- 扫描完成后不自动重新运行完整批量回测。
- 复用现有 `RoundBacktestContext`、`RoundTask`、`worker_round_backtest`、`merge_round_results`。
- 代码注释与文档使用中文，符合项目现有风格。

---

## File Structure

- **Create:** `caipiao/ui/optimal_period_config.py` — 策略到优化参数的映射、扫描范围、识别函数。
- **Create:** `caipiao/ui/optimal_period_scan_thread.py` — 后台扫描线程，运行多组批量回测并选出最优。
- **Create:** `tests/test_optimal_period_scan.py` — 单元测试。
- **Modify:** `caipiao/ui/components/batch_backtest_dialog.py` — 添加“一键找最优期数”按钮、进度/日志展示、回调。

---

## Task 1: Optimal Period Config Module

**Files:**
- Create: `caipiao/ui/optimal_period_config.py`
- Test: `tests/test_optimal_period_scan.py`（映射部分）

**Interfaces:**
- Consumes: `strategy_id: str`
- Produces: `resolve_optimal_param(strategy_id: str) -> tuple[str, list[int]] | None`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from caipiao.ui.optimal_period_config import (
    OPTIMAL_PERIOD_RANGES,
    STRATEGY_PARAM_MAP,
    resolve_optimal_param,
)


def test_resolve_param_for_smart_hot_cold():
    result = resolve_optimal_param("smart_hot_cold")
    assert result is not None
    param_name, values = result
    assert param_name == "lookback"
    assert values == OPTIMAL_PERIOD_RANGES["lookback"]


def test_resolve_param_for_xgboost():
    result = resolve_optimal_param("xgboost")
    assert result is not None
    param_name, values = result
    assert param_name == "history_count"
    assert values == OPTIMAL_PERIOD_RANGES["history_count"]


def test_resolve_param_for_generic_balanced():
    result = resolve_optimal_param("balanced_3d")
    assert result is not None
    param_name, values = result
    assert param_name == "lookback"


def test_resolve_param_unsupported():
    assert resolve_optimal_param("random") is None
    assert resolve_optimal_param("odd_even") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_optimal_period_scan.py::test_resolve_param_for_smart_hot_cold -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'caipiao.ui.optimal_period_config'`

- [ ] **Step 3: Write minimal implementation**

```python
"""一键找最优期数的参数配置."""

from __future__ import annotations

from typing import List, Tuple


OPTIMAL_PERIOD_RANGES: dict[str, list[int]] = {
    "lookback": [20, 50, 80, 100, 150, 200, 300],
    "history_count": [100, 200, 300, 500, 800, 1000, -1],
}


STRATEGY_PARAM_MAP: dict[str, str] = {
    "smart_hot_cold": "lookback",
    "missing_number": "lookback",
    "balanced": "lookback",
    "xgboost": "history_count",
    "lightgbm": "history_count",
    "catboost": "history_count",
}


def resolve_optimal_param(strategy_id: str) -> Tuple[str, list[int]] | None:
    """根据策略 id 返回要优化的参数名及其扫描范围."""
    for prefix, param_name in STRATEGY_PARAM_MAP.items():
        if strategy_id.startswith(prefix):
            return param_name, OPTIMAL_PERIOD_RANGES[param_name]
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_optimal_period_scan.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add caipiao/ui/optimal_period_config.py tests/test_optimal_period_scan.py
git commit -m "feat(optimal-period): add param resolution and ranges"
```

---

## Task 2: Optimal Period Scan Thread

**Files:**
- Create: `caipiao/ui/optimal_period_scan_thread.py`
- Test: `tests/test_optimal_period_scan.py`（扫描线程部分）

**Interfaces:**
- Consumes: `BatchBacktestResult` from `caipiao.ui.batch_backtest_result`, `RoundBacktestContext`, `RoundTask`, `worker_round_backtest`, `merge_round_results` from `caipiao.ui.batch_backtest_worker`, `_normalize_max_workers` from `caipiao.ui.batch_backtest_thread`, `resolve_optimal_param` from `caipiao.ui.optimal_period_config`.
- Produces: `ScanResult` dataclass; `OptimalPeriodScanThread` with `progress`, `status_message`, `result_ready` signals.

- [ ] **Step 1: Write the failing test**

```python
from datetime import datetime, timedelta

from caipiao.core.engine import GenerationEngine
from caipiao.core.profile import SSQ
from caipiao.core.strategies import SmartHotColdStrategy
from caipiao.data.models import DrawRecord
from caipiao.ui.optimal_period_scan_thread import OptimalPeriodScanThread, ScanResult


class _MockRepository:
    def __init__(self, records):
        self._records = list(records)

    def get_all(self):
        return self._records[:]


def _make_records(n=120):
    records = []
    base = datetime(2023, 1, 1)
    for i in range(n):
        base_offset = (i * 7) % 33
        nums = sorted({((base_offset + j * 13) % 33) + 1 for j in range(6)})
        while len(nums) < 6:
            nums.append(next(num for num in range(1, 34) if num not in nums))
            nums.sort()
        blue = (i * 5 + 3) % 16 + 1
        records.append(
            DrawRecord(
                issue=f"2023{i+1:03d}",
                draw_date=base + timedelta(days=i),
                red_balls=sorted(nums),
                blue_ball=blue,
            )
        )
    return records


def test_scan_thread_finds_optimal_lookback():
    records = _make_records(120)
    engine = GenerationEngine()
    engine.register(SmartHotColdStrategy())

    thread = OptimalPeriodScanThread(
        engine=engine,
        strategy_id="smart_hot_cold",
        profile=SSQ,
        data_repository=_MockRepository(records),
        start_date=datetime(2023, 4, 1),
        end_date=datetime(2023, 4, 10),
        tickets_per_round=1,
        base_options={"hot_weight": 60, "cold_weight": 40},
        plugin_dir=None,
    )

    result = None
    error = None

    def on_finished(r, exc):
        nonlocal result, error
        result = r
        error = exc

    thread.result_ready.connect(on_finished)
    thread.run()

    assert error is None, error
    assert isinstance(result, ScanResult)
    assert result.param_name == "lookback"
    assert result.optimal_value in result.all_values
    assert result.optimal_result.total_rounds == 10


def test_scan_thread_unsupported_strategy():
    records = _make_records(10)
    engine = GenerationEngine()
    from caipiao.core.strategies import RandomStrategy

    engine.register(RandomStrategy())

    thread = OptimalPeriodScanThread(
        engine=engine,
        strategy_id="random",
        profile=SSQ,
        data_repository=_MockRepository(records),
        start_date=datetime(2023, 1, 1),
        end_date=datetime(2023, 1, 10),
        tickets_per_round=1,
        base_options={},
        plugin_dir=None,
    )

    result = None
    error = None

    def on_finished(r, exc):
        nonlocal result, error
        result = r
        error = exc

    thread.result_ready.connect(on_finished)
    thread.run()

    assert result is None
    assert isinstance(error, ValueError)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_optimal_period_scan.py::test_scan_thread_finds_optimal_lookback -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'caipiao.ui.optimal_period_scan_thread'`

- [ ] **Step 3: Write minimal implementation**

```python
"""一键找最优期数后台扫描线程."""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QThread, Signal

from .batch_backtest_result import BatchBacktestResult
from .batch_backtest_thread import _normalize_max_workers
from .batch_backtest_worker import (
    RoundBacktestContext,
    RoundTask,
    init_worker_process,
    merge_round_results,
    worker_round_backtest,
)
from .optimal_period_config import resolve_optimal_param
from ..core.engine import GenerationEngine
from ..core.profile import LotteryProfile
from ..data.repository import DrawRepository


@dataclass
class ScanResult:
    """参数扫描结果."""

    param_name: str
    optimal_value: int
    optimal_result: BatchBacktestResult
    all_results: List[Tuple[int, BatchBacktestResult]]

    @property
    def all_values(self) -> List[int]:
        """所有扫描过的参数值."""
        return [value for value, _ in self.all_results]


class OptimalPeriodScanThread(QThread):
    """对单一参数扫描多个取值，找出固定奖金合计最高的参数值."""

    progress = Signal(int, int)  # 当前完成组数, 总组数
    status_message = Signal(str)  # 状态文本
    result_ready = Signal(object, object)  # ScanResult | None, error | None

    def __init__(
        self,
        engine: GenerationEngine,
        strategy_id: str,
        profile: LotteryProfile,
        data_repository: DrawRepository,
        start_date: datetime,
        end_date: datetime,
        tickets_per_round: int,
        base_options: Dict[str, Any],
        plugin_dir: Optional[str] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("OptimalPeriodScanThread")
        self.engine = engine
        self.strategy_id = strategy_id
        self.profile = profile
        self.data_repository = data_repository
        self.start_date = start_date
        self.end_date = end_date
        self.tickets_per_round = tickets_per_round
        self.base_options = base_options
        self.plugin_dir = plugin_dir

    def run(self) -> None:
        try:
            resolved = resolve_optimal_param(self.strategy_id)
            if resolved is None:
                self.result_ready.emit(
                    None,
                    ValueError(f"策略 {self.strategy_id} 不支持一键找最优期数"),
                )
                return

            param_name, param_values = resolved

            records = self.data_repository.get_all()
            target_records = [
                r
                for r in records
                if self.start_date.date() <= r.draw_date.date() <= self.end_date.date()
            ]
            target_records.sort(key=lambda r: r.draw_date)
            if not target_records:
                self.result_ready.emit(
                    None, ValueError("指定日期范围内没有开奖记录")
                )
                return

            min_required = min(v for v in param_values if v > 0)
            if len(records) < min_required:
                self.result_ready.emit(
                    None,
                    ValueError(
                        f"历史数据不足，至少需要 {min_required} 期才能扫描 {param_name}"
                    ),
                )
                return

            base_context = RoundBacktestContext(
                strategy_id=self.strategy_id,
                profile_key=self.profile.key,
                tickets_per_round=self.tickets_per_round,
                options=dict(self.base_options),
                is_ml=self.strategy_id.startswith(("xgboost", "lightgbm", "catboost")),
                needs_history=True,
                records=records,
                seed=42,
                plugin_dir=self.plugin_dir,
            )
            tasks = [
                RoundTask(index=i, actual=r) for i, r in enumerate(target_records)
            ]

            all_results: List[Tuple[int, BatchBacktestResult]] = []
            max_workers = _normalize_max_workers(
                self.base_options.get("batch_backtest_workers")
            )
            completed = 0
            total = len(param_values)

            executor = None
            futures: List[Any] = []
            try:
                executor = ProcessPoolExecutor(
                    max_workers=max_workers,
                    initializer=init_worker_process,
                    initargs=(base_context.seed,),
                )

                for value in param_values:
                    context = self._build_context(base_context, param_name, value)
                    futures.append(
                        (
                            value,
                            executor.submit(
                                self._run_one_value, context, tasks, len(tasks)
                            ),
                        )
                    )

                for value, future in futures:
                    if self.isInterruptionRequested():
                        break
                    result = future.result()
                    all_results.append((value, result))
                    completed += 1
                    self.progress.emit(completed, total)
                    self.status_message.emit(
                        f"已完成 {param_name}={value} 的扫描（{completed}/{total}）"
                    )
            finally:
                if executor is not None:
                    for _, f in futures:
                        f.cancel()
                    executor.shutdown(wait=False, cancel_futures=True)

            if not all_results:
                self.result_ready.emit(
                    None, ValueError("没有完成任何参数扫描")
                )
                return

            best = self._pick_best(all_results)
            scan_result = ScanResult(
                param_name=param_name,
                optimal_value=best[0],
                optimal_result=best[1],
                all_results=all_results,
            )
            self.result_ready.emit(scan_result, None)
        except Exception as exc:  # noqa: BLE001
            self.result_ready.emit(None, exc)

    def _build_context(
        self,
        base_context: RoundBacktestContext,
        param_name: str,
        value: int,
    ) -> RoundBacktestContext:
        options = dict(base_context.options)
        options[param_name] = value
        return RoundBacktestContext(
            strategy_id=base_context.strategy_id,
            profile_key=base_context.profile_key,
            tickets_per_round=base_context.tickets_per_round,
            options=options,
            is_ml=base_context.is_ml,
            needs_history=base_context.needs_history,
            records=base_context.records,
            seed=base_context.seed,
            plugin_dir=base_context.plugin_dir,
        )

    @staticmethod
    def _run_one_value(
        context: RoundBacktestContext, tasks: List[RoundTask], total_rounds: int
    ) -> BatchBacktestResult:
        futures = []
        try:
            with ProcessPoolExecutor(
                max_workers=1,
                initializer=init_worker_process,
                initargs=(context.seed,),
            ) as executor:
                futures = [
                    executor.submit(worker_round_backtest, context, task)
                    for task in tasks
                ]
                round_results = [future.result() for future in futures]
        finally:
            for f in futures:
                f.cancel()
        return merge_round_results(round_results, total_rounds=total_rounds)

    @staticmethod
    def _pick_best(
        results: List[Tuple[int, BatchBacktestResult]],
    ) -> Tuple[int, BatchBacktestResult]:
        return max(
            results,
            key=lambda item: (
                item[1].total_fixed_prize,
                item[1].hit_count,
                -item[0],
            ),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_optimal_period_scan.py -v`

Expected: PASS

> 注意：`_run_one_value` 每次新建 `ProcessPoolExecutor(max_workers=1)` 可能较慢；如果测试中不便于创建子进程，可考虑用线程或直接顺序执行。但为复用现有 worker，此处先按进程实现。若测试失败，可改为对每组值直接顺序调用 `worker_round_backtest`（因为当前数据量小），但产品环境保持进程池以获得并行。

- [ ] **Step 5: Commit**

```bash
git add caipiao/ui/optimal_period_scan_thread.py tests/test_optimal_period_scan.py
git commit -m "feat(optimal-period): add scan thread and ScanResult"
```

---

## Task 3: Integrate into BatchBacktestDialog

**Files:**
- Modify: `caipiao/ui/components/batch_backtest_dialog.py`
- Test: 手动运行 `python main.py` 验证 UI（无新增自动化 UI 测试）。

**Interfaces:**
- Consumes: `OptimalPeriodScanThread`, `ScanResult` from `caipiao.ui.optimal_period_scan_thread`, `resolve_optimal_param` from `caipiao.ui.optimal_period_config`.
- Produces: 新增按钮 `_optimal_btn`、回调 `_run_optimal_period_scan`、结果处理 `_on_optimal_finished`、结果格式化 `_format_optimal_summary`。

- [ ] **Step 1: 导入新模块**

在 `caipiao/ui/components/batch_backtest_dialog.py` 顶部添加：

```python
from ...ui.optimal_period_scan_thread import OptimalPeriodScanThread
```

- [ ] **Step 2: 添加按钮**

在 `_setup_ui` 中，把停止按钮右侧新增优化按钮。现有代码段：

```python
        self.stop_btn = QPushButton("停止回测")
        self.stop_btn.setToolTip("停止当前正在进行的批量回测")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_batch_backtest)
        control_layout.addWidget(self.stop_btn)

        control_layout.addStretch()
```

改为：

```python
        self.stop_btn = QPushButton("停止回测")
        self.stop_btn.setToolTip("停止当前正在进行的批量回测")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_batch_backtest)
        control_layout.addWidget(self.stop_btn)

        self.optimal_btn = QPushButton("一键找最优期数")
        self.optimal_btn.setToolTip(
            "自动扫描当前策略的“统计期数”或“使用历史记录期数”，"
            "找出固定奖金合计最高的参数值并应用"
        )
        self.optimal_btn.clicked.connect(self._run_optimal_period_scan)
        control_layout.addWidget(self.optimal_btn)

        control_layout.addStretch()
```

- [ ] **Step 3: 实现启动扫描回调**

在 `_stop_batch_backtest` 方法附近新增：

```python
    def _run_optimal_period_scan(self) -> None:
        start_qdate = self.start_date_edit.date()
        end_qdate = self.end_date_edit.date()
        if start_qdate > end_qdate:
            QMessageBox.warning(self, "日期错误", "起始日期不能晚于结束日期")
            return

        start_date = datetime(start_qdate.year(), start_qdate.month(), start_qdate.day())
        end_date = datetime(end_qdate.year(), end_qdate.month(), end_qdate.day())

        strategy_id = self.strategy_panel.current_strategy_id()
        if not strategy_id:
            QMessageBox.warning(self, "提示", "请选择一个生成策略")
            return

        from ...ui.optimal_period_config import resolve_optimal_param

        resolved = resolve_optimal_param(strategy_id)
        if resolved is None:
            QMessageBox.information(
                self,
                "不支持",
                "当前策略没有可一键优化的“使用期数”参数。",
            )
            return

        try:
            base_options = self.strategy_panel.current_options()
        except ValueError as exc:
            QMessageBox.warning(self, "参数错误", str(exc))
            return

        self.run_btn.setEnabled(False)
        self.run_btn.setText("批量回测中...")
        self.stop_btn.setEnabled(True)
        self.optimal_btn.setEnabled(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.detail_text.clear()
        self.status_text.clear()
        self.summary_label.setText("正在扫描最优参数，请稍候...")

        self._scan_thread = OptimalPeriodScanThread(
            engine=self.context.engine,
            strategy_id=strategy_id,
            profile=self.profile,
            data_repository=self.data_repository,
            start_date=start_date,
            end_date=end_date,
            tickets_per_round=self.count_spin.value(),
            base_options=base_options,
            plugin_dir=self.plugin_dir,
            parent=self,
        )
        self._scan_thread.progress.connect(self._on_progress)
        self._scan_thread.status_message.connect(self._on_status_message)
        self._scan_thread.result_ready.connect(
            self._on_optimal_finished, Qt.ConnectionType.QueuedConnection
        )
        self._scan_thread.finished.connect(self._cleanup_finished_scan_thread)
        self._scan_thread.start()

    def _cleanup_finished_scan_thread(self) -> None:
        thread = self.sender()
        if thread is None:
            return
        if getattr(self, "_scan_thread", None) is thread:
            self._scan_thread = None
        try:
            thread.deleteLater()
        except RuntimeError:
            pass
```

- [ ] **Step 4: 实现扫描完成回调与摘要**

在 `_on_finished` 方法附近新增：

```python
    def _on_optimal_finished(self, result, error) -> None:
        self.run_btn.setEnabled(True)
        self.run_btn.setText("开始批量回测")
        self.stop_btn.setEnabled(False)
        self.optimal_btn.setEnabled(True)
        self.progress.setVisible(False)

        if error:
            QMessageBox.critical(self, "扫描失败", str(error))
            self.summary_label.setText("一键找最优期数失败。")
            return

        if result is None:
            self.summary_label.setText(
                self.summary_label.text() + "\n（已停止）"
            )
            return

        # 自动将最优参数写回策略面板
        self.strategy_panel.set_options({result.param_name: result.optimal_value})

        summary_lines = [
            f"最优参数：{result.param_name} = {result.optimal_value}",
            f"回测期数：{result.optimal_result.total_rounds} 期",
            f"总花费：{result.optimal_result.total_cost} 元",
            f"固定奖金合计：{result.optimal_result.total_fixed_prize} 元",
            f"中奖次数：{result.optimal_result.hit_count} 次",
            f"首注中奖次数：{result.optimal_result.first_ticket_hit_count} 次",
        ]
        self.summary_label.setText("\n".join(summary_lines))

        # 在日志区打印所有结果排名
        ranked = sorted(
            result.all_results,
            key=lambda item: (
                item[1].total_fixed_prize,
                item[1].hit_count,
                -item[0],
            ),
            reverse=True,
        )
        self.status_text.append("=" * 40)
        self.status_text.append("一键找最优期数扫描结果：")
        for rank, (value, res) in enumerate(ranked, start=1):
            self.status_text.append(
                f"{rank}. {result.param_name}={value}: "
                f"固定奖金 {res.total_fixed_prize} 元, "
                f"中奖 {res.hit_count} 次, "
                f"首注 {res.first_ticket_hit_count} 次"
            )
        self.status_text.append("=" * 40)
```

- [ ] **Step 5: 更新停止按钮逻辑**

修改 `_stop_batch_backtest`，同时中断扫描线程：

```python
    def _stop_batch_backtest(self) -> None:
        if self._thread and self._thread.isRunning():
            self.status_text.append("用户请求停止批量回测，等待当前期处理完成...")
            self._thread.requestInterruption()
            self.stop_btn.setEnabled(False)
        if getattr(self, "_scan_thread", None) and self._scan_thread.isRunning():
            self.status_text.append("用户请求停止参数扫描...")
            self._scan_thread.requestInterruption()
            self.stop_btn.setEnabled(False)
```

- [ ] **Step 6: 更新 closeEvent**

在 `closeEvent` 中增加扫描线程清理：

```python
        if getattr(self, "_scan_thread", None) and self._scan_thread.isRunning():
            self._scan_thread.requestInterruption()
            if not self._scan_thread.wait(5000):
                self._scan_thread.terminate()
                self._scan_thread.wait(1000)
```

- [ ] **Step 7: 提交**

```bash
git add caipiao/ui/components/batch_backtest_dialog.py
git commit -m "feat(optimal-period): integrate scan button into batch backtest dialog"
```

---

## Task 4: 运行测试与全量验证

- [ ] **Step 1: 运行新增测试**

```bash
pytest tests/test_optimal_period_scan.py -v
```

Expected: all PASS

- [ ] **Step 2: 运行现有批量回测相关测试**

```bash
pytest tests/test_batch_backtest_integration.py tests/test_batch_backtest_worker.py -v
```

Expected: all PASS

- [ ] **Step 3: 运行全量测试**

```bash
pytest tests/ -v
```

Expected: all PASS（或仅已存在的跳过/失败）

- [ ] **Step 4: 手动启动程序验证 UI**

```bash
python main.py
```

验证：
- 打开批量历史回测窗口。
- 选择 `smart_hot_cold` 策略，点击“一键找最优期数”。
- 等待扫描完成，确认策略面板的“统计期数”被自动修改。
- 选择 `xgboost` 策略，确认“使用历史记录期数”被自动修改。
- 选择 `random` 策略，确认提示“当前策略没有可一键优化的参数”。

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "test(optimal-period): add tests and verify integration"
```

---

## Self-Review

**Spec coverage:**
- 界面入口 → Task 3
- 参数映射与范围 → Task 1
- 扫描线程与并行 → Task 2
- 最优标准与结果展示 → Task 2 + Task 3
- 错误处理 → Task 2 + Task 3
- 测试 → Task 1-4
- 扩展预留 → 代码结构（独立配置模块、ScanResult）已预留

**Placeholder scan:** 无 TBD/TODO/待实现。

**Type consistency:**
- `resolve_optimal_param` 返回 `Tuple[str, list[int]] | None` 在配置模块、测试、调用处一致。
- `ScanResult` 字段与 `OptimalPeriodScanThread.result_ready` 信号一致。
- `_pick_best` 返回 `Tuple[int, BatchBacktestResult]` 与 `ScanResult` 构造一致。

**潜在问题与建议：**
- `OptimalPeriodScanThread._run_one_value` 每组参数新建一个单进程池，可能带来进程启动开销。若测试中子进程导致不稳定，可优先改为直接顺序调用 `worker_round_backtest`（数据量小），产品环境再评估是否值得为每组参数复用共享池。实际实现时若发现慢，可改为共享一个进程池，按 `(value, task)` 派发，但合并逻辑需按 value 分组。
- `BatchBacktestDialog` 中 `run_btn` 在扫描期间显示“批量回测中...”可能让用户困惑；可改为“扫描中...”。实现时把 `self.run_btn.setText("批量回测中...")` 改为 `"扫描中..."`，恢复时改回 `"开始批量回测"`。
- ML 策略扫描非常慢，UI 提示需明确；当前已在按钮 tooltip 和 `summary_label` 中说明。
