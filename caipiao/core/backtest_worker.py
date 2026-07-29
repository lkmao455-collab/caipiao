"""批量历史回测核心 worker 函数.

本模块放置在 core 层，供 UI 与策略稳定性验证等 core 模块共享。
所有输入/输出均须可被 pickle 序列化，不得依赖 Qt 对象、数据库连接或文件句柄。
"""

from __future__ import annotations

import os
import random
import shutil
from pathlib import Path

import numpy as np

from caipiao.core.backtest_data import (
    BatchBacktestResult,
    RoundBacktestContext,
    RoundTask,
    RoundResult,
)
from caipiao.core.engine import (
    GenerationEngine,
    apply_dlt_experience_filter,
    apply_fc3d_experience_filter,
    apply_qlc_experience_filter,
    dlt_filtered_gen_count,
    fc3d_filtered_gen_count,
    qlc_filtered_gen_count,
)
from caipiao.core.prize import calculate_prize
from caipiao.core.profile import LotteryProfile, get_profile
from caipiao.core.strategies import build_strategies
from caipiao.ml.catboost_model import LotteryCatBoostModel
from caipiao.ml.common.predictor import BaseMLPredictor as GenericMLPredictor
from caipiao.ml.lgbm_model import LotteryLightGBMModel
from caipiao.ml.common.model_store import compute_lookback, new_model_path
from caipiao.ml.model import LotteryXGBoostModel
from caipiao.ml.predictor import MLPredictor


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

        # 3D/七乐彩 经验策略过滤（跟随主界面设置）：按理论通过率放大候选数量，
        # 生成后与主界面走同一个过滤+截断后处理（3D 还会重分配 bet_mode），
        # 比对用的 history 已限定为目标期之前的记录，无未来函数。
        gen_count = context.tickets_per_round
        fc3d_filter_active = False
        qlc_filter_active = False
        dlt_filter_active = False
        cp = mo = 0
        min_sum = max_sum = 0
        if context.profile_key == "3d" and options.get("_fc3d_filter_enabled") and history:
            cp = int(options.get("_fc3d_filter_compare_periods", 5))
            mo = int(options.get("_fc3d_filter_max_overlap", 1))
            min_sum = int(options.get("_fc3d_filter_min_sum", 0))
            max_sum = int(options.get("_fc3d_filter_max_sum", 27))
            gen_count, _ = fc3d_filtered_gen_count(
                context.tickets_per_round, history, cp, mo, min_sum, max_sum
            )
            fc3d_filter_active = True
        elif context.profile_key == "qlc" and options.get("_qlc_filter_enabled") and history:
            cp = int(options.get("_qlc_filter_compare_periods", 5))
            mo = int(options.get("_qlc_filter_max_overlap", 2))
            min_sum = int(options.get("_qlc_filter_min_sum", 0))
            max_sum = int(options.get("_qlc_filter_max_sum", 210))
            gen_count, _ = qlc_filtered_gen_count(
                context.tickets_per_round, history, cp, mo, min_sum, max_sum
            )
            qlc_filter_active = True
        elif context.profile_key == "dlt" and options.get("_dlt_filter_enabled") and history:
            cp = int(options.get("_dlt_filter_compare_periods", 7))
            mo = int(options.get("_dlt_filter_max_front_overlap", 0))
            min_sum = int(options.get("_dlt_filter_min_front_sum", 15))
            max_sum = int(options.get("_dlt_filter_max_front_sum", 165))
            block_back = bool(options.get("_dlt_filter_block_back", True))
            back_cp = int(options.get("_dlt_filter_back_compare_periods", 1))
            gen_count, _ = dlt_filtered_gen_count(
                context.tickets_per_round, history, cp, mo, min_sum, max_sum
            )
            dlt_filter_active = True

        tickets = engine.generate(
            context.strategy_id,
            count=gen_count,
            options=options,
        )

        if fc3d_filter_active:
            tickets = apply_fc3d_experience_filter(
                tickets, history, context.tickets_per_round, cp, mo,
                min_sum=min_sum, max_sum=max_sum,
            )
        elif qlc_filter_active:
            tickets = apply_qlc_experience_filter(
                tickets, history, context.tickets_per_round, cp, mo,
                min_sum=min_sum, max_sum=max_sum,
            )
        elif dlt_filter_active:
            tickets = apply_dlt_experience_filter(
                tickets, history, context.tickets_per_round, cp, mo,
                min_front_sum=min_sum, max_front_sum=max_sum,
                block_back_match=block_back,
                back_compare_periods=back_cp,
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
                profile.key, hits, ticket.groups, task.actual.groups,
                details=ticket.details,
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
            # 错误期数不影响汇总，但需记录到 errors
            merged.errors.append(r.error)
            continue
        merged.total_cost += r.total_cost
        merged.hit_count += r.hit_count
        merged.total_fixed_prize += r.total_fixed_prize
        merged.float_prize_count += r.float_prize_count
        merged.first_ticket_hit_count += r.first_ticket_hit_count
        merged.ticket_results.extend(r.ticket_results)
        # 还原中奖明细，供结果界面「中奖记录」面板使用（之前合并时仅保留汇总，
        # 导致一键找最优策略/期数扫描完成后详细结果面板为空）。
        for tr in r.ticket_results:
            if not _is_winner(tr["prize_amount"]):
                continue
            t_idx = tr["ticket_index"]
            ticket = r.tickets[t_idx] if 0 <= t_idx < len(r.tickets) else None
            merged.winner_details.append({
                "round": r.index,
                "date": r.date_str,
                "issue": r.issue_str,
                "ticket": ticket,
                "prize_name": tr["prize_name"],
                "prize_amount": tr["prize_amount"],
                "is_first": t_idx == 0,
            })
        for k, v in r.ticket_index_hits.items():
            merged.ticket_index_hits[k] = merged.ticket_index_hits.get(k, 0) + v

    return merged
