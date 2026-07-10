"""测试遗漏号追踪策略改进效果."""

from datetime import datetime, timedelta
import random
import math
from collections import Counter
from caipiao.core.strategies.lotteries.fc3d import FC3DMissingNumberStrategy
from caipiao.core.strategies.lotteries.fc3d.stability import (
    geometric_missing_zscore,
    raw_missing_periods,
    softmax_scores,
    chi_square_uniform_test,
)
from caipiao.core.strategies.lotteries.fc3d.utils import positional_frequency, DIGIT_POOL
from caipiao.data.models import DrawRecord


def make_realistic_history(n=100):
    """创建更真实的测试数据，包含一些统计显著的冷号."""
    random.seed(42)
    records = []
    
    # 创建基础数据：大部分均匀，但某些数字故意减少出现
    cold_digits = {0: 2, 3: 3, 7: 1}  # 位置0的冷号：数字0出现2次，数字3出现3次，数字7出现1次
    
    for i in range(n):
        # 生成3个数字
        pos = []
        for p in range(3):
            if p == 0:
                # 位置0：某些数字出现次数较少
                if random.random() < 0.1:  # 10%概率选择冷号
                    digit = random.choice([0, 3, 7])
                else:
                    digit = random.randint(0, 9)
            else:
                # 其他位置：正常随机
                digit = random.randint(0, 9)
            pos.append(digit)
        
        records.append(
            DrawRecord(
                f"2024{i:03d}",
                datetime(2024, 1, 1) + timedelta(days=i),
                profile="3d",
                groups={"pos": pos},
            )
        )
    
    return records


def test_statistical_significance():
    """测试统计显著性检验."""
    print("=" * 80)
    print("测试统计显著性检验")
    print("=" * 80)
    
    records = make_realistic_history(100)
    strategy = FC3DMissingNumberStrategy()
    
    # 测试不同参数
    test_cases = [
        {"lookback": 100, "z_threshold": 196, "temperature": 5},
        {"lookback": 100, "z_threshold": 150, "temperature": 5},
        {"lookback": 100, "z_threshold": 258, "temperature": 5},
    ]
    
    for i, options in enumerate(test_cases):
        print(f"\n测试用例 {i+1}: z_threshold={options['z_threshold']}")
        
        # 生成号码
        tickets = strategy.generate(count=10, options={"history": records, **options})
        
        # 分析结果
        all_digits = []
        for ticket in tickets:
            all_digits.extend(ticket.groups["pos"])
        
        digit_counts = Counter(all_digits)
        total = len(all_digits)
        
        print(f"  生成号码数量: {len(tickets)}")
        print(f"  数字分布: {dict(sorted(digit_counts.items()))}")
        
        # 计算每个数字的频率
        for d in range(10):
            freq = digit_counts.get(d, 0) / total
            print(f"    数字{d}: {freq:.3f} ({digit_counts.get(d, 0)}/{total})")
        
        # 检查是否偏向冷号
        cold_digits = [0, 3, 7]  # 我们故意减少的数字
        cold_freq = sum(digit_counts.get(d, 0) for d in cold_digits) / total
        print(f"  冷号(0,3,7)总频率: {cold_freq:.3f}")
        
        # 显示策略说明
        basis = tickets[0].basis
        if "统计显著偏冷号码" in basis:
            start = basis.find("统计显著偏冷号码") + len("统计显著偏冷号码(z>")
            end = basis.find(")", start)
            print(f"  策略检测到显著冷号")


def test_probability_distribution():
    """测试概率分布改进."""
    print("\n" + "=" * 80)
    print("测试概率分布改进")
    print("=" * 80)
    
    records = make_realistic_history(100)
    
    # 计算原始遗漏值
    raw_missing = raw_missing_periods(records, 100)
    geo_z = geometric_missing_zscore(raw_missing)
    
    print("\n位置0的z-score:")
    for d in range(10):
        print(f"  数字{d}: z={geo_z[0][d]:.3f}")
    
    # 测试softmax输出
    logits = [geo_z[0][d] for d in range(10)]
    probs_t1 = softmax_scores(logits, temperature=1.0)
    probs_t05 = softmax_scores(logits, temperature=0.5)
    probs_t2 = softmax_scores(logits, temperature=2.0)
    
    print("\n位置0的softmax概率分布:")
    print(f"{'数字':>4} | {'T=1.0':>8} | {'T=0.5':>8} | {'T=2.0':>8}")
    print("-" * 40)
    for d in range(10):
        print(f"{d:4d} | {probs_t1[d]:8.4f} | {probs_t05[d]:8.4f} | {probs_t2[d]:8.4f}")
    
    # 计算分布熵
    def entropy(probs):
        return -sum(p * math.log2(p) for p in probs if p > 0)
    
    max_entropy = math.log2(10)  # 均匀分布的熵
    print(f"\n分布熵 (T=1.0): {entropy(probs_t1):.3f} / {max_entropy:.3f} ({entropy(probs_t1)/max_entropy*100:.1f}%)")
    print(f"分布熵 (T=0.5): {entropy(probs_t05):.3f} / {max_entropy:.3f} ({entropy(probs_t05)/max_entropy*100:.1f}%)")
    print(f"分布熵 (T=2.0): {entropy(probs_t2):.3f} / {max_entropy:.3f} ({entropy(probs_t2)/max_entropy*100:.1f}%)")


def test_chi_square_guard():
    """测试χ²均匀性检验守卫."""
    print("\n" + "=" * 80)
    print("测试χ²均匀性检验守卫")
    print("=" * 80)
    
    # 创建均匀分布的数据
    random.seed(123)
    uniform_records = []
    for i in range(100):
        pos = [random.randint(0, 9) for _ in range(3)]
        uniform_records.append(
            DrawRecord(
                f"2024{i:03d}",
                datetime(2024, 1, 1) + timedelta(days=i),
                profile="3d",
                groups={"pos": pos},
            )
        )
    
    # 创建非均匀分布的数据
    non_uniform_records = []
    for i in range(100):
        # 位置0偏向数字0-2
        if random.random() < 0.5:
            pos0 = random.choice([0, 1, 2])
        else:
            pos0 = random.randint(0, 9)
        pos = [pos0, random.randint(0, 9), random.randint(0, 9)]
        non_uniform_records.append(
            DrawRecord(
                f"2024{i:03d}",
                datetime(2024, 1, 1) + timedelta(days=i),
                profile="3d",
                groups={"pos": pos},
            )
        )
    
    print("\n均匀分布数据:")
    pos_freq = positional_frequency(uniform_records, 100)
    for pos in range(3):
        counts = [pos_freq[pos].get(d, 0) for d in range(10)]
        chi2, is_uniform = chi_square_uniform_test(counts)
        print(f"  位置{pos}: χ²={chi2:.2f}, 均匀={is_uniform}")
    
    print("\n非均匀分布数据:")
    pos_freq = positional_frequency(non_uniform_records, 100)
    for pos in range(3):
        counts = [pos_freq[pos].get(d, 0) for d in range(10)]
        chi2, is_uniform = chi_square_uniform_test(counts)
        print(f"  位置{pos}: χ²={chi2:.2f}, 均匀={is_uniform}")
    
    # 测试策略在不同数据下的行为
    strategy = FC3DMissingNumberStrategy()
    
    print("\n均匀数据下的策略行为:")
    tickets = strategy.generate(count=5, options={"history": uniform_records, "lookback": 100, "z_threshold": 196})
    basis = tickets[0].basis
    if "退化为均匀随机" in basis:
        print("  ✓ 正确退化为均匀随机")
    else:
        print("  ✗ 未正确处理均匀数据")
    
    print("\n非均匀数据下的策略行为:")
    tickets = strategy.generate(count=5, options={"history": non_uniform_records, "lookback": 100, "z_threshold": 196})
    basis = tickets[0].basis
    if "统计显著偏冷号码" in basis:
        print("  ✓ 检测到显著冷号")
    else:
        print("  ✗ 未检测到显著冷号")


def test_parameter_sensitivity():
    """测试参数敏感性."""
    print("\n" + "=" * 80)
    print("测试参数敏感性")
    print("=" * 80)
    
    records = make_realistic_history(100)
    strategy = FC3DMissingNumberStrategy()
    
    # 测试不同温度参数
    print("\n温度参数对概率分布的影响:")
    for temp in [1, 3, 5, 10, 20]:
        options = {
            "history": records,
            "lookback": 100,
            "z_threshold": 196,
            "temperature": temp,
        }
        tickets = strategy.generate(count=100, options=options)
        
        # 统计数字分布
        all_digits = []
        for ticket in tickets:
            all_digits.extend(ticket.groups["pos"])
        
        digit_counts = Counter(all_digits)
        total = len(all_digits)
        
        # 计算最大/最小频率比
        freqs = [digit_counts.get(d, 0) / total for d in range(10)]
        max_freq = max(freqs)
        min_freq = min(freqs)
        ratio = max_freq / min_freq if min_freq > 0 else float('inf')
        
        print(f"  温度={temp:2d}: 最大频率={max_freq:.3f}, 最小频率={min_freq:.3f}, 比值={ratio:.2f}x")


def test_basis_explanation():
    """测试策略说明文本."""
    print("\n" + "=" * 80)
    print("测试策略说明文本")
    print("=" * 80)
    
    records = make_realistic_history(100)
    strategy = FC3DMissingNumberStrategy()
    
    tickets = strategy.generate(count=1, options={"history": records, "lookback": 100, "z_threshold": 196})
    
    print("\n策略说明:")
    print(tickets[0].basis)
    
    print("\n详细信息:")
    details = tickets[0].details
    if "z_scores" in details:
        print(f"  z阈值: {details['z_threshold']}")
        print(f"  位置0的z-score: {details['z_scores'][0]}")


if __name__ == "__main__":
    test_statistical_significance()
    test_probability_distribution()
    test_chi_square_guard()
    test_parameter_sensitivity()
    test_basis_explanation()
    
    print("\n" + "=" * 80)
    print("测试完成!")
    print("=" * 80)
