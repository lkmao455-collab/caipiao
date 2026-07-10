"""调试遗漏号追踪策略."""

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


def make_cold_history(n=1000, cold_digit=0, seed=42):
    """创建冷号数据."""
    random.seed(seed)
    records = []
    
    for i in range(n):
        pos = []
        for p in range(3):
            if p == 0:
                # 位置0：冷号出现次数极少
                if random.random() < 0.02:  # 2%概率选冷号
                    digit = cold_digit
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


def debug_strategy():
    """调试策略."""
    print("=" * 80)
    print("调试遗漏号追踪策略")
    print("=" * 80)
    
    records = make_cold_history(1000, cold_digit=0, seed=42)
    strategy = FC3DMissingNumberStrategy()
    
    # 检查χ²检验结果
    pos_freq = positional_frequency(records, 1000)
    print("\nχ²检验结果:")
    uniform_flags = []
    for pos in range(3):
        counts = [pos_freq[pos].get(d, 0) for d in range(10)]
        chi2, is_uniform = chi_square_uniform_test(counts)
        print(f"  位置{pos}: χ²={chi2:.2f}, 均匀={is_uniform}")
        uniform_flags.append(is_uniform)
    
    print(f"\nuniform_flags: {uniform_flags}")
    print(f"all_uniform: {all(uniform_flags)}")
    
    # 计算z-score
    raw_missing = raw_missing_periods(records, 1000)
    geo_z = geometric_missing_zscore(raw_missing)
    
    print("\n位置0的z-score:")
    for d in range(10):
        print(f"  数字{d}: z={geo_z[0][d]:.3f}")
    
    # 模拟策略逻辑
    z_threshold = 1.96
    significant_cold = []
    
    for pos in range(3):
        if uniform_flags[pos]:
            # 数据均匀：无显著冷号
            cold_digits = []
        else:
            # 数据不均匀：找出z-score超过阈值的显著偏冷号码
            cold_digits = [
                d for d in DIGIT_POOL
                if geo_z[pos][d] > z_threshold
            ]
        significant_cold.append(cold_digits)
        print(f"\n位置{pos}: uniform={uniform_flags[pos]}, cold_digits={cold_digits}")
    
    total_significant = sum(len(cold) for cold in significant_cold)
    print(f"\nsignificant_cold: {significant_cold}")
    print(f"total_significant: {total_significant}")
    
    # 测试策略
    options = {
        "history": records,
        "lookback": 1000,
        "z_threshold": 196,
        "temperature": 5,
    }
    
    tickets = strategy.generate(count=1, options=options)
    basis = tickets[0].basis
    
    print(f"\n策略说明:")
    print(basis)
    
    # 检查是否包含"统计显著偏冷号码"
    if "统计显著偏冷号码" in basis:
        print(f"\n✓ 策略说明中包含'统计显著偏冷号码'")
    else:
        print(f"\n✗ 策略说明中不包含'统计显著偏冷号码'")


if __name__ == "__main__":
    debug_strategy()
