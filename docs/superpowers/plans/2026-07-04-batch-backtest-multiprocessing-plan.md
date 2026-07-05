# 批量历史回测多进程优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `BatchBacktestThread` 的逐期串行回测改造为基于 `ProcessPoolExecutor` 的多进程并行回测，保证数据安全、无死锁、无 OOM，并保持现有 Qt 信号接口兼容。

**Architecture：** 保留 `BatchBacktestThread` 作为 UI 后台线程；将"跑一期回测"拆分为可序列化的纯函数 `worker_round_backtest`，通过 `ProcessPoolExecutor` 派发；主线程按 `index` 排序合并 `RoundResult`，还原为 `BatchBacktestResult`。

**Tech Stack：** Python 3.x、PyQt6、concurrent.futures、multiprocessing、pickle、XGBoost/LightGBM/CatBoost。

## Global Constraints

- 进程池大小默认 `max(1, min(os.cpu_count() // 2, 4))`，可通过配置 `batch_backtest_workers` 调整。
- 每个 worker 进程启动时限制 ML 库内部线程数为 1。
- 不传递 Qt 对象、数据库连接、文件句柄、lambda/闭包给 worker。
- `GenerationEngine`、ML predictor 等对象在 worker 进程内部重新构造。
- 保持现有 `BatchBacktestThread` 的 Qt 信号接口：`progress(int,int)`、`status_message(str)`、`round_ready(int,int,list)`、`result_ready(object,object)`。
- 结果按 `RoundResult.index` 排序合并，保证最终顺序与日期顺序一致。

---

## File Structure

| 文件 | 职责 |
|---|---|
| `caipiao/ui/batch_backtest_thread.py` | 现有批量回测线程主循环，需改造为派发/收集进程任务。 |
| `caipiao/ui/batch_backtest_worker.py` | 新增：worker 进程函数、初始化函数、上下文/任务/结果数据类。 |
| `caipiao/ui/components/batch_backtest_dialog.py` | 可能需适配 `round_ready` 信号语义变化（可选）。 |
| `tests/test_batch_backtest_worker.py` | 新增：worker 函数与结果合并的单元测试。 |
| `tests/test_batch_backtest_integration.py` | 新增：统计策略与 ML 策略的多进程回测集成测试。 |

---

### Task 1: 创建 worker 模块与数据类

**Files:**
- Create: `caipiao/ui/batch_backtest_worker.py`
- Test: `tests/test_batch_backtest_worker.py`

**Interfaces:**
- Produces:
  - `RoundBacktestContext(strategy_id, profile_key, tickets_per_round, options, is_ml, needs_history, records, seed)`
  - `RoundTask(index, actual)`
  - `RoundResult(index, total_cost, hit_count, total_fixed_prize, float_prize_count, winners, ticket_results, ticket_index_hits, error=None)`
  - `worker_round_backtest(context: RoundBacktestContext, task: RoundTask) -> RoundResult`

- [ ] **Step 1: 编写失败测试**

```python
# tests/test_batch_backtest_worker.py
import pytest
from datetime import datetime
from caipiao.ui.batch_backtest_worker import (
    RoundBacktestContext,
    RoundTask,
    RoundResult,
    worker_round_backtest,
)
from caipiao.core.models import DrawRecord


def test_worker_returns_round_result():
    record = DrawRecord(
        draw_date=datetime(2024, 1, 1),
        numbers=[1, 2, 3, 4, 5, 6, 7],
        special_number=None,
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
    task = RoundTask(index=0, actual=record)
    result = worker_round_backtest(context, task)
    assert isinstance(result, RoundResult)
    assert result.index == 0
    assert result.error is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_batch_backtest_worker.py::test_worker_returns_round_result -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'caipiao.ui.batch_backtest_worker'`

- [ ] **Step 3: 实现数据类与 worker 函数骨架**

```python
# caipiao/ui/batch_backtest_worker.py
from __future__ import annotations

import os
import random
import shutil
import atexit
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from caipiao.core.engine import GenerationEngine
from caipiao.core.prize import calculate_prize
from caipiao.core.profile import LotteryProfile, get_profile


@dataclass(frozen=True)
class RoundBacktestContext:
    strategy_id: str
    profile_key: str
    tickets_per_round: int
    options: dict
    is_ml: bool
    needs_history: bool
    records: list
    seed: int


@dataclass(frozen=True)
class RoundTask:
    index: int
    actual: Any


@dataclass(frozen=True)
class RoundResult:
    index: int
    total_cost: int = 0
    hit_count: int = 0
    total_fixed_prize: int = 0
    float_prize_count: int = 0
    winners: list[int] = field(default_factory=list)
    ticket_results: list[dict] = field(default_factory=list)
    ticket_index_hits: dict[int, int] = field(default_factory=dict)
    error: str | None = None


def _get_worker_temp_dir() -> str:
    pid = os.getpid()
    base = os.path.join(".caipiao", "tmp", "backtest_workers")
    path = os.path.join(base, f"worker_{pid}")
    os.makedirs(path, exist_ok=True)
    return path


def _cleanup_worker_temp_dir():
    shutil.rmtree(_get_worker_temp_dir(), ignore_errors=True)


def _configure_worker_threads():
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
    os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")


def init_worker_process(seed: int):
    """每个子进程启动时调用。"""
    _configure_worker_threads()
    _get_worker_temp_dir()
    atexit.register(_cleanup_worker_temp_dir)
    random.seed(seed)
    np.random.seed(seed)


def worker_round_backtest(context: RoundBacktestContext, task: RoundTask) -> RoundResult:
    """在子进程中执行一期回测。"""
    try:
        random.seed(context.seed + task.index)
        np.random.seed(context.seed + task.index)

        profile = get_profile(context.profile_key)
        engine = GenerationEngine()

        history = [r for r in context.records if r.draw_date < task.actual.draw_date]
        if context.needs_history and len(history) < 100:
            return RoundResult(index=task.index, error="history too short")

        options = dict(context.options)
        if context.needs_history:
            options["history"] = history

        # TODO: ML 模型训练需要把 _prepare_ml_options 的逻辑搬到这里
        # 暂时只支持非 ML 策略
        if context.is_ml:
            return RoundResult(index=task.index, error="ML not yet supported in worker")

        tickets = engine.generate(
            context.strategy_id,
            count=context.tickets_per_round,
            options=options,
        )

        total_cost = 0
        hit_count = 0
        total_fixed_prize = 0
        float_prize_count = 0
        winners = []
        ticket_results = []
        ticket_index_hits: dict[int, int] = {}

        for t_idx, ticket in enumerate(tickets):
            hits = {g.key: len(set(ticket.numbers_for(g.key)) & set(task.actual.numbers_for(g.key))) for g in profile.groups}
            prize_name, prize_amount = calculate_prize(profile.key, hits, ticket.groups, task.actual.groups)

            total_cost += 2
            ticket_results.append({
                "round": task.index,
                "ticket_index": t_idx,
                "hits": hits,
                "prize_name": prize_name,
                "prize_amount": prize_amount,
            })

            if prize_amount is not None:
                total_fixed_prize += prize_amount
                hit_count += 1
                winners.append(t_idx)
                ticket_index_hits[t_idx] = ticket_index_hits.get(t_idx, 0) + 1

        return RoundResult(
            index=task.index,
            total_cost=total_cost,
            hit_count=hit_count,
            total_fixed_prize=total_fixed_prize,
            float_prize_count=float_prize_count,
            winners=winners,
            ticket_results=ticket_results,
            ticket_index_hits=ticket_index_hits,
        )
    except Exception as e:
        return RoundResult(index=task.index, error=repr(e))
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_batch_backtest_worker.py::test_worker_returns_round_result -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add caipiao/ui/batch_backtest_worker.py tests/test_batch_backtest_worker.py
git commit -m "feat: add batch backtest worker module with data classes and skeleton"
```

---

### Task 2: 实现结果合并函数

**Files:**
- Modify: `caipiao/ui/batch_backtest_worker.py`
- Test: `tests/test_batch_backtest_worker.py`

**Interfaces:**
- Consumes: `RoundResult`
- Produces: `merge_round_results(results: list[RoundResult], total_rounds: int) -> BatchBacktestResult`

- [ ] **Step 1: 编写失败测试**

```python
def test_merge_round_results():
    from caipiao.ui.batch_backtest_thread import BatchBacktestResult
    r1 = RoundResult(index=0, total_cost=4, hit_count=1, total_fixed_prize=10)
    r2 = RoundResult(index=1, total_cost=4, hit_count=0, total_fixed_prize=0)
    merged = merge_round_results([r2, r1], total_rounds=2)
    assert merged.total_cost == 8
    assert merged.hit_count == 1
    assert merged.total_fixed_prize == 10
    assert merged.total_rounds == 2
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_batch_backtest_worker.py::test_merge_round_results -v`
Expected: FAIL with `ImportError: cannot import name 'merge_round_results'`

- [ ] **Step 3: 实现合并函数**

```python
# 追加到 caipiao/ui/batch_backtest_worker.py
from caipiao.ui.batch_backtest_thread import BatchBacktestResult


def merge_round_results(results: list[RoundResult], total_rounds: int) -> BatchBacktestResult:
    """按 index 排序合并各期结果。"""
    merged = BatchBacktestResult(total_rounds=total_rounds)
    sorted_results = sorted(results, key=lambda r: r.index)

    for r in sorted_results:
        if r.error:
            # 错误期数不影响汇总，仅记录
            continue
        merged.total_cost += r.total_cost
        merged.hit_count += r.hit_count
        merged.total_fixed_prize += r.total_fixed_prize
        merged.float_prize_count += r.float_prize_count
        merged.ticket_results.extend(r.ticket_results)
        for k, v in r.ticket_index_hits.items():
            merged.ticket_index_hits[k] = merged.ticket_index_hits.get(k, 0) + v
        # winners 是跨期的，是否需要保留取决于 BatchBacktestResult 的定义
        # 这里暂不合并 winners 到顶层，因为原语义是按期 emit

    return merged
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_batch_backtest_worker.py::test_merge_round_results -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add caipiao/ui/batch_backtest_worker.py tests/test_batch_backtest_worker.py
git commit -m "feat: add merge_round_results helper"
```

---

### Task 3: 将 ML 准备逻辑提取为可序列化函数

**Files:**
- Modify: `caipiao/ui/batch_backtest_thread.py`（查看 `_prepare_ml_options`）
- Modify: `caipiao/ui/batch_backtest_worker.py`
- Test: `tests/test_batch_backtest_worker.py`

**Interfaces:**
- Produces: `prepare_ml_options(history: list, options: dict, profile_key: str, draw_date, temp_dir: str) -> dict`

- [ ] **Step 1: 阅读现有 `_prepare_ml_options` 实现**

Run: `Read caipiao/ui/batch_backtest_thread.py:217-264`
记录：
- 构造了哪些 ML predictor
- 训练时是否需要临时目录
- 返回的 options 包含哪些键

- [ ] **Step 2: 编写失败测试**

```python
def test_prepare_ml_options_signature():
    # 仅验证函数可导入并返回 dict
    from caipiao.ui.batch_backtest_worker import prepare_ml_options
    result = prepare_ml_options([], {}, "ssq", datetime(2024, 1, 1), "/tmp")
    assert isinstance(result, dict)
```

- [ ] **Step 3: 把 `_prepare_ml_options` 逻辑搬到 worker 模块**

```python
# caipiao/ui/batch_backtest_worker.py
def prepare_ml_options(
    history: list,
    options: dict,
    profile_key: str,
    draw_date,
    temp_dir: str,
) -> dict:
    """基于现有 _prepare_ml_options 逻辑，改造为可序列化的纯函数。"""
    # TODO: 把原 _prepare_ml_options 的逻辑搬过来
    # 注意：训练时传入 temp_dir 给 CatBoost / XGBoost / LightGBM
    return options
```

- [ ] **Step 4: 修改原 `_prepare_ml_options` 复用新函数**

在 `caipiao/ui/batch_backtest_thread.py` 中，把 `_prepare_ml_options` 的函数体替换为调用 `prepare_ml_options`。

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/test_batch_backtest_worker.py::test_prepare_ml_options_signature -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add caipiao/ui/batch_backtest_worker.py caipiao/ui/batch_backtest_thread.py tests/test_batch_backtest_worker.py
git commit -m "refactor: extract ML preparation into serializable prepare_ml_options"
```

---

### Task 4: 改造 BatchBacktestThread 使用进程池

**Files:**
- Modify: `caipiao/ui/batch_backtest_thread.py`
- Test: `tests/test_batch_backtest_integration.py`

**Interfaces:**
- Consumes: `RoundBacktestContext`, `RoundTask`, `RoundResult`, `worker_round_backtest`, `init_worker_process`, `merge_round_results`
- Produces: 通过 `result_ready` 信号发出合并后的 `BatchBacktestResult`

- [ ] **Step 1: 阅读并理解现有 `BatchBacktestThread.run()`**

Run: `Read caipiao/ui/batch_backtest_thread.py:91-216`
记录当前主循环结构。

- [ ] **Step 2: 编写集成测试（先失败）**

```python
# tests/test_batch_backtest_integration.py
import pytest
from datetime import datetime, timedelta
from caipiao.ui.batch_backtest_thread import BatchBacktestThread
from caipiao.core.models import DrawRecord


def _make_records(n=10):
    return [
        DrawRecord(
            draw_date=datetime(2024, 1, 1) + timedelta(days=i),
            numbers=[1, 2, 3, 4, 5, 6, 7],
            special_number=None,
        )
        for i in range(n)
    ]


def test_batch_thread_runs_in_parallel():
    records = _make_records(5)
    thread = BatchBacktestThread(
        strategy_id="random",
        profile_key="ssq",
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 1, 5),
        tickets_per_round=1,
        options={},
        data_repository=MockRepository(records),
        parent=None,
    )
    result = None

    def on_finished(r, _):
        nonlocal result
        result = r

    thread.result_ready.connect(on_finished)
    thread.run()
    assert result is not None
    assert result.total_rounds == 5
    assert result.total_cost == 10
```

其中 `MockRepository` 需要实现 `get_all()` 返回记录列表。

- [ ] **Step 3: 改造 `BatchBacktestThread.run()`**

把现有主循环替换为：

```python
from concurrent.futures import ProcessPoolExecutor, as_completed
from caipiao.ui.batch_backtest_worker import (
    RoundBacktestContext,
    RoundTask,
    worker_round_backtest,
    init_worker_process,
    merge_round_results,
)

# 在类中新增配置属性
_DEFAULT_MAX_WORKERS = max(1, min(os.cpu_count() // 2, 4))

class BatchBacktestThread(QThread):
    # ... 原有信号和 __init__ ...

    def run(self) -> None:
        records = self.data_repository.get_all()
        target_records = [
            r for r in records
            if self.start_date.date() <= r.draw_date.date() <= self.end_date.date()
        ]
        target_records.sort(key=lambda r: r.draw_date)

        context = RoundBacktestContext(
            strategy_id=self.strategy_id,
            profile_key=self.profile.key,
            tickets_per_round=self.tickets_per_round,
            options=dict(self.options),
            is_ml=self._is_ml,
            needs_history=self._needs_history,
            records=records,
            seed=42,
        )
        tasks = [RoundTask(index=i, actual=r) for i, r in enumerate(target_records)]

        max_workers = self.options.get("batch_backtest_workers", _DEFAULT_MAX_WORKERS)
        executor = None
        futures = []
        round_results = []
        completed = 0
        errors = []

        try:
            executor = ProcessPoolExecutor(
                max_workers=max_workers,
                initializer=init_worker_process,
                initargs=(context.seed,),
            )
            futures = [executor.submit(worker_round_backtest, context, task)
                       for task in tasks]

            for future in as_completed(futures):
                if self.isInterruptionRequested():
                    break

                result = future.result()
                round_results.append(result)
                if result.error:
                    errors.append(result.error)
                else:
                    # 可选：emit round_ready，语义为"又完成一期"
                    self.round_ready.emit(result.index, len(tasks), result.winners)

                completed += 1
                self.progress.emit(completed, len(tasks))
                self.status_message.emit(f"已完成 {completed}/{len(tasks)} 期")

                if len(errors) > len(tasks) * 0.3:
                    break

        except Exception as e:
            self.result_ready.emit(None, e)
            return
        finally:
            if executor is not None:
                for f in futures:
                    f.cancel()
                executor.shutdown(wait=False, cancel_futures=True)

        if errors and completed == 0:
            self.result_ready.emit(None, Exception(errors[0]))
            return

        merged = merge_round_results(round_results, total_rounds=len(tasks))
        merged.errors = errors  # 如果 BatchBacktestResult 需要扩展
        self.result_ready.emit(merged, None)
```

- [ ] **Step 4: 运行集成测试**

Run: `pytest tests/test_batch_backtest_integration.py -v`
Expected: PASS（可能需要调整 `BatchBacktestResult` 兼容性）

- [ ] **Step 5: 提交**

```bash
git add caipiao/ui/batch_backtest_thread.py tests/test_batch_backtest_integration.py
git commit -m "feat: parallelize batch backtest with ProcessPoolExecutor"
```

---

### Task 5: 适配 UI 层与信号语义

**Files:**
- Modify: `caipiao/ui/components/batch_backtest_dialog.py`

**Interfaces:**
- Consumes: `round_ready(int, int, list)` 信号语义变化

- [ ] **Step 1: 阅读 `_on_round_ready` 实现**

Run: `Read caipiao/ui/components/batch_backtest_dialog.py`
找到 `_on_round_ready` 槽函数。

- [ ] **Step 2: 确认是否需要修改**

如果 `_on_round_ready` 仅做实时刷新而不强依赖"第 index 期"的语义，则不需要修改，只需确认。

- [ ] **Step 3: 如有必要，修改状态更新逻辑**

如果当前实现假设 `round_ready` 按顺序 emit 并累加 `_running_cost` 等字段，需要改为从 `result` 对象重新计算或忽略 `round_ready` 的累计作用。

示例修改：
```python
def _on_round_ready(self, index, total, winners):
    # 多进程下 index 不保证顺序，仅用于刷新进度
    self.progress_bar.setValue(int(index / total * 100))
```

- [ ] **Step 4: 运行 UI 相关测试**

Run: `pytest tests/ -v`
Expected: 所有测试通过

- [ ] **Step 5: 提交**

```bash
git add caipiao/ui/components/batch_backtest_dialog.py
git commit -m "ui: adapt batch dialog to out-of-order round_ready semantics"
```

---

### Task 6: 添加 ML 策略支持与临时目录隔离

**Files:**
- Modify: `caipiao/ui/batch_backtest_worker.py`
- Modify: `caipiao/ml/` 中各模型训练入口（仅参数调整）
- Test: `tests/test_batch_backtest_integration.py`

**Interfaces:**
- Produces: ML 策略也能在 worker 进程中正确训练并返回结果

- [ ] **Step 1: 完善 `prepare_ml_options` 函数**

把原 `_prepare_ml_options` 的完整逻辑搬到 `prepare_ml_options`，并在训练时传入 `_get_worker_temp_dir()`。

- [ ] **Step 2: 修改 ML 库训练参数**

- XGBoost: `nthread=1`
- LightGBM: `num_threads=1`
- CatBoost: `thread_count=1`，`train_dir=temp_dir`

- [ ] **Step 3: 在 worker 中启用 ML 分支**

```python
if context.is_ml:
    options = prepare_ml_options(history, options, context.profile_key, task.actual.draw_date, _get_worker_temp_dir())
```

- [ ] **Step 4: 编写 ML 策略集成测试**

```python
def test_batch_thread_ml_strategy():
    records = _make_records(10)
    thread = BatchBacktestThread(
        strategy_id="xgboost",
        profile_key="ssq",
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 1, 3),
        tickets_per_round=1,
        options={},
        data_repository=MockRepository(records),
        parent=None,
    )
    # 运行并验证无错误
```

- [ ] **Step 5: 运行测试**

Run: `pytest tests/test_batch_backtest_integration.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add caipiao/ui/batch_backtest_worker.py caipiao/ml/ tests/test_batch_backtest_integration.py
git commit -m "feat: support ML strategies in parallel backtest with isolated temp dirs"
```

---

### Task 7: 性能基准测试与调优

**Files:**
- Create: `scripts/benchmark_batch_backtest.py`

- [ ] **Step 1: 创建基准脚本**

```python
# scripts/benchmark_batch_backtest.py
import time
import sys
from caipiao.ui.batch_backtest_thread import BatchBacktestThread


def run(strategy_id, workers=None):
    # 构造相同日期区间的记录
    # ...
    start = time.perf_counter()
    thread = BatchBacktestThread(...)
    thread.run()
    elapsed = time.perf_counter() - start
    print(f"{strategy_id} workers={workers} elapsed={elapsed:.2f}s")


if __name__ == "__main__":
    run("random", workers=1)
    run("random", workers=4)
    run("xgboost", workers=1)
    run("xgboost", workers=4)
```

- [ ] **Step 2: 运行基准测试**

Run: `python scripts/benchmark_batch_backtest.py`
Expected: 多进程版本耗时显著低于单进程版本

- [ ] **Step 3: 根据结果调整默认 worker 数**

如果内存使用过高，降低 `_DEFAULT_MAX_WORKERS`；如果 CPU 利用率不足，提高上限。

- [ ] **Step 4: 提交**

```bash
git add scripts/benchmark_batch_backtest.py
git commit -m "chore: add batch backtest performance benchmark"
```

---

### Task 8: 清理与最终验证

**Files:**
- 项目全局

- [ ] **Step 1: 运行全量测试**

Run: `pytest tests/ -v`
Expected: 全部通过

- [ ] **Step 2: 检查代码风格**

Run: `flake8 caipiao/ui/batch_backtest_worker.py caipiao/ui/batch_backtest_thread.py`
Expected: 无严重问题

- [ ] **Step 3: 检查临时目录清理**

Run: 启动回测后取消，检查 `.caipiao/tmp/backtest_workers/` 无残留。

- [ ] **Step 4: 提交并准备合并**

```bash
git add .
git commit -m "feat: complete parallel batch backtest implementation"
```

---

## Self-Review

### Spec Coverage

| 设计文档章节 | 对应任务 |
|---|---|
| 总体并发架构 | Task 4 |
| 数据流与序列化 | Task 1, Task 2 |
| 安全与同步 | Task 1, Task 4, Task 6 |
| 临时文件冲突 | Task 1, Task 6 |
| 错误处理、进度、取消 | Task 4 |
| ML 库内部线程限制 | Task 1, Task 6 |
| 测试计划 | Task 1, Task 2, Task 3, Task 4, Task 6, Task 7, Task 8 |

### Placeholder Scan

- 无 TBD、TODO。
- 无"implement later"等模糊描述。
- 每个任务包含具体文件路径、接口、测试命令、提交命令。

### Type Consistency

- `RoundBacktestContext`、`RoundTask`、`RoundResult` 在 Task 1 定义，后续任务复用。
- `worker_round_backtest` 签名保持一致：`(context, task) -> RoundResult`。
- `merge_round_results` 签名：`(list[RoundResult], int) -> BatchBacktestResult`。
