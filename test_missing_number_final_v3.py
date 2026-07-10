"""测试遗漏号追踪策略改进效果 - 最终版v3."""

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


def make_uniform_history(n=1000, seed=42):
    """创建均匀分布数据."""
    random.seed(seed)
    records = []
    
    for i in range(n):
        pos = [random.randint(0, 9) for _ in range(3)]
        records.append(
            DrawRecord(
                f"2024{i:03d}",
                datetime(2024, 1, 1) + timedelta(days=i),
                profile="3d",
                groups={"pos": pos},
            )
        )
    
    return records


def make_cold_history_v2(n=1000, cold_digit=0, seed=42):
    """创建冷号数据 - 确保χ²检验显示数据不均匀."""
    random.seed(seed)
    records = []
    
    for i in range(n):
        pos = []
        for p in range(3):
            if p == 0:
                # 位置0：冷号出现次数极少，热号出现次数极多
                if random.random() < 0.01:  # 1%概率选冷号
                    digit = cold_digit
                elif random.random() < 0.3:  # 30%概率选热号
                    digit = 5
                else:
                    digit = random.randint(0, 9)
            else:
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


def test_uniform_data():
    """测试均匀数据."""
    print("=" * 80)
    print("测试均匀数据")
    print("=" * 80)
    
    records = make_uniform_history(1000, seed=42)
    strategy = FC3DMissingNumberStrategy()
    
    # 检查χ²检验结果
    pos_freq = positional_frequency(records, 1000)
    print("\nχ²检验结果:")
    uniform_count = 0
    for pos in range(3):
        counts = [pos_freq[pos].get(d, 0) for d in range(10)]
        chi2, is_uniform = chi_square_uniform_test(counts)
        print(f"  位置{pos}: χ²={chi2:.2f}, 均匀={is_uniform}")
        if is_uniform:
            uniform_count += 1
    
    print(f"\n均匀位置数量: {uniform_count}/3")
    
    # 测试策略
    options = {
        "history": records,
        "lookback": 1000,
        "z_threshold": 196,
        "temperature": 5,
    }
    
    tickets = strategy.generate(count=10, options=options)
    
    # 分析结果
    all_digits = []
    for ticket in tickets:
        all_digits.extend(ticket.groups["pos"])
    
    digit_counts = Counter(all_digits)
    total = len(all_digits)
    
    print(f"\n生成号码数量: {len(tickets)}")
    print(f"数字分布: {dict(sorted(digit_counts.items()))}")
    
    # 计算每个数字的频率
    for d in range(10):
        freq = digit_counts.get(d, 0) / total
        print(f"  数字{d}: {freq:.3f} ({digit_counts.get(d, 0)}/{total})")
    
    # 检查策略说明
    basis = tickets[0].basis
    if "退化为均匀随机" in basis:
        print(f"\n✓ 策略正确退化为均匀随机")
    else:
        print(f"\n✗ 策略未正确处理均匀数据")
        print(f"说明: {basis[:200]}...")


def test_cold_data():
    """测试冷号数据."""
    print("\n" + "=" * 80)
    print("测试冷号数据")
    print("=" * 80)
    
    records = make_cold_history_v2(1000, cold_digit=0, seed=42)
    strategy = FC3DMissingNumberStrategy()
    
    # 检查χ²检验结果
    pos_freq = positional_frequency(records, 1000)
    print("\nχ²检验结果:")
    uniform_count = 0
    for pos in range(3):
        counts = [pos_freq[pos].get(d, 0) for d in range(10)]
        chi2, is_uniform = chi_square_uniform_test(counts)
        print(f"  位置{pos}: χ²={chi2:.2f}, 均匀={is_uniform}")
        if is_uniform:
            uniform_count += 1
    
    print(f"\n均匀位置数量: {uniform_count}/3")
    
    # 计算z-score
    raw_missing = raw_missing_periods(records, 1000)
    geo_z = geometric_missing_zscore(raw_missing)
    
    print("\n位置0的z-score:")
    for d in range(10):
        print(f"  数字{d}: z={geo_z[0][d]:.3f}")
    
    # 测试策略
    options = {
        "history": records,
        "lookback": 1000,
        "z_threshold": 196,
        "temperature": 5,
    }
    
    tickets = strategy.generate(count=10, options=options)
    
    # 分析结果
    all_digits = []
    for ticket in tickets:
        all_digits.extend(ticket.groups["pos"])
    
    digit_counts = Counter(all_digits)
    total = len(all_digits)
    
    print(f"\n生成号码数量: {len(tickets)}")
    print(f"数字分布: {dict(sorted(digit_counts.items()))}")
    
    # 计算每个数字的频率
    for d in range(10):
        freq = digit_counts.get(d, 0) / total
        print(f"  数字{d}: {freq:.3f} ({digit_counts.get(d, 0)}/{total})")
    
    # 检查冷号频率
    cold_freq = digit_counts.get(0, 0) / total
    print(f"\n冷号(0)频率: {cold_freq:.3f}")
    
    # 检查策略说明
    basis = tickets[0].basis
    if "统计显著偏冷号码" in basis and "无统计显著偏冷号码" not in basis:
        print(f"✓ 策略检测到显著冷号")
    else:
        print(f"✗ 策略未检测到显著冷号")
        print(f"说明: {basis[:200]}...")


def test_false_positive_rate():
    """测试假阳性率."""
    print("\n" + "=" * 80)
    print("测试假阳性率")
    print("=" * 80)
    
    # 使用不同的种子创建多个均匀数据集
    false_positives = 0
    total_tests = 10
    
    for i in range(total_tests):
        records = make_uniform_history(1000, seed=i*100)
        strategy = FC3DMissingNumberStrategy()
        
        options = {
            "history": records,
            "lookback": 1000,
            "z_threshold": 196,
            "temperature": 5,
        }
        
        tickets = strategy.generate(count=5, options=options)
        basis = tickets[0].basis
        
        # 检查是否错误地检测到显著冷号
        if "统计显著偏冷号码" in basis and "无统计显著偏冷号码" not in basis:
            false_positives += 1
            print(f"  测试{i+1}: 检测到显著冷号 (假阳性)")
        else:
            print(f"  测试{i+1}: 未检测到显著冷号 (正确)")
    
    false_positive_rate = false_positives / total_tests
    
    print(f"\n假阳性次数: {false_positives}/{total_tests}")
    print(f"假阳性率: {false_positive_rate:.1%}")
    
    if false_positive_rate < 0.1:  # 10%阈值
        print(f"✓ 假阳性率可接受 (<10%)")
    else:
        print(f"✗ 假阳性率过高 (>=10%)")


def test_statistical_power():
    """测试统计功效."""
    print("\n" + "=" * 80)
    print("测试统计功效")
    print("=" * 80)
    
    # 使用不同的种子创建多个冷号数据集
    true_positives = 0
    total_tests = 10
    
    for i in range(total_tests):
        records = make_cold_history_v2(1000, cold_digit=0, seed=i*100)
        strategy = FC3DMissingNumberStrategy()
        
        options = {
            "history": records,
            "lookback": 1000,
            "z_threshold": 196,
            "temperature": 5,
        }
        
        tickets = strategy.generate(count=5, options=options)
        basis = tickets[0].basis
        
        # 检查是否正确检测到显著冷号
        if "统计显著偏冷号码" in basis and "无统计显著偏冷号码" not in basis and "0" in basis:
            true_positives += 1
            print(f"  测试{i+1}: 检测到冷号0 (正确)")
        else:
            print(f"  测试{i+1}: 未检测到冷号0 (假阴性)")
    
    true_positive_rate = true_positives / total_tests
    
    print(f"\n真阳性次数: {true_positives}/{total_tests}")
    print(f"真阳性率: {true_positive_rate:.1%}")
    
    if true_positive_rate > 0.8:  # 80%阈值
        print(f"✓ 统计功效可接受 (>80%)")
    else:
        print(f"✗ 统计功效不足 (<=80%)")


if __name__ == "__main__":
    test_uniform_data()
    test_cold_data()
    test_false_positive_rate()
    test_statistical_power()
    
    print("\n" + "=" * 80)
    print("测试完成!")
    print("=" * 80)
