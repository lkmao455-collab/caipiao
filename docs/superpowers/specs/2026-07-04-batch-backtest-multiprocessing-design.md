# 批量历史回测多进程优化设计文档

## 1. 目标与成功标准

### 1.1 目标
对 `caipiao/ui/batch_backtest_thread.py` 中的批量历史回测进行多进程并行优化，在不改变 UI 行为的前提下缩短回测总耗时。

### 1.2 成功标准
- **速度提升倍数**：在常见多核机器上，批量回测 wall-clock 时间相比单线程版本有显著提升（预期接近 CPU 核心数，受 ML 训练峰值限制）。
- **通用性与可扩展性**：方案覆盖所有策略类型（统计策略、ML 策略），不针对某一种策略硬编码。
- **线程安全**：无数据冲突、无死锁、无内存溢出。
- **兼容性**：保持现有 `BatchBacktestThread` 的 Qt 信号接口，UI 改动最小化。

## 2. 现状分析

### 2.1 当前实现
- 批量回测入口：`caipiao/ui/batch_backtest_thread.py` 中的 `BatchBacktestThread.run()`。
- 主循环：逐期遍历目标日期区间内的开奖记录，每期执行：
  1. 切出历史记录 `history`。
  2. 若为 ML 策略，调用 `_prepare_ml_options()` 训练临时模型。
  3. 调用 `GenerationEngine.generate()` 生成号码。
  4. 逐注与当期真实开奖对比，更新 `BatchBacktestResult`。
- 当前没有任何并行/线程池/进程池使用。
- 结果通过 Qt 信号 `progress`、`status_message`、`round_ready`、`result_ready` 与 UI 通信。

### 2.2 性能瓶颈
- **CPU 密集**：ML 策略每回测日期都会重新训练模型，是主要耗时来源。
- **期与期独立**：每期只依赖历史记录（只读），没有状态依赖，天然适合并行。
- **GIL 限制**：ML 训练在 Python GIL 内，Python 线程池无法真正利用多核。

## 3. 方案选择

### 3.1 候选方案

| 方案 | 并发单元 | 优点 | 缺点 | 适用性 |
|---|---|---|---|---|
| A. 期级进程池并行 | 每期一个子进程 | 真正利用多核；进程隔离避免 ML 库线程冲突；通用性强 | 内存开销较高；需要序列化 | **推荐** |
| B. 期级线程池并行 | 每期一个子线程 | 实现简单；内存开销低 | 受 GIL 限制；ML 库内部线程叠加风险大 | 不推荐 |
| C. 混合分层并行 | 非 ML 用线程池，ML 用进程池 | 理论上可针对不同策略优化 | 实现复杂；需要按策略分支；维护成本高 | 暂缓 |

### 3.2 选定方案
采用 **方案 A：期级进程池并行**。

理由：
1. 每期任务独立，适合拆分。
2. 进程级并行可绕过 GIL，真正利用多核。
3. 用户接受进程池 + 数据拷贝的内存开销。
4. ML 库内部线程数可通过环境变量和库参数限制，避免冲突。

## 4. 总体并发架构

```
┌─────────────────────────────────────────────────────────────┐
│                        UI 主线程                             │
│  BatchBacktestDialog  ──►  BatchBacktestThread (QThread)     │
└─────────────────────────┬───────────────────────────────────┘
                          │ 提交任务 / 收集结果
┌─────────────────────────┴───────────────────────────────────┐
│              进程池 (ProcessPoolExecutor)                    │
│  worker_round_backtest(context, task)                        │
│     ├── 切历史数据                                          │
│     ├── 训练 ML 模型 / 生成号码 / 兑奖                       │
│     └── 返回 RoundResult（纯数据，无 Qt 对象）               │
└─────────────────────────────────────────────────────────────┘
```

- 保留 `BatchBacktestThread` 作为 UI 后台工作线程。
- 内部使用 `concurrent.futures.ProcessPoolExecutor` 派发每期计算任务。
- 进程池大小默认：`max(1, min(os.cpu_count() // 2, 4))`，可通过配置 `batch_backtest_workers` 调整。
- 每个 worker 进程启动时限制 ML 库内部线程数为 1，避免与进程级并行叠加。

## 5. 数据流与序列化

### 5.1 只读上下文（RoundBacktestContext）
每期任务共享的只读数据：

```python
@dataclass(frozen=True)
class RoundBacktestContext:
    strategy_id: str
    profile_key: str
    tickets_per_round: int
    options: dict
    is_ml: bool
    needs_history: bool
    records: list[DrawRecord]
    seed: int
```

### 5.2 每期任务输入（RoundTask）
```python
@dataclass(frozen=True)
class RoundTask:
    index: int
    actual: DrawRecord
```

### 5.3 Worker 输出（RoundResult）
```python
@dataclass(frozen=True)
class RoundResult:
    index: int
    total_cost: int
    hit_count: int
    total_fixed_prize: int
    float_prize_count: int
    winners: list[int]
    ticket_results: list[dict]
    ticket_index_hits: dict[int, int]
    error: str | None
```

### 5.4 主线程汇总
1. 按 `RoundResult.index` 排序，保证最终顺序与日期顺序一致。
2. 累加各期统计字段。
3. 合并 `ticket_results`、`ticket_index_hits`、`winners`。
4. 还原为现有 `BatchBacktestResult`，保持 UI 后续逻辑不变。

### 5.5 序列化约束
- 不传递 Qt 对象、数据库连接、文件句柄、lambda/闭包。
- `GenerationEngine`、ML predictor 等对象在 worker 进程内部重新构造。
- 实施前先用 `pickle.dumps()` 验证参数可序列化。

## 6. 安全与同步

### 6.1 数据冲突防范
- worker 只读取 `RoundBacktestContext` 和 `RoundTask`，返回新的 `RoundResult`。
- 无共享可变状态；不跨进程修改对象。
- 每个 worker 独立训练模型、独立释放资源。

### 6.2 死锁防范
- 只使用 `ProcessPoolExecutor.submit` + `as_completed`。
- 不在 worker 内再启动子进程或线程池。
- 不在 `__del__`、析构函数、信号处理中请求进程池结果。

### 6.3 内存溢出防范
- 限制进程数：默认 4，可配置。
- 限制每个 worker 内部线程数：
  - `OMP_NUM_THREADS=1`
  - `OPENBLAS_NUM_THREADS=1`
  - `MKL_NUM_THREADS=1`
  - `VECLIB_MAXIMUM_THREADS=1`
  - `NUMEXPR_NUM_THREADS=1`
  - XGBoost `nthread=1`
  - LightGBM `num_threads=1`
  - CatBoost `thread_count=1`
- 使用 `as_completed` 及时消费结果，不缓存全部 future。
- `records` 列表只读，Linux fork 下利用写时复制（COW）。
- 任务粒度按"期"拆分，避免过小任务导致调度开销。

### 6.4 临时文件冲突解决方案
- 每个 worker 进程启动时创建独立临时目录：
  ```
  .caipiao/tmp/backtest_workers/worker_<pid>/
  ```
- 通过 `ProcessPoolExecutor(initializer=...)` 在进程启动时创建目录并设置环境变量。
- CatBoost 等库训练时显式指定 `train_dir` 为该目录。
- worker 正常退出时通过 `atexit` 清理；批量回测结束时主线程兜底清理；程序异常退出时下次启动清理过期目录。

### 6.5 随机性控制
- 每个 worker 根据 `context.seed + task.index` 设置独立随机种子，保证结果可复现。

## 7. 错误处理、进度与取消

### 7.1 错误处理
- worker 内部 `try/except`，失败返回 `RoundResult(error="...")`。
- 主线程收集错误，最终显示"已完成 X 期，Y 期成功，Z 期失败"。
- 整批失败阈值：若失败期数超过 30%，直接终止并提示环境或配置异常。

### 7.2 进度上报
- 使用 `as_completed` 按完成数量上报进度：
  ```python
  self.progress.emit(completed_count, total)
  ```
- `round_ready` 信号保留，但语义从"第 N 期完成"变为"又完成 1 期"。

### 7.3 取消机制
```python
try:
    executor = ProcessPoolExecutor(...)
    futures = [executor.submit(worker_round_backtest, context, task)
               for task in tasks]
    for future in as_completed(futures):
        if self.isInterruptionRequested():
            break
        # 收集结果
finally:
    for f in futures:
        f.cancel()
    executor.shutdown(wait=False, cancel_futures=True)
    _cleanup_all_worker_temp_dirs()
```

- Python 3.9+ 支持 `cancel_futures=True`；低版本需手动兼容。
- `wait=False` 避免关闭阻塞 UI。

## 8. 影响范围

### 8.1 需要修改的文件
- `caipiao/ui/batch_backtest_thread.py`：主改造文件。
- 可能新增 `caipiao/ui/batch_backtest_worker.py`：worker 函数和初始化函数。
- `caipiao/ui/components/batch_backtest_dialog.py`：可能需要适配 `round_ready` 信号语义变化。

### 8.2 不需要修改的文件
- `caipiao/ui/main_window.py`：入口不变。
- `caipiao/persistence/backtest_db.py`：保存逻辑不变。
- ML 模型训练代码本身不变，仅参数调整。

## 9. 测试计划

- 单元测试：验证 `RoundResult` 按 `index` 正确合并。
- 集成测试：覆盖统计策略和 ML 策略的批量回测，验证结果与单线程版本一致。
- 性能测试：在相同日期区间对比 wall-clock 时间。
- 异常测试：模拟 worker 失败，验证错误收集和汇总。
- 取消测试：验证中途取消时进程池正确关闭，无僵尸进程。

## 10. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| pickle 序列化失败 | worker 无法启动 | 实施前验证参数可序列化；只传纯数据 |
| ML 库内部线程叠加 | 性能下降、OOM | 限制每个 worker 内部线程数为 1 |
| 内存峰值过高 | OOM | 默认进程数保守；提供配置项 |
| 临时文件冲突 | 训练失败 | 每 worker 独立临时目录 |
| 结果顺序错乱 | UI 展示异常 | 按 `index` 排序后合并 |
| 子进程成为僵尸 | 资源泄漏 | `executor.shutdown(wait=False, cancel_futures=True)` |
| Windows spawn 启动慢 | 首次回测延迟 | worker 函数放独立模块；模块顶层避免耗时初始化 |

## 11. 后续扩展

- 支持"多策略/多参数网格"级并行：在更高层把不同策略/参数组合也作为独立任务提交到同一进程池。
- 支持结果流式持久化：每期结果完成即写入数据库，减少内存占用。
- 支持回测任务队列和后台运行：允许用户启动回测后关闭对话框，稍后查看结果。
