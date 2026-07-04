"""批量回测多进程性能基准脚本.

用法:
    python scripts/benchmark_batch_backtest.py

对比不同 worker 数下随机策略与 ML 策略的批量回测耗时。
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta

# 让脚本可以直接从项目根目录运行时导入 caipiao 包
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from caipiao.core.engine import GenerationEngine
from caipiao.core.profile import SSQ
from caipiao.core.strategies import RandomStrategy
from caipiao.data.models import DrawRecord
from caipiao.ui.batch_backtest_thread import BatchBacktestThread


class _MockRepository:
    """模拟数据仓库，仅实现 get_all() 接口."""

    def __init__(self, records):
        self._records = list(records)

    def get_all(self):
        return self._records[:]


def _make_ssq_records(n: int) -> list[DrawRecord]:
    """生成 n 期双色球模拟开奖记录."""
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
                issue=f"{base.year}{i + 1:03d}",
                draw_date=base + timedelta(days=i),
                red_balls=sorted(nums),
                blue_ball=blue,
            )
        )
    return records


def _make_engine() -> GenerationEngine:
    engine = GenerationEngine()
    engine.register(RandomStrategy())
    return engine


def _run_benchmark(strategy_id: str, workers: int, records: list[DrawRecord],
                   start_date: datetime, end_date: datetime,
                   tickets_per_round: int) -> float:
    """运行一次回测并返回耗时（秒）。"""
    options = {"batch_backtest_workers": workers}
    thread = BatchBacktestThread(
        engine=_make_engine(),
        strategy_id=strategy_id,
        profile=SSQ,
        data_repository=_MockRepository(records),
        start_date=start_date,
        end_date=end_date,
        tickets_per_round=tickets_per_round,
        options=options,
        parent=None,
    )

    result = None
    exception = None

    def on_finished(r, exc):
        nonlocal result, exception
        result = r
        exception = exc

    thread.result_ready.connect(on_finished)

    start = time.perf_counter()
    thread.run()
    elapsed = time.perf_counter() - start

    if exception is not None:
        raise exception

    status = "ok" if result and not result.errors else f"errors={len(result.errors) if result else '?'})"
    print(f"strategy={strategy_id} workers={workers} elapsed={elapsed:.2f}s rounds={result.total_rounds if result else 0} cost={result.total_cost if result else 0} {status}")
    return elapsed


def benchmark_random() -> None:
    """随机策略基准：60 期目标回测，比较 1/4 worker。"""
    total_records = 100
    target_rounds = 60
    records = _make_ssq_records(total_records)
    start_date = records[total_records - target_rounds].draw_date
    end_date = records[-1].draw_date

    print("\n[random strategy benchmark]")
    _run_benchmark("random", 1, records, start_date, end_date, tickets_per_round=20)
    _run_benchmark("random", 4, records, start_date, end_date, tickets_per_round=20)


def benchmark_xgboost() -> None:
    """XGBoost 策略基准：40 期目标回测，比较 1/4 worker。

    每期需要至少 100 期历史数据，因此总记录数 = 100 + target_rounds。
    """
    try:
        import xgboost  # noqa: F401
    except ImportError:
        print("\n[xgboost strategy benchmark skipped: xgboost not installed]")
        return

    target_rounds = 40
    total_records = 100 + target_rounds
    records = _make_ssq_records(total_records)
    start_date = records[100].draw_date
    end_date = records[-1].draw_date

    print("\n[xgboost strategy benchmark]")
    _run_benchmark("xgboost", 1, records, start_date, end_date, tickets_per_round=5)
    _run_benchmark("xgboost", 4, records, start_date, end_date, tickets_per_round=5)


def main() -> int:
    print(f"CPU count: {__import__('os').cpu_count()}")
    benchmark_random()
    benchmark_xgboost()
    return 0


if __name__ == "__main__":
    sys.exit(main())
