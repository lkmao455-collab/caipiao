"""测试福彩3D集成策略."""

from datetime import datetime, timedelta
import random
from caipiao.core.strategies.lotteries.fc3d import FC3DEnsembleStrategy
from caipiao.data.models import DrawRecord


def make_test_history(n=100, seed=42):
    """创建测试历史数据."""
    random.seed(seed)
    records = []
    
    for i in range(n):
        # 生成带有一定规律的号码
        if random.random() < 0.3:
            pos = [random.choice([1, 3, 5, 7, 9]) for _ in range(3)]
        else:
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


def test_ensemble_strategy():
    """测试集成策略."""
    print("=" * 80)
    print("测试福彩3D集成策略")
    print("=" * 80)
    
    records = make_test_history(100, seed=42)
    strategy = FC3DEnsembleStrategy()
    
    # 测试默认参数
    print("\n1. 测试默认参数：")
    tickets = strategy.generate(count=5, options={"history": records})
    
    for i, ticket in enumerate(tickets, 1):
        nums = ticket.groups["pos"]
        print(f"  第{i}组: {nums[0]} {nums[1]} {nums[2]}")
    
    print(f"\n策略说明：")
    print(f"  {ticket.basis[:200]}...")
    
    # 测试自适应权重
    print("\n2. 测试自适应权重：")
    tickets = strategy.generate(
        count=5,
        options={"history": records, "adaptive": True}
    )
    
    for i, ticket in enumerate(tickets, 1):
        nums = ticket.groups["pos"]
        print(f"  第{i}组: {nums[0]} {nums[1]} {nums[2]}")
    
    if "weights" in ticket.details:
        weights = ticket.details["weights"]
        print(f"\n  自适应权重：")
        print(f"    历史均衡: {weights['balanced']:.1%}")
        print(f"    智能冷热号: {weights['hot_cold']:.1%}")
        print(f"    遗漏号追踪: {weights['missing']:.1%}")
    
    # 测试固定权重
    print("\n3. 测试固定权重（偏向智能冷热号）：")
    tickets = strategy.generate(
        count=5,
        options={
            "history": records,
            "adaptive": False,
            "balanced_weight": 20,
            "hot_cold_weight": 60,
            "missing_weight": 20,
        }
    )
    
    for i, ticket in enumerate(tickets, 1):
        nums = ticket.groups["pos"]
        print(f"  第{i}组: {nums[0]} {nums[1]} {nums[2]}")
    
    # 测试不同温度
    print("\n4. 测试不同温度参数：")
    for temp in [1, 5, 10, 20]:
        tickets = strategy.generate(
            count=3,
            options={"history": records, "temperature": temp}
        )
        nums_list = [ticket.groups["pos"] for ticket in tickets]
        print(f"  温度={temp}: {nums_list}")
    
    # 测试χ²检验
    print("\n5. 测试χ²检验结果：")
    tickets = strategy.generate(count=1, options={"history": records})
    if "chi_square" in tickets[0].details:
        chi2 = tickets[0].details["chi_square"]
        is_uniform = tickets[0].details["is_uniform"]
        print(f"  χ²值: {chi2}")
        print(f"  均匀性: {is_uniform}")


def test_strategy_comparison():
    """对比集成策略与单一策略."""
    print("\n" + "=" * 80)
    print("对比集成策略与单一策略")
    print("=" * 80)
    
    from caipiao.core.strategies.lotteries.fc3d import (
        FC3DBalancedStrategy,
        FC3DSmartHotColdStrategy,
        FC3DMissingNumberStrategy,
    )
    
    records = make_test_history(100, seed=42)
    
    strategies = {
        "历史均衡": FC3DBalancedStrategy(),
        "智能冷热号": FC3DSmartHotColdStrategy(),
        "遗漏号追踪": FC3DMissingNumberStrategy(),
        "集成策略": FC3DEnsembleStrategy(),
    }
    
    for name, strategy in strategies.items():
        tickets = strategy.generate(count=10, options={"history": records})
        
        # 统计数字分布
        all_nums = []
        for ticket in tickets:
            all_nums.extend(ticket.groups["pos"])
        
        from collections import Counter
        counter = Counter(all_nums)
        
        print(f"\n【{name}】")
        print(f"  数字分布: {dict(sorted(counter.items()))}")
        
        # 计算均匀性
        total = len(all_nums)
        probs = [counter.get(d, 0) / total for d in range(10)]
        import math
        entropy = -sum(p * math.log2(p) for p in probs if p > 0)
        max_entropy = math.log2(10)
        uniformity = entropy / max_entropy
        print(f"  均匀性: {uniformity:.3f}")


if __name__ == "__main__":
    test_ensemble_strategy()
    test_strategy_comparison()
    
    print("\n" + "=" * 80)
    print("所有测试完成!")
    print("=" * 80)
