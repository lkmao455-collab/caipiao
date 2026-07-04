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
from pathlib import Path
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
from caipiao.ml.catboost_model import LotteryCatBoostModel
from caipiao.ml.generic_predictor import GenericMLPredictor
from caipiao.ml.lgbm_model import LotteryLightGBMModel
from caipiao.ml.model import LotteryXGBoostModel
from caipiao.ml.model_store import compute_lookback, new_model_path
from caipiao.ml.predictor import MLPredictor
from caipiao.ui.batch_backtest_result import BatchBacktestResult


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
    plugin_dir: str | None = None


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
    first_ticket_hit_count: int = 0
    winners: list[int] = field(default_factory=list)
    ticket_results: list[dict] = field(default_factory=list)
    ticket_index_hits: dict[int, int] = field(default_factory=dict)
    # 以下字段用于在主线程还原旧版 round_ready 信号所需的详情字典
    date_str: str = ""
    issue_str: str = ""
    actual_groups: dict = field(default_factory=dict)
    tickets: list = field(default_factory=list)
    error: str | None = None


def _is_winner(prize_amount) -> bool:
    """奖金为 None（浮动奖）或 >0 均视为中奖."""
    return prize_amount is None or prize_amount > 0


def _ticket_is_first(ticket_index: int) -> bool:
    """判断是否为第一注."""
    return ticket_index == 0


def _get_worker_temp_dir() -> str:
    pid = os.getpid()
    base = os.path.join(".caipiao", "tmp", "backtest_workers")
    path = os.path.join(base, f"worker_{pid}")
    os.makedirs(path, exist_ok=True)
    return path


def _cleanup_worker_temp_dir():
    shutil.rmtree(_get_worker_temp_dir(), ignore_errors=True)


def _configure_worker_threads():
    # 强制单线程，避免子进程内 OpenMP/MKL 等线程池爆炸。
    # 使用直接赋值而非 setdefault，确保父进程已设置的环境变量也被覆盖。
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
    os.environ["NUMEXPR_NUM_THREADS"] = "1"


def _build_engine(profile_key: str, plugin_dir: str | None = None) -> GenerationEngine:
    """根据彩种构造并注册好全部策略的 GenerationEngine。

    若提供了 ``plugin_dir``，worker 会重新加载该目录下的策略插件，
    保证批量回测在子进程中也能使用用户自定义的插件策略。
    """
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

    if plugin_dir:
        from caipiao.plugins import PluginManager

        pm = PluginManager(engine, plugin_dir)
        pm.load_all()

    return engine


def prepare_ml_options(
    history: list,
    options: dict,
    profile_key: str,
    draw_date,
    temp_dir: str,
) -> dict:
    """基于历史数据为 ML 策略训练临时模型，并返回（可能已更新的）options。

    此函数为纯函数：不依赖 ``self``、Qt 对象或闭包，输入/输出均可被 pickle
    序列化，可在子进程中执行。``temp_dir`` 会透传给底层训练器，作为 CatBoost
    的 ``train_dir`` 以及各后端线程隔离的临时根目录。
    """
    strategy_id = options.get("strategy_id")
    if not strategy_id:
        return dict(options)

    result = dict(options)
    lookback = compute_lookback(len(history))

    # 影响模型路径/缓存命名的参数来自用户原始选项，排除运行时注入的字段。
    path_options = {
        k: v for k, v in options.items() if k not in ("history", "strategy_id")
    }

    if profile_key == "ssq":
        if strategy_id.startswith("lightgbm"):
            model_class = LotteryLightGBMModel
            prefix = "lightgbm"
        elif strategy_id.startswith("catboost"):
            model_class = LotteryCatBoostModel
            prefix = "catboost"
        else:
            model_class = LotteryXGBoostModel
            prefix = "xgboost"

        model_path = new_model_path(
            history,
            lookback,
            prefix=prefix,
            options=path_options,
        )
        predictor = MLPredictor(
            history,
            lookback=lookback,
            model_path=model_path,
            model_class=model_class,
            temp_dir=temp_dir,
        )
        predictor.train()
        return result

    if strategy_id.startswith("lightgbm"):
        backend = "lightgbm"
    elif strategy_id.startswith("catboost"):
        backend = "catboost"
    else:
        backend = "xgboost"

    profile = get_profile(profile_key)
    prefix = (
        profile.lightgbm_prefix()
        if backend == "lightgbm"
        else profile.catboost_prefix()
        if backend == "catboost"
        else profile.xgboost_prefix()
    )
    model_path = new_model_path(
        history,
        lookback,
        prefix=prefix,
        options=path_options,
    )
    predictor = GenericMLPredictor(
        history,
        profile=profile,
        lookback=lookback,
        model_path=model_path,
        backend=backend,
        temp_dir=temp_dir,
    )
    predictor.train()
    return result


def init_worker_process(seed: int):
    """每个子进程启动时调用。"""
    _configure_worker_threads()
    worker_tmp = _get_worker_temp_dir()
    # 将模型缓存目录重定向到 worker 私有临时目录，避免多进程并发写入冲突。
    os.environ["CAIPIAO_MODEL_DIR"] = worker_tmp
    atexit.register(_cleanup_worker_temp_dir)
    random.seed(seed)
    np.random.seed(seed)


def _detect_ml_strategy(engine: GenerationEngine, strategy_id: str, context_is_ml: bool) -> bool:
    """判断策略是否需要预先训练 ML 模型.

    优先根据策略实例的 ``is_ml`` 属性判断（支持插件 ML 策略），
    同时保留主线程传入的 ``context.is_ml`` 作为兼容兜底。
    """
    if context_is_ml:
        return True
    strategy = engine.get(strategy_id)
    return strategy is not None and getattr(strategy, "is_ml", False)


def worker_round_backtest(context: RoundBacktestContext, task: RoundTask) -> RoundResult:
    """在子进程中执行一期回测。"""
    try:
        random.seed(context.seed + task.index)
        np.random.seed(context.seed + task.index)

        profile = get_profile(context.profile_key)
        engine = _build_engine(context.profile_key, context.plugin_dir)

        history = [r for r in context.records if r.draw_date < task.actual.draw_date]
        if context.needs_history and len(history) < 100:
            return RoundResult(index=task.index, error="history too short")

        options = dict(context.options)
        if context.needs_history:
            options["history"] = history

        if _detect_ml_strategy(engine, context.strategy_id, context.is_ml):
            options["strategy_id"] = context.strategy_id
            options = prepare_ml_options(
                history,
                options,
                context.profile_key,
                task.actual.draw_date,
                _get_worker_temp_dir(),
            )

        tickets = engine.generate(
            context.strategy_id,
            count=context.tickets_per_round,
            options=options,
        )

        date_str = task.actual.draw_date.strftime("%Y-%m-%d")
        issue_str = task.actual.issue or "未知期号"

        total_cost = 0
        hit_count = 0
        total_fixed_prize = 0
        float_prize_count = 0
        first_ticket_hit_count = 0
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
                if _ticket_is_first(t_idx):
                    first_ticket_hit_count += 1

        return RoundResult(
            index=task.index,
            total_cost=total_cost,
            hit_count=hit_count,
            total_fixed_prize=total_fixed_prize,
            float_prize_count=float_prize_count,
            first_ticket_hit_count=first_ticket_hit_count,
            winners=winners,
            ticket_results=ticket_results,
            ticket_index_hits=ticket_index_hits,
            date_str=date_str,
            issue_str=issue_str,
            actual_groups=dict(task.actual.groups),
            tickets=list(tickets),
        )
    except Exception as e:
        return RoundResult(index=task.index, error=repr(e))


def merge_round_results(results: list[RoundResult], total_rounds: int) -> BatchBacktestResult:
    """按 index 排序合并各期结果，保证最终顺序与日期顺序一致."""
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
        merged.first_ticket_hit_count += r.first_ticket_hit_count
        merged.ticket_results.extend(r.ticket_results)
        for k, v in r.ticket_index_hits.items():
            merged.ticket_index_hits[k] = merged.ticket_index_hits.get(k, 0) + v

    return merged
