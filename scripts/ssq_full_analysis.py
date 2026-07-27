"""双色球完整历史分析报告."""

import json
import statistics
from datetime import datetime
from collections import Counter

from caipiao.data.models import DrawRecord
from caipiao.data.analyzer import DrawAnalyzer, LotteryAnalyzer
from caipiao.core.profile import SSQ
from caipiao.core.strategies.lotteries.ssq.balanced import SSQBalancedStrategy
from caipiao.core.strategies.lotteries.ssq.smart_hot_cold import SSQSmartHotColdStrategy
from caipiao.core.strategies.lotteries.ssq.stats import SSQStatsStrategy


def main():
    # Load data
    with open(".caipiao/draws.json", "r", encoding="utf-8") as f:
        raw = json.load(f)

    records = []
    for r in raw:
        records.append(DrawRecord(
            issue=r["issue"],
            draw_date=datetime.fromisoformat(r["draw_date"]),
            red_balls=r["red_balls"],
            blue_ball=r["blue_ball"],
        ))

    analyzer = DrawAnalyzer(records, SSQ)
    la = LotteryAnalyzer(records)

    print("=" * 70)
    print(f"双色球历史数据分析报告 (共 {len(records)} 期)")
    print(f"数据范围: {records[0].draw_date.strftime('%Y-%m-%d')} ~ {records[-1].draw_date.strftime('%Y-%m-%d')}")
    print("=" * 70)

    # 1. 奇偶比分析
    print("\n" + "-" * 40)
    print("一、奇偶比分析")
    print("-" * 40)
    for lookback in [50, 100, 200, 500, len(records)]:
        odd_r, even_r = analyzer.odd_even_ratio(lookback)
        print(f"  最近{lookback:>4d}期: 奇={odd_r:.3f} 偶={even_r:.3f} => 期望奇数={round(6*odd_r)}个")

    # 2. 大小比分析
    print("\n" + "-" * 40)
    print("二、大小比分析 (1-16小 / 17-33大)")
    print("-" * 40)
    for lookback in [50, 100, 200, 500, len(records)]:
        high_r, low_r = analyzer.high_low_ratio(lookback)
        print(f"  最近{lookback:>4d}期: 大={high_r:.3f} 小={low_r:.3f} => 期望大号={round(6*high_r)}个")

    # 3. 和值分析
    print("\n" + "-" * 40)
    print("三、和值分析")
    print("-" * 40)
    for lookback in [100, 500, len(records)]:
        stats = analyzer.sum_statistics(lookback)
        sliced = records[-lookback:]
        all_sums = [sum(r.red_balls) for r in sliced]
        std = statistics.stdev(all_sums) if len(all_sums) > 1 else 0
        print(f"  最近{lookback:>4d}期: 最小={stats['min']:.0f} 最大={stats['max']:.0f} 平均={stats['avg']:.1f} 中位数={stats['median']:.1f} 标准差={std:.1f}")

    # 4. 连号分析
    print("\n" + "-" * 40)
    print("四、连号分析")
    print("-" * 40)
    for lookback in [100, 500]:
        consec = analyzer.consecutive_frequency(lookback)
        consec_dist = analyzer.consecutive_count_distribution(lookback)
        print(f"  最近{lookback:>4d}期: 含连号比例={consec*100:.1f}%")
        for k, v in sorted(consec_dist.items()):
            print(f"    {k}对连号: {v*100:.1f}%")

    # 5. 三区分布
    print("\n" + "-" * 40)
    print("五、三区分布 (1-11 / 12-22 / 23-33)")
    print("-" * 40)
    for lookback in [100, 500, len(records)]:
        zone = analyzer.zone_distribution(lookback)
        print(f"  最近{lookback:>4d}期: 区1={zone['zone1']:.3f} 区2={zone['zone2']:.3f} 区3={zone['zone3']:.3f} => 期望分布={round(6*zone['zone1'])}:{round(6*zone['zone2'])}:{round(6*zone['zone3'])}")

    # 6. 冷热号
    print("\n" + "-" * 40)
    print("六、红球冷热号统计")
    print("-" * 40)
    hot30 = analyzer.hot("red", 10, 30)
    cold30 = analyzer.cold("red", 10, 30)
    print(f"  最近30期 热号TOP10: {hot30}")
    print(f"  最近30期 冷号TOP10: {cold30}")

    hot100 = analyzer.hot("red", 10, 100)
    cold100 = analyzer.cold("red", 10, 100)
    print(f"  最近100期热号TOP10: {hot100}")
    print(f"  最近100期冷号TOP10: {cold100}")

    # 7. 遗漏值
    print("\n" + "-" * 40)
    print("七、红球遗漏值 (最近50期)")
    print("-" * 40)
    missing = analyzer.missing("red", 50)
    for n, m in missing[:10]:
        bar = "#" * m
        print(f"  号码{n:2d}: 已遗漏{m:2d}期 {bar}")

    # 8. 蓝球分析
    print("\n" + "-" * 40)
    print("八、蓝球频率分布 (最近100期)")
    print("-" * 40)
    blue_freq = analyzer.frequency("blue", 100)
    for n in range(1, 17):
        cnt = blue_freq.get(n, 0)
        bar = "#" * (cnt // 2)
        print(f"  {n:2d}: {cnt:3d} {bar}")

    missing_blue = analyzer.missing("blue", 100)
    print(f"\n  蓝球遗漏TOP8: {missing_blue[:8]}")

    # 9. χ² 均匀性检验
    print("\n" + "-" * 40)
    print("九、χ² 均匀性检验")
    print("-" * 40)
    from caipiao.core.strategies.lotteries.ssq.stability import chi_square_uniform_test
    red_counter = {n: 0 for n in range(1, 34)}
    for r in records[-200:]:
        for n in r.red_balls:
            if n in red_counter:
                red_counter[n] += 1
    red_counts = [red_counter[n] for n in range(1, 34)]
    chi2, is_uniform = chi_square_uniform_test(red_counts)
    print(f"  红球(最近200期): χ²={chi2:.2f} {'均匀' if is_uniform else '显著偏离均匀'} (临界值=46.19)")

    blue_counter = {n: 0 for n in range(1, 17)}
    for r in records[-200:]:
        if r.blue_ball in blue_counter:
            blue_counter[r.blue_ball] += 1
    blue_counts = [blue_counter[n] for n in range(1, 17)]
    chi2_b, is_uniform_b = chi_square_uniform_test(blue_counts)
    print(f"  蓝球(最近200期): χ²={chi2_b:.2f} {'均匀' if is_uniform_b else '显著偏离均匀'} (临界值=25.00)")

    # 10. 几何分布z-score分析
    print("\n" + "-" * 40)
    print("十、遗漏值几何分布z-score (最近100期)")
    print("-" * 40)
    missing_reds = la.missing_reds(100)
    p_red = 1.0 / 33.0
    expected_red = (1 - p_red) / p_red
    sigma_red = (1 - p_red) / p_red ** 0.5
    significant = [(n, m, round((m - expected_red) / sigma_red, 2)) for n, m in missing_reds if (m - expected_red) / sigma_red > 1.96]
    print(f"  红球期望遗漏={expected_red:.1f}期, σ={sigma_red:.1f}")
    print(f"  统计显著偏冷(z>1.96): {significant if significant else '无'}")
    print(f"  TOP5高遗漏: {[(n, m, round((m - expected_red) / sigma_red, 2)) for n, m in missing_reds[:5]]}")

    # 11. 策略推荐号码
    print("\n" + "=" * 70)
    print("十一、策略推荐号码")
    print("=" * 70)

    # Balanced strategy
    balanced = SSQBalancedStrategy()
    tickets_b = balanced.generate(count=5, options={"history": records, "seed": 42, "lookback": 200})
    print("\n【历史均衡策略】(lookback=200)")
    for i, t in enumerate(tickets_b, 1):
        reds = t.groups["red"]
        blue = t.groups["blue"][0]
        odd = sum(1 for n in reds if n % 2 == 1)
        high = sum(1 for n in reds if n >= 17)
        total = sum(reds)
        consec = sum(1 for j in range(len(reds)-1) if reds[j]+1 == reds[j+1])
        z1 = sum(1 for n in reds if 1 <= n <= 11)
        z2 = sum(1 for n in reds if 12 <= n <= 22)
        z3 = sum(1 for n in reds if 23 <= n <= 33)
        print(f"  注{i}: 红球={reds} 蓝球={blue:2d} | 奇偶={odd}:{6-odd} 大小={high}:{6-high} 和值={total:3d} 连号={consec} 区间={z1}:{z2}:{z3}")

    # Smart hot cold strategy
    smart = SSQSmartHotColdStrategy()
    tickets_s = smart.generate(count=5, options={"history": records, "lookback": 200})
    print("\n【智能冷热号策略】(lookback=200)")
    for i, t in enumerate(tickets_s, 1):
        reds = t.groups["red"]
        blue = t.groups["blue"][0]
        odd = sum(1 for n in reds if n % 2 == 1)
        high = sum(1 for n in reds if n >= 17)
        total = sum(reds)
        consec = sum(1 for j in range(len(reds)-1) if reds[j]+1 == reds[j+1])
        z1 = sum(1 for n in reds if 1 <= n <= 11)
        z2 = sum(1 for n in reds if 12 <= n <= 22)
        z3 = sum(1 for n in reds if 23 <= n <= 33)
        print(f"  注{i}: 红球={reds} 蓝球={blue:2d} | 奇偶={odd}:{6-odd} 大小={high}:{6-high} 和值={total:3d} 连号={consec} 区间={z1}:{z2}:{z3}")

    # Stats smart mode
    stats_strat = SSQStatsStrategy()
    tickets_st = stats_strat.generate(count=5, options={"history": records, "lookback": 200, "mode": "smart"})
    print("\n【统计分析策略】(smart模式, lookback=200)")
    for i, t in enumerate(tickets_st, 1):
        reds = t.groups["red"]
        blue = t.groups["blue"][0]
        odd = sum(1 for n in reds if n % 2 == 1)
        high = sum(1 for n in reds if n >= 17)
        total = sum(reds)
        consec = sum(1 for j in range(len(reds)-1) if reds[j]+1 == reds[j+1])
        z1 = sum(1 for n in reds if 1 <= n <= 11)
        z2 = sum(1 for n in reds if 12 <= n <= 22)
        z3 = sum(1 for n in reds if 23 <= n <= 33)
        print(f"  注{i}: 红球={reds} 蓝球={blue:2d} | 奇偶={odd}:{6-odd} 大小={high}:{6-high} 和值={total:3d} 连号={consec} 区间={z1}:{z2}:{z3}")

    # 12. 回测验证：用最后20期验证策略命中率
    print("\n" + "=" * 70)
    print("十二、回测验证 (最后20期)")
    print("=" * 70)
    test_periods = 20
    train_end = len(records) - test_periods
    train_records = records[:train_end]
    test_records = records[train_end:]

    strategies = [
        ("历史均衡", SSQBalancedStrategy(), {"history": train_records, "lookback": 200}),
        ("智能冷热号", SSQSmartHotColdStrategy(), {"history": train_records, "lookback": 200}),
        ("统计分析", SSQStatsStrategy(), {"history": train_records, "lookback": 200, "mode": "smart"}),
    ]

    for name, strat, base_opts in strategies:
        red_hit_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}
        blue_hit = 0
        for i, actual in enumerate(test_records):
            opts = {**base_opts, "seed": i + 1}
            ticket = strat.generate(count=1, options=opts)[0]
            predicted_reds = set(ticket.groups["red"])
            actual_reds = set(actual.red_balls)
            hits = len(predicted_reds & actual_reds)
            red_hit_counts[hits] = red_hit_counts.get(hits, 0) + 1
            if ticket.groups["blue"][0] == actual.blue_ball:
                blue_hit += 1

        total_combos = sum(red_hit_counts.values())
        print(f"\n  【{name}】")
        for k in sorted(red_hit_counts.keys()):
            pct = red_hit_counts[k] / total_combos * 100
            bar = "#" * int(pct / 2)
            print(f"    {k}个红球命中: {red_hit_counts[k]:2d}次 ({pct:5.1f}%) {bar}")
        print(f"    蓝球命中: {blue_hit}次 ({blue_hit/total_combos*100:.1f}%)")

    print("\n" + "=" * 70)
    print("声明: 彩票开奖是独立随机事件，历史统计规律不能预测未来开奖。")
    print("本报告所有分析仅作为号码筛选参考，不提供中奖保证。")
    print("=" * 70)


if __name__ == "__main__":
    main()
