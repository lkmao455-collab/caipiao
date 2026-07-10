"""测试遗漏号追踪策略改进效果 - 最终版."""

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


def make_controlled_history(n=100, cold_digit=0, hot_digit=5):
    """创建受控的测试数据，确保统计显著性."""
    random.seed(42)
    records = []
    
    for i in range(n):
        # 生成3个数字
        pos = []
        for p in range(3):
            if p == 0:
                # 位置0：冷号出现次数极少，热号出现次数极多
                if i < 10:  # 前10期：冷号出现1次
                    digit = cold_digit
                elif i < 20:  # 10-20期：热号出现多次
                    digit = hot_digit
                else:
                    # 其他数字随机出现
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


def test_statistical_power():
    """测试统计功效：策略是否能检测到真正的冷号."""
    print("=" * 80)
    print("测试统计功效：策略是否能检测到真正的冷号")
    print("=" * 80)
    
    # 创建包含真正冷号的数据
    records = make_controlled_history(100, cold_digit=0, hot_digit=5)
    strategy = FC3DMissingNumberStrategy()
    
    # 测试不同z_threshold
    z_thresholds = [150, 196, 258, 300]
    
    for z_thresh in z_thresholds:
        options = {
            "history": records,
            "lookback": 100,
            "z_threshold": z_thresh,
            "temperature": 5,
        }
        
        tickets = strategy.generate(count=10, options=options)
        
        # 分析结果
        all_digits = []
        for ticket in tickets:
            all_digits.extend(ticket.groups["pos"])
        
        digit_counts = Counter(all_digits)
        total = len(all_digits)
        
        # 检查冷号(0)的频率
        cold_freq = digit_counts.get(0, 0) / total
        hot_freq = digit_counts.get(5, 0) / total
        
        print(f"\nz_threshold={z_thresh/100:.2f}:")
        print(f"  冷号(0)频率: {cold_freq:.3f}")
        print(f"  热号(5)频率: {hot_freq:.3f}")
        print(f"  冷/热比: {cold_freq/hot_freq:.2f}" if hot_freq > 0 else "  冷/热比: N/A")
        
        # 检查策略是否检测到显著冷号
        basis = tickets[0].basis
        if "0" in basis and "统计显著偏冷号码" in basis:
            print(f"  ✓ 策略检测到冷号0")
        else:
            print(f"  ✗ 策略未检测到冷号0")


def test_false_positive_rate():
    """测试假阳性率：在均匀数据下策略是否错误地检测到冷号."""
    print("\n" + "=" * 80)
    print("测试假阳性率：在均匀数据下策略是否错误地检测到冷号")
    print("=" * 80)
    
    # 创建均匀分布的数据
    random.seed(123)
    uniform_records = []
    for i in range(200):
        pos = [random.randint(0, 9) for _ in range(3)]
        uniform_records.append(
            DrawRecord(
                f"2024{i:03d}",
                datetime(2024, 1, 1) + timedelta(days=i),
                profile="3d",
                groups={"pos": pos},
            )
        )
    
    strategy = FC3DMissingNumberStrategy()
    
    # 测试不同z_threshold
    z_thresholds = [150, 196, 258, 300]
    
    for z_thresh in z_thresholds:
        options = {
            "history": uniform_records,
            "lookback": 100,
            "z_threshold": z_thresh,
            "temperature": 5,
        }
        
        # 多次运行测试假阳性
        false_positives = 0
        total_tests = 10
        
        for _ in range(total_tests):
            tickets = strategy.generate(count=5, options=options)
            basis = tickets[0].basis
            
            # 检查是否错误地检测到显著冷号
            if "统计显著偏冷号码" in basis:
                false_positives += 1
        
        false_positive_rate = false_positives / total_tests
        
        print(f"\nz_threshold={z_thresh/100:.2f}:")
        print(f"  假阳性次数: {false_positives}/{total_tests}")
        print(f"  假阳性率: {false_positive_rate:.1%}")
        
        # 期望假阳性率 < 5% (因为z>1.96对应5%显著性水平)
        if z_thresh == 196:
            if false_positive_rate < 0.1:  # 放宽到10%
                print(f"  ✓ 假阳性率可接受 (<10%)")
            else:
                print(f"  ✗ 假阳性率过高 (>=10%)")


def test_temperature_effect():
    """测试温度参数对策略的影响."""
    print("\n" + "=" * 80)
    print("测试温度参数对策略的影响")
    print("=" * 80)
    
    records = make_controlled_history(100, cold_digit=0, hot_digit=5)
    strategy = FC3DMissingNumberStrategy()
    
    # 测试不同温度
    temperatures = [1, 3, 5, 10, 20]
    
    print(f"\n{'温度':>4} | {'冷号频率':>8} | {'热号频率':>8} | {'冷/热比':>8} | {'分布熵':>8}")
    print("-" * 50)
    
    for temp in temperatures:
        options = {
            "history": records,
            "lookback": 100,
            "z_threshold": 196,
            "temperature": temp,
        }
        
        tickets = strategy.generate(count=100, options=options)
        
        # 分析结果
        all_digits = []
        for ticket in tickets:
            all_digits.extend(ticket.groups["pos"])
        
        digit_counts = Counter(all_digits)
        total = len(all_digits)
        
        # 计算冷号和热号频率
        cold_freq = digit_counts.get(0, 0) / total
        hot_freq = digit_counts.get(5, 0) / total
        ratio = cold_freq / hot_freq if hot_freq > 0 else float('inf')
        
        # 计算分布熵
        probs = [digit_counts.get(d, 0) / total for d in range(10)]
        entropy = -sum(p * math.log2(p) for p in probs if p > 0)
        
        print(f"{temp:4d} | {cold_freq:8.3f} | {hot_freq:8.3f} | {ratio:8.2f} | {entropy:8.3f}")


def test_z_threshold_effect():
    """测试z_threshold参数对策略的影响."""
    print("\n" + "=" * 80)
    print("测试z_threshold参数对策略的影响")
    print("=" * 80)
    
    records = make_controlled_history(100, cold_digit=0, hot_digit=5)
    strategy = FC3DMissingNumberStrategy()
    
    # 测试不同z_threshold
    z_thresholds = [150, 196, 258, 300]
    
    print(f"\n{'z阈值':>6} | {'冷号频率':>8} | {'热号频率':>8} | {'冷/热比':>8} | {'分布熵':>8}")
    print("-" * 55)
    
    for z_thresh in z_thresholds:
        options = {
            "history": records,
            "lookback": 100,
            "z_threshold": z_thresh,
            "temperature": 5,
        }
        
        tickets = strategy.generate(count=100, options=options)
        
        # 分析结果
        all_digits = []
        for ticket in tickets:
            all_digits.extend(ticket.groups["pos"])
        
        digit_counts = Counter(all_digits)
        total = len(all_digits)
        
        # 计算冷号和热号频率
        cold_freq = digit_counts.get(0, 0) / total
        hot_freq = digit_counts.get(5, 0) / total
        ratio = cold_freq / hot_freq if hot_freq > 0 else float('inf')
        
        # 计算分布熵
        probs = [digit_counts.get(d, 0) / total for d in range(10)]
        entropy = -sum(p * math.log2(p) for p in probs if p > 0)
        
        print(f"{z_thresh/100:6.2f} | {cold_freq:8.3f} | {hot_freq:8.3f} | {ratio:8.2f} | {entropy:8.3f}")


def test_basis_explanation_quality():
    """测试策略说明文本的质量."""
    print("\n" + "=" * 80)
    print("测试策略说明文本的质量")
    print("=" * 80)
    
    records = make_controlled_history(100, cold_digit=0, hot_digit=5)
    strategy = FC3DMissingNumberStrategy()
    
    # 测试不同场景
    test_cases = [
        {"name": "均匀数据", "records": make_controlled_history(100)},
        {"name": "冷号数据", "records": records},
    ]
    
    for case in test_cases:
        print(f"\n场景: {case['name']}")
        tickets = strategy.generate(count=1, options={
            "history": case['records'],
            "lookback": 100,
            "z_threshold": 196,
            "temperature": 5,
        })
        
        basis = tickets[0].basis
        
        # 检查说明文本是否包含必要信息
        checks = {
            "包含策略名称": "遗漏号追踪策略" in basis,
            "包含z阈值": "z阈值=" in basis,
            "包含χ²检验结果": "χ²检验" in basis,
            "包含数学说明": "几何分布" in basis,
            "包含风险提示": "不能预测独立随机开奖" in basis,
        }
        
        print(f"  说明文本质量检查:")
        for check, passed in checks.items():
            status = "✓" if passed else "✗"
            print(f"    {status} {check}")
        
        # 显示部分说明文本
        print(f"  说明文本前200字符: {basis[:200]}...")


def test_consistency():
    """测试策略的一致性：相同输入是否产生相同输出."""
    print("\n" + "=" * 80)
    print("测试策略的一致性：相同输入是否产生相同输出")
    print("=" * 80)
    
    records = make_controlled_history(100, cold_digit=0, hot_digit=5)
    strategy = FC3DMissingNumberStrategy()
    
    options = {
        "history": records,
        "lookback": 100,
        "z_threshold": 196,
        "temperature": 5,
        "seed": 42,
    }
    
    # 多次运行相同输入
    results = []
    for i in range(5):
        tickets = strategy.generate(count=3, options=options)
        result = [tuple(ticket.groups["pos"]) for ticket in tickets]
        results.append(result)
    
    # 检查一致性
    all_same = all(r == results[0] for r in results)
    
    print(f"\n相同输入运行5次:")
    print(f"  结果一致: {all_same}")
    
    if all_same:
        print(f"  ✓ 策略具有确定性（相同种子产生相同结果）")
    else:
        print(f"  ✗ 策略不具有确定性")
    
    # 显示结果
    for i, result in enumerate(results):
        print(f"  运行{i+1}: {result}")


def test_mathematical_correctness():
    """测试数学正确性：验证z-score计算和概率分布."""
    print("\n" + "=" * 80)
    print("测试数学正确性：验证z-score计算和概率分布")
    print("=" * 80)
    
    records = make_controlled_history(100, cold_digit=0, hot_digit=5)
    
    # 计算原始遗漏值
    raw_missing = raw_missing_periods(records, 100)
    geo_z = geometric_missing_zscore(raw_missing)
    
    print("\n位置0的z-score:")
    for d in range(10):
        print(f"  数字{d}: z={geo_z[0][d]:.3f}")
    
    # 验证z-score计算
    expected = 9.0  # Geom(0.1)的期望
    sigma = math.sqrt(0.9) / 0.1  # ≈9.49
    
    print(f"\n理论值:")
    print(f"  期望遗漏期数: {expected}")
    print(f"  标准差: {sigma:.2f}")
    
    # 验证冷号0的z-score
    cold_missing = raw_missing[0][0]  # 数字0的遗漏期数
    cold_z = (cold_missing - expected) / sigma
    print(f"\n冷号0:")
    print(f"  遗漏期数: {cold_missing}")
    print(f"  计算z-score: {cold_z:.3f}")
    print(f"  代码计算z-score: {geo_z[0][0]:.3f}")
    print(f"  一致性: {abs(cold_z - geo_z[0][0]) < 0.001}")
    
    # 验证softmax概率分布
    logits = [geo_z[0][d] for d in range(10)]
    probs = softmax_scores(logits, temperature=1.0)
    
    print(f"\nsoftmax概率分布:")
    print(f"  概率和: {sum(probs):.6f} (应为1.0)")
    print(f"  所有概率非负: {all(p >= 0 for p in probs)}")
    print(f"  最大概率: {max(probs):.4f} (数字{probs.index(max(probs))})")
    print(f"  最小概率: {min(probs):.4f} (数字{probs.index(min(probs))})")


if __name__ == "__main__":
    test_statistical_power()
    test_false_positive_rate()
    test_temperature_effect()
    test_z_threshold_effect()
    test_basis_explanation_quality()
    test_consistency()
    test_mathematical_correctness()
    
    print("\n" + "=" * 80)
    print("所有测试完成!")
    print("=" * 80)
