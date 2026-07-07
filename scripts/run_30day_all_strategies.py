"""对指定彩种执行最近30天（期）的策略历史回测.

用法:
    python scripts/run_30day_all_strategies.py <profile_key> [--skip-ml] [rounds] [tickets_per_round]

示例:
    python scripts/run_30day_all_strategies.py ssq
    python scripts/run_30day_all_strategies.py ssq --skip-ml 30 1
    python scripts/run_30day_all_strategies.py 3d
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from caipiao.core.engine import GenerationEngine
from caipiao.core.prize import calculate_prize
from caipiao.core.profile import PROFILES, get_profile
from caipiao.core.strategies.generic import build_strategies, is_ml_strategy, needs_history
from caipiao.data.repository import DrawRepository


def _register_all_strategies(engine: GenerationEngine, profile) -> None:
    """注册该彩种全部可用策略."""
    for strategy in build_strategies(profile):
        engine.register(strategy)

    # 双色球/大乐透在 generic.build_strategies 之外还有 legacy 策略
    if profile.key == "ssq":
        from caipiao.core.strategies import (
            BalancedStrategy,
            BayesianStrategy,
            MarkovChainStrategy,
            MLStrategy,
            OddEvenStrategy,
            RandomStrategy,
        )
        engine.register(RandomStrategy())
        engine.register(OddEvenStrategy())
        engine.register(BalancedStrategy())
        engine.register(BayesianStrategy())
        engine.register(MarkovChainStrategy())
        engine.register(MLStrategy("xgboost"))


def _run_backtest(
    profile_key: str,
    rounds: int = 30,
    tickets_per_round: int = 5,
    skip_ml: bool = False,
) -> None:
    profile = get_profile(profile_key)
    repo = DrawRepository(f".caipiao/{profile.storage_file}", profile=profile)
    records = repo.get_all()
    if len(records) < rounds + 20:
        print(f"数据不足: {profile.name} 只有 {len(records)} 期记录")
        return

    engine = GenerationEngine()
    _register_all_strategies(engine, profile)

    target_records = records[-rounds:]

    ml_note = "（不含 ML 策略）" if skip_ml else "（含 ML 策略）"
    print(f"\n=== {profile.name}（{profile_key}）最近 {rounds} 期策略回测 {ml_note} ===")
    print(f"回测期号范围: {target_records[0].issue} ~ {target_records[-1].issue}")
    print(f"每策略每期生成 {tickets_per_round} 注\n")

    strategy_ids = [s.metadata.id for s in engine.list_strategies()]
    if skip_ml:
        strategy_ids = [sid for sid in strategy_ids if not is_ml_strategy(sid)]

    for strategy_id in strategy_ids:
        strategy = engine.get(strategy_id)
        if strategy is None:
            continue

        total_cost = 0
        total_fixed_prize = 0
        float_prize_count = 0
        hit_count = 0
        round_results = []

        for actual in target_records:
            history = [r for r in records if r.draw_date < actual.draw_date]
            if needs_history(strategy_id) and len(history) < 20:
                continue

            options = {}
            if needs_history(strategy_id):
                options["history"] = history

            try:
                tickets = engine.generate(strategy_id, count=tickets_per_round, options=options)
            except Exception as exc:
                round_results.append((actual.issue, f"生成失败: {exc}"))
                continue

            for ticket in tickets:
                total_cost += 2
                hits = {}
                for g in profile.groups:
                    actual_nums = actual.groups.get(g.key, [])
                    predicted_nums = ticket.groups.get(g.key, [])
                    if g.positional:
                        hits[g.key] = sum(1 for a, p in zip(actual_nums, predicted_nums) if a == p)
                    elif g.draw_only:
                        ticket_numbers = set()
                        for pg in profile.pick_groups:
                            ticket_numbers.update(ticket.groups.get(pg.key, []))
                        hits[g.key] = len(set(actual_nums) & ticket_numbers)
                    else:
                        hits[g.key] = len(set(actual_nums) & set(predicted_nums))

                prize_name, prize_amount = calculate_prize(profile.key, hits, ticket.groups, actual.groups)
                if prize_amount is None:
                    float_prize_count += 1
                    hit_count += 1
                elif prize_amount > 0:
                    total_fixed_prize += prize_amount
                    hit_count += 1

                round_results.append((actual.issue, prize_name, prize_amount))

        profit = total_fixed_prize - total_cost
        print(f"策略: {strategy_id}")
        print(f"  总花费: {total_cost} 元, 固定奖金: {total_fixed_prize} 元, 盈亏: {profit} 元")
        print(f"  中奖次数: {hit_count}, 浮动奖次数: {float_prize_count}")
        if round_results and isinstance(round_results[-1], tuple) and len(round_results[-1]) == 2:
            errors = [r for r in round_results if isinstance(r, tuple) and len(r) == 2]
            if errors:
                print(f"  生成失败期数: {len(errors)} (示例: {errors[0][1]})")
        print()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="对指定彩种执行最近多期的策略历史回测")
    parser.add_argument("profile_key", choices=list(PROFILES.keys()), help="彩种 key")
    parser.add_argument("--skip-ml", action="store_true", help="跳过需要训练模型的 ML 策略")
    parser.add_argument("rounds", nargs="?", type=int, default=30, help="回测期数（默认 30）")
    parser.add_argument("tickets", nargs="?", type=int, default=5, help="每期生成注数（默认 5）")
    args = parser.parse_args(argv[1:])
    _run_backtest(args.profile_key, rounds=args.rounds, tickets_per_round=args.tickets, skip_ml=args.skip_ml)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
