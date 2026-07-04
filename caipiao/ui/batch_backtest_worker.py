"""批量历史回测 worker 函数与可序列化数据类.

本模块设计为在子进程中执行单期回测，所有输入/输出均须可被 pickle 序列化，
不得依赖 Qt 对象、数据库连接或文件句柄。
"""

from __future__ import annotations

import atexit
import os
import random
import shutil
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from caipiao.core.engine import GenerationEngine
from caipiao.core.prize import calculate_prize
from caipiao.core.profile import LotteryProfile, get_profile
from caipiao.core.strategies import (
    BalancedStrategy,
    CatBoostStrategy,
    ExcludeIncludeStrategy,
    HotColdStrategy,
    LightGBMStrategy,
    MissingNumberStrategy,
    OddEvenStrategy,
    RandomStrategy,
    SmartHotColdStrategy,
    XGBoostStrategy,
)
from caipiao.core.strategies.generic import build_strategies


@dataclass(frozen=True)
class RoundBacktestContext:
    """一期回测所需的全部上下文（可序列化）。"""

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
    """一期回测任务。"""

    index: int
    actual: Any


@dataclass(frozen=True)
class RoundResult:
    """一期回测结果。"""

    index: int
    total_cost: int = 0
    hit_count: int = 0
    total_fixed_prize: int = 0
    float_prize_count: int = 0
    winners: list[int] = field(default_factory=list)
    ticket_results: list[dict] = field(default_factory=list)
    ticket_index_hits: dict[int, int] = field(default_factory=dict)
    error: str | None = None


def _is_winner(prize_amount) -> bool:
    """奖金为 None（浮动奖）或 >0 均视为中奖."""
    return prize_amount is None or prize_amount > 0


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


def _build_engine(profile_key: str) -> GenerationEngine:
    """根据彩种构造并注册好全部策略的 GenerationEngine。"""
    engine = GenerationEngine()
    if profile_key == "ssq":
        engine.register(RandomStrategy())
        engine.register(OddEvenStrategy())
        engine.register(HotColdStrategy())
        engine.register(ExcludeIncludeStrategy())
        engine.register(SmartHotColdStrategy())
        engine.register(MissingNumberStrategy())
        engine.register(BalancedStrategy())
        engine.register(XGBoostStrategy())
        engine.register(LightGBMStrategy())
        engine.register(CatBoostStrategy())
    else:
        profile = get_profile(profile_key)
        for strategy in build_strategies(profile):
            engine.register(strategy)
    return engine


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
        engine = _build_engine(context.profile_key)

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
            hits: dict[str, int] = {}
            for g in profile.groups:
                actual_nums = task.actual.groups.get(g.key, [])
                predicted_nums = ticket.groups.get(g.key, [])
                if g.positional:
                    hits[g.key] = sum(
                        1 for a, p in zip(actual_nums, predicted_nums) if a == p
                    )
                elif g.draw_only:
                    ticket_numbers: set[int] = set()
                    for pg in profile.pick_groups:
                        ticket_numbers.update(ticket.groups.get(pg.key, []))
                    hits[g.key] = len(set(actual_nums) & ticket_numbers)
                else:
                    hits[g.key] = len(set(actual_nums) & set(predicted_nums))

            prize_name, prize_amount = calculate_prize(
                profile.key, hits, ticket.groups, task.actual.groups
            )

            total_cost += 2
            is_winner = _is_winner(prize_amount)
            ticket_results.append({
                "round": task.index,
                "ticket_index": t_idx,
                "hits": hits,
                "prize_name": prize_name,
                "prize_amount": prize_amount,
            })

            if prize_amount is not None:
                total_fixed_prize += prize_amount
                if is_winner:
                    hit_count += 1
            else:
                float_prize_count += 1
                hit_count += 1

            if is_winner:
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
