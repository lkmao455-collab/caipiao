# Optimal Strategy and Parameter Scan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在批量历史回测对话框新增“一键找最优策略和参数”功能，扫描所有依赖历史数据的策略及其可调参数，找出固定奖金合计最高的策略+参数组合并自动应用。

**Architecture:** 将 `OptimalPeriodScanThread` 中“对单一策略扫描多参数”的核心逻辑提取为独立函数，供新的 `OptimalStrategyScanThread` 复用；新线程遍历所有 `needs_history=True` 的策略，对每个策略执行参数扫描，汇总各策略最优结果后跨策略排序，最终由对话框回写策略面板。

**Tech Stack:** Python 3.10+, PySide6, pytest, 现有批量回测多进程 worker。

## Global Constraints

- 仅覆盖 `needs_history=True` 的策略。
- 默认以 `total_fixed_prize` 最高为最优标准；相同时比较 `hit_count`；仍相同取策略 id 字典序较小者。
- 扫描范围不可配置（后续扩展）。
- 扫描完成后不自动重新运行完整批量回测。
- 复用现有 `RoundBacktestContext`、`RoundTask`、`worker_round_backtest`、`merge_round_results`。
- 保留已有“一键找最优期数”按钮及行为。
- 代码注释与文档使用中文，符合项目现有风格。

---

## File Structure

- **Create:** `caipiao/ui/optimal_strategy_scan_thread.py` — 策略+参数扫描线程。
- **Create:** `tests/test_optimal_strategy_scan.py` — 策略扫描单元测试。
- **Modify:** `caipiao/ui/optimal_period_scan_thread.py` — 提取 `_scan_param_values` 独立函数，供策略扫描线程复用。
- **Modify:** `caipiao/ui/components/batch_backtest_dialog.py` — 新增按钮、回调、UI 状态同步。

---

## Task 1: Extract Single-Strategy Parameter Scan Function

**Files:**
- Modify: `caipiao/ui/optimal_period_scan_thread.py`
- Test: `tests/test_optimal_period_scan.py`（验证重构后行为不变）

**Interfaces:**
- Consumes: `RoundBacktestContext`, `RoundTask`, `worker_round_backtest`, `merge_round_results`, `BatchBacktestResult`, `_normalize_max_workers`, `init_worker_process`.
- Produces: `scan_param_values(context, tasks, param_name, param_values, progress_callback=None, interruption_callback=None) -> List[Tuple[int, BatchBacktestResult]]`.

- [ ] **Step 1: Write the failing test for extracted function**

```python
def test_scan_param_values_returns_results(monkeypatch):
    from caipiao.ui.optimal_period_scan_thread import scan_param_values
    from caipiao.ui.batch_backtest_worker import RoundBacktestContext, RoundTask
    from caipiao.ui.batch_backtest_result import BatchBacktestResult
    from caipiao.data.models import DrawRecord
    from datetime import datetime

    record = DrawRecord(
        issue="2024001",
        draw_date=datetime(2024, 1, 1),
        red_balls=[1, 2, 3, 4, 5, 6],
        blue_ball=7,
    )
    context = RoundBacktestContext(
        strategy_id="random",
        profile_key="ssq",
        tickets_per_round=1,
        options={},
        is_ml=False,
        needs_history=False,
        records=[record],
        seed=42,
    )
    tasks = [RoundTask(index=0, actual=record)]

    class _MockExecutor:
        def __init__(self, *args, **kwargs):
            pass
        def submit(self, fn, *args, **kwargs):
            class F:
                def result(self):
                    return fn(*args, **kwargs)
            return F()
        def shutdown(self, *args, **kwargs):
            pass

    monkeypatch.setattr(
        "caipiao.ui.optimal_period_scan_thread.ProcessPoolExecutor", _MockExecutor
    )

    results = scan_param_values(context, tasks, "lookback", [10, 20])
    assert len(results) == 2
    assert all(isinstance(r[1], BatchBacktestResult) for r in results)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_optimal_period_scan.py::test_scan_param_values_returns_results -v`

Expected: FAIL with `ImportError: cannot import name 'scan_param_values'`

- [ ] **Step 3: Refactor `OptimalPeriodScanThread` to use extracted function**

在 `caipiao/ui/optimal_period_scan_thread.py` 中添加独立函数：

```python
def scan_param_values(
    base_context: RoundBacktestContext,
    tasks: List[RoundTask],
    param_name: str,
    param_values: List[int],
    progress_callback: Optional[Callable[[int, int], None]] = None,
    status_callback: Optional[Callable[[str], None]] = None,
    interruption_callback: Optional[Callable[[], bool]] = None,
) -> List[Tuple[int, BatchBacktestResult]]:
    """对单一策略扫描多个参数取值，返回每个取值对应的结果."""
    all_results: List[Tuple[int, BatchBacktestResult]] = []
    max_workers = _normalize_max_workers(
        base_context.options.get("batch_backtest_workers")
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
            context = _build_context(base_context, param_name, value)
            futures.append(
                (
                    value,
                    executor.submit(
                        _run_one_value, context, tasks, len(tasks)
                    ),
                )
            )

        for value, future in futures:
            if interruption_callback is not None and interruption_callback():
                break
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001
                result = BatchBacktestResult(
                    total_rounds=len(tasks),
                    errors=[repr(exc)],
                )
            all_results.append((value, result))
            completed += 1
            if progress_callback is not None:
                progress_callback(completed, total)
            if status_callback is not None:
                status_callback(f"已完成 {param_name}={value} 的扫描（{completed}/{total}）")
    finally:
        if executor is not None:
            for _, f in futures:
                f.cancel()
            executor.shutdown(wait=False, cancel_futures=True)

    return all_results
```

并将 `OptimalPeriodScanThread.run` 中对 `param_values` 的扫描循环替换为调用 `scan_param_values`。

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_optimal_period_scan.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add caipiao/ui/optimal_period_scan_thread.py tests/test_optimal_period_scan.py
git commit -m "refactor(optimal-period): extract scan_param_values for reuse"
```

---

## Task 2: Optimal Strategy Scan Thread

**Files:**
- Create: `caipiao/ui/optimal_strategy_scan_thread.py`
- Test: `tests/test_optimal_strategy_scan.py`

**Interfaces:**
- Consumes: `scan_param_values` from `caipiao.ui.optimal_period_scan_thread`, `resolve_optimal_param` from `caipiao.ui.optimal_period_config`, `needs_history` from `caipiao.core.strategies.generic`, `BatchBacktestResult`, `RoundBacktestContext`, `RoundTask`, `GenerationEngine`, `LotteryProfile`, `DrawRepository`.
- Produces: `StrategyScanResult` dataclass; `OptimalStrategyScanThread` with `progress`, `status_message`, `result_ready` signals.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from datetime import datetime, timedelta

from caipiao.core.engine import GenerationEngine
from caipiao.core.profile import SSQ
from caipiao.core.strategies import HotColdStrategy, SmartHotColdStrategy
from caipiao.data.models import DrawRecord
from caipiao.ui.optimal_strategy_scan_thread import (
    OptimalStrategyScanThread,
    StrategyScanResult,
)


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


def _run_thread(thread):
    result = None
    error = None

    def on_finished(r, exc):
        nonlocal result, error
        result = r
        error = exc

    thread.result_ready.connect(on_finished)
    thread.run()
    return result, error


def test_strategy_scan_finds_best():
    records = _make_records(120)
    engine = GenerationEngine()
    engine.register(HotColdStrategy())
    engine.register(SmartHotColdStrategy())

    thread = OptimalStrategyScanThread(
        engine=engine,
        profile=SSQ,
        data_repository=_MockRepository(records),
        start_date=datetime(2023, 4, 1),
        end_date=datetime(2023, 4, 10),
        tickets_per_round=1,
        base_options={"hot_weight": 60, "cold_weight": 40},
        plugin_dir=None,
    )

    result, error = _run_thread(thread)

    assert error is None, error
    assert isinstance(result, StrategyScanResult)
    assert result.optimal_strategy_id in ("hot_cold", "smart_hot_cold")
    assert result.optimal_result.total_rounds == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_optimal_strategy_scan.py::test_strategy_scan_finds_best -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'caipiao.ui.optimal_strategy_scan_thread'`

- [ ] **Step 3: Write minimal implementation**

```python
"""一键找最优策略和参数后台扫描线程."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QThread, Signal

from .batch_backtest_result import BatchBacktestResult
from .batch_backtest_worker import RoundBacktestContext, RoundTask
from .optimal_period_config import resolve_optimal_param
from .optimal_period_scan_thread import scan_param_values
from ..core.engine import GenerationEngine
from ..core.profile import LotteryProfile
from ..core.strategies.generic import needs_history
from ..data.repository import DrawRepository


@dataclass
class StrategyScanResult:
    """策略+参数扫描结果."""

    optimal_strategy_id: str
    optimal_strategy_name: str
    param_name: Optional[str]
    optimal_value: Optional[int]
    optimal_result: BatchBacktestResult
    all_results: List[Tuple[str, Optional[int], BatchBacktestResult]]
    interrupted: bool = False


class OptimalStrategyScanThread(QThread):
    """扫描所有使用历史数据的策略，找出最优策略及其参数."""

    progress = Signal(int, int)  # 当前完成策略数, 总策略数
    status_message = Signal(str)  # 状态文本
    result_ready = Signal(object, object)  # StrategyScanResult | None, error | None

    def __init__(
        self,
        engine: GenerationEngine,
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
        self.setObjectName("OptimalStrategyScanThread")
        self.engine = engine
        self.profile = profile
        self.data_repository = data_repository
        self.start_date = start_date
        self.end_date = end_date
        self.tickets_per_round = tickets_per_round
        self.base_options = base_options
        self.plugin_dir = plugin_dir

    def run(self) -> None:
        try:
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

            if len(records) < 100:
                self.result_ready.emit(
                    None,
                    ValueError("历史数据不足，所有候选策略至少需要 100 期历史数据"),
                )
                return

            candidates = [
                s for s in self.engine.list_strategies() if needs_history(s.metadata.id)
            ]
            if not candidates:
                self.result_ready.emit(
                    None, ValueError("当前没有使用历史数据的策略可用")
                )
                return

            tasks = [
                RoundTask(index=i, actual=r) for i, r in enumerate(target_records)
            ]

            all_results: List[Tuple[str, Optional[int], BatchBacktestResult]] = []
            completed = 0
            total = len(candidates)
            interrupted = False

            for strategy in candidates:
                if self.isInterruptionRequested():
                    interrupted = True
                    break

                strategy_id = strategy.metadata.id
                resolved = resolve_optimal_param(strategy_id)

                base_context = RoundBacktestContext(
                    strategy_id=strategy_id,
                    profile_key=self.profile.key,
                    tickets_per_round=self.tickets_per_round,
                    options=dict(self.base_options),
                    is_ml=strategy_id.startswith(("xgboost", "lightgbm", "catboost")),
                    needs_history=True,
                    records=records,
                    seed=42,
                    plugin_dir=self.plugin_dir,
                )

                if resolved is None:
                    # 无独立期数参数的策略，使用默认参数跑一次
                    results = scan_param_values(
                        base_context,
                        tasks,
                        "",
                        [None],  # 占位，实际不使用
                        progress_callback=None,
                        status_callback=None,
                        interruption_callback=self.isInterruptionRequested,
                    )
                    value, result = results[0]
                    all_results.append((strategy_id, None, result))
                else:
                    param_name, param_values = resolved
                    value_results = scan_param_values(
                        base_context,
                        tasks,
                        param_name,
                        param_values,
                        progress_callback=None,
                        status_callback=lambda msg: self.status_message.emit(msg),
                        interruption_callback=self.isInterruptionRequested,
                    )
                    best = self._pick_best_param(value_results)
                    if best is not None:
                        all_results.append((strategy_id, best[0], best[1]))
                    else:
                        # 该策略所有参数均失败，记录一个失败结果
                        all_results.append(
                            (
                                strategy_id,
                                None,
                                BatchBacktestResult(
                                    total_rounds=len(tasks),
                                    errors=[f"{strategy_id} 所有参数扫描均失败"],
                                ),
                            )
                        )

                completed += 1
                self.progress.emit(completed, total)
                self.status_message.emit(
                    f"已完成 {strategy.metadata.name} 的策略扫描（{completed}/{total}）"
                )

            if not all_results:
                self.result_ready.emit(
                    None, ValueError("没有完成任何策略扫描")
                )
                return

            if all(result.errors for _, _, result in all_results):
                self.result_ready.emit(
                    None,
                    ValueError(
                        "所有策略扫描均失败: "
                        + "; ".join(
                            f"{sid}: {result.errors[0]}"
                            for sid, _, result in all_results
                        )
                    ),
                )
                return

            best = self._pick_best_strategy(all_results)
            if best is None:
                self.result_ready.emit(
                    None, ValueError("所有策略组合均失败")
                )
                return

            strategy_id, value, result = best
            strategy = self.engine.get(strategy_id)
            strategy_name = (
                strategy.metadata.name if strategy is not None else strategy_id
            )
            param_name = None
            if value is not None:
                resolved = resolve_optimal_param(strategy_id)
                param_name = resolved[0] if resolved else None

            scan_result = StrategyScanResult(
                optimal_strategy_id=strategy_id,
                optimal_strategy_name=strategy_name,
                param_name=param_name,
                optimal_value=value,
                optimal_result=result,
                all_results=all_results,
                interrupted=interrupted,
            )
            self.result_ready.emit(scan_result, None)
        except Exception as exc:  # noqa: BLE001
            self.result_ready.emit(None, exc)

    @staticmethod
    def _pick_best_param(
        results: List[Tuple[int, BatchBacktestResult]],
    ) -> Optional[Tuple[int, BatchBacktestResult]]:
        eligible = [item for item in results if not item[1].errors]
        if not eligible:
            return None
        return max(
            eligible,
            key=lambda item: (
                item[1].total_fixed_prize,
                item[1].hit_count,
                -item[0],
            ),
        )

    @staticmethod
    def _pick_best_strategy(
        results: List[Tuple[str, Optional[int], BatchBacktestResult]],
    ) -> Optional[Tuple[str, Optional[int], BatchBacktestResult]]:
        eligible = [item for item in results if not item[2].errors]
        if not eligible:
            return None
        return max(
            eligible,
            key=lambda item: (
                item[2].total_fixed_prize,
                item[2].hit_count,
                item[0],
            ),
        )
```

- [ ] **Step 4: Adjust `scan_param_values` for parameterless strategies**

当前 `scan_param_values` 要求 `param_values: List[int]` 和 `param_name: str`。对于无参数策略，需要允许 `param_values` 为 `[None]` 且不在 options 中设置参数。

修改 `_build_context`：

```python
def _build_context(
    base_context: RoundBacktestContext,
    param_name: str,
    value: Optional[int],
) -> RoundBacktestContext:
    options = dict(base_context.options)
    if value is not None:
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
```

并调整 `scan_param_values` 的类型签名：`param_values: List[Optional[int]]`。

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_optimal_strategy_scan.py tests/test_optimal_period_scan.py -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add caipiao/ui/optimal_strategy_scan_thread.py tests/test_optimal_strategy_scan.py caipiao/ui/optimal_period_scan_thread.py
git commit -m "feat(optimal-strategy): add strategy+parameter scan thread"
```

---

## Task 3: Integrate into BatchBacktestDialog

**Files:**
- Modify: `caipiao/ui/components/batch_backtest_dialog.py`
- Test: 手动运行 `python main.py` 验证 UI。

**Interfaces:**
- Consumes: `OptimalStrategyScanThread`, `StrategyScanResult` from `caipiao.ui.optimal_strategy_scan_thread`.
- Produces: 新增按钮 `_strategy_scan_btn`、回调 `_run_optimal_strategy_scan`、结果处理 `_on_strategy_scan_finished`。

- [ ] **Step 1: 添加按钮**

在 `_setup_ui` 中，在 `optimal_btn` 右侧新增：

```python
        self.strategy_scan_btn = QPushButton("一键找最优策略和参数")
        self.strategy_scan_btn.setToolTip(
            "自动扫描所有使用历史数据的策略及其期数参数，"
            "找出固定奖金合计最高的策略和参数并应用"
        )
        self.strategy_scan_btn.clicked.connect(self._run_optimal_strategy_scan)
        control_layout.addWidget(self.strategy_scan_btn)
```

- [ ] **Step 2: 实现启动回调**

```python
    def _run_optimal_strategy_scan(self) -> None:
        start_qdate = self.start_date_edit.date()
        end_qdate = self.end_date_edit.date()
        if start_qdate > end_qdate:
            QMessageBox.warning(self, "日期错误", "起始日期不能晚于结束日期")
            return

        start_date = datetime(start_qdate.year(), start_qdate.month(), start_qdate.day())
        end_date = datetime(end_qdate.year(), end_qdate.month(), end_qdate.day())

        records = self.data_repository.get_all()
        if len(records) < 100:
            QMessageBox.warning(self, "数据不足", "候选策略需要至少 100 期历史数据")
            return

        try:
            base_options = self.strategy_panel.current_options()
        except ValueError as exc:
            QMessageBox.warning(self, "参数错误", str(exc))
            return

        self.run_btn.setEnabled(False)
        self.run_btn.setText("扫描中...")
        self.stop_btn.setEnabled(True)
        self.optimal_btn.setEnabled(False)
        self.strategy_scan_btn.setEnabled(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.detail_text.clear()
        self.status_text.clear()
        self.summary_label.setText("正在扫描最优策略和参数，请稍候...")

        self._strategy_scan_thread = OptimalStrategyScanThread(
            engine=self.context.engine,
            profile=self.profile,
            data_repository=self.data_repository,
            start_date=start_date,
            end_date=end_date,
            tickets_per_round=self.count_spin.value(),
            base_options=base_options,
            plugin_dir=self.plugin_dir,
            parent=self,
        )
        self._strategy_scan_thread.progress.connect(self._on_progress)
        self._strategy_scan_thread.status_message.connect(self._on_status_message)
        self._strategy_scan_thread.result_ready.connect(
            self._on_strategy_scan_finished, Qt.ConnectionType.QueuedConnection
        )
        self._strategy_scan_thread.finished.connect(self._cleanup_finished_strategy_scan_thread)
        self._strategy_scan_thread.start()

    def _cleanup_finished_strategy_scan_thread(self) -> None:
        thread = self.sender()
        if thread is None:
            return
        if getattr(self, "_strategy_scan_thread", None) is thread:
            self._strategy_scan_thread = None
        try:
            thread.deleteLater()
        except RuntimeError:
            pass
```

- [ ] **Step 3: 实现结果回调**

```python
    def _on_strategy_scan_finished(self, result, error) -> None:
        self.run_btn.setEnabled(True)
        self.run_btn.setText("开始批量回测")
        self.stop_btn.setEnabled(False)
        self.optimal_btn.setEnabled(True)
        self.strategy_scan_btn.setEnabled(True)
        self.progress.setVisible(False)

        if error:
            QMessageBox.critical(self, "扫描失败", str(error))
            self.summary_label.setText("一键找最优策略和参数失败。")
            return

        if result is None:
            self.summary_label.setText(
                self.summary_label.text() + "\n（已停止）"
            )
            return

        # 自动将最优策略和参数写回策略面板
        self.strategy_panel.set_strategy_id(result.optimal_strategy_id)
        if result.param_name is not None and result.optimal_value is not None:
            self.strategy_panel.set_options({result.param_name: result.optimal_value})

        summary_lines = [
            f"最优策略：{result.optimal_strategy_name} ({result.optimal_strategy_id})",
        ]
        if result.param_name is not None:
            summary_lines.append(f"最优参数：{result.param_name} = {result.optimal_value}")
        summary_lines.extend([
            f"回测期数：{result.optimal_result.total_rounds} 期",
            f"总花费：{result.optimal_result.total_cost} 元",
            f"固定奖金合计：{result.optimal_result.total_fixed_prize} 元",
            f"中奖次数：{result.optimal_result.hit_count} 次",
            f"首注中奖次数：{result.optimal_result.first_ticket_hit_count} 次",
        ])
        if result.interrupted:
            summary_lines.append("（已中断，结果为部分扫描）")
        self.summary_label.setText("\n".join(summary_lines))

        ranked = sorted(
            result.all_results,
            key=lambda item: (
                item[2].total_fixed_prize,
                item[2].hit_count,
                item[0],
            ),
            reverse=True,
        )
        self.status_text.append("=" * 40)
        self.status_text.append("一键找最优策略和参数扫描结果：")
        for rank, (strategy_id, value, res) in enumerate(ranked, start=1):
            strategy = self.context.engine.get(strategy_id)
            name = strategy.metadata.name if strategy is not None else strategy_id
            failed_mark = "（失败）" if res.errors else ""
            param_text = f" 参数={value}" if value is not None else ""
            self.status_text.append(
                f"{rank}. {name} ({strategy_id}){param_text}: "
                f"固定奖金 {res.total_fixed_prize} 元, "
                f"中奖 {res.hit_count} 次, "
                f"首注 {res.first_ticket_hit_count} 次"
                f"{failed_mark}"
            )
        self.status_text.append("=" * 40)
```

- [ ] **Step 4: 同步现有按钮状态**

在 `_run_batch_backtest` 中禁用 `strategy_scan_btn`：

```python
        self.optimal_btn.setEnabled(False)
        self.strategy_scan_btn.setEnabled(False)
```

在 `_on_finished` 中恢复：

```python
        self.optimal_btn.setEnabled(True)
        self.strategy_scan_btn.setEnabled(True)
```

在 `_run_optimal_period_scan` 中禁用 `strategy_scan_btn`：

```python
        self.run_btn.setEnabled(False)
        self.run_btn.setText("扫描中...")
        self.stop_btn.setEnabled(True)
        self.optimal_btn.setEnabled(False)
        self.strategy_scan_btn.setEnabled(False)
```

在 `_on_optimal_finished` 中恢复 `strategy_scan_btn`：

```python
        self.stop_btn.setEnabled(False)
        self.optimal_btn.setEnabled(True)
        self.strategy_scan_btn.setEnabled(True)
```

在 `_stop_batch_backtest` 中处理策略扫描线程：

```python
        if getattr(self, "_strategy_scan_thread", None) and self._strategy_scan_thread.isRunning():
            self.status_text.append("用户请求停止策略扫描...")
            self._strategy_scan_thread.requestInterruption()
            self.stop_btn.setEnabled(False)
```

在 `closeEvent` 中处理策略扫描线程：

```python
        if getattr(self, "_strategy_scan_thread", None) and self._strategy_scan_thread.isRunning():
            self._strategy_scan_thread.requestInterruption()
            if not self._strategy_scan_thread.wait(5000):
                self._strategy_scan_thread.terminate()
                self._strategy_scan_thread.wait(1000)
```

- [ ] **Step 5: 运行测试**

```bash
venv/Scripts/python -m pytest tests/test_optimal_strategy_scan.py tests/test_optimal_period_scan.py tests/test_batch_backtest_integration.py tests/test_batch_backtest_worker.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add caipiao/ui/components/batch_backtest_dialog.py
git commit -m "feat(optimal-strategy): integrate strategy scan button into dialog"
```

---

## Task 4: Tests and Verification

- [ ] **Step 1: 运行新增测试**

```bash
venv/Scripts/python -m pytest tests/test_optimal_strategy_scan.py -v
```

Expected: all PASS

- [ ] **Step 2: 运行现有相关测试**

```bash
venv/Scripts/python -m pytest tests/test_optimal_period_scan.py tests/test_batch_backtest_integration.py tests/test_batch_backtest_worker.py -v
```

Expected: all PASS

- [ ] **Step 3: 运行全量测试**

```bash
venv/Scripts/python -m pytest tests/ -q --tb=short
```

Expected: all PASS

- [ ] **Step 4: 手动启动程序验证 UI**

```bash
venv/Scripts/python main.py
```

验证：
- 打开批量历史回测窗口，确认出现“一键找最优策略和参数”按钮。
- 点击后等待扫描完成，确认策略面板自动切换为最优策略并设置参数。
- 检查日志区是否列出所有候选策略的排名。
- 确认“一键找最优期数”按钮仍然正常工作。

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "test(optimal-strategy): add tests and verify integration"
```

---

## Self-Review

**Spec coverage:**
- 候选策略过滤 → Task 2
- 无参数策略处理 → Task 2
- 参数扫描复用 → Task 1
- 全局最优排序 → Task 2
- 自动回写策略面板 → Task 3
- 结果摘要与排名 → Task 3
- 错误处理 → Task 2 + Task 3
- 测试 → Task 2 + Task 4
- UI 状态同步 → Task 3

**Placeholder scan:** 无 TBD/TODO/待实现。

**Type consistency:**
- `scan_param_values` 签名中 `param_values: List[Optional[int]]` 与 `_build_context` 的 `value: Optional[int]` 一致。
- `StrategyScanResult` 字段与 `OptimalStrategyScanThread.result_ready` 信号一致。
- `_pick_best_strategy` 返回 `Tuple[str, Optional[int], BatchBacktestResult]` 与结果构造一致。

**潜在问题：**
- `scan_param_values` 对无参数策略使用 `[None]` 列表和空 `param_name` 略显别扭。如果更优雅的方式是单独提供一个 `run_single_strategy` 函数，但考虑到复用现有 `scan_param_values` 的失败隔离、进程池、回调机制，当前方式更简单。
- `OptimalStrategyScanThread` 按策略顺序串行扫描，每个策略内部通过 `scan_param_values` 并行扫描参数。若策略数量多，整体耗时仍较长。后续可考虑策略间也并行，但会增加实现复杂度。
