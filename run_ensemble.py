"""运行福彩3D集成策略，展示效果."""

from datetime import datetime, timedelta
import random
from collections import Counter
from caipiao.core.strategies.lotteries.fc3d import (
    FC3DEnsembleStrategy,
    FC3DBalancedStrategy,
    FC3DSmartHotColdStrategy,
    FC3DMissingNumberStrategy,
)
from caipiao.data.models import DrawRecord


def make_test_history(n=200, seed=42):
    """创建测试历史数据（模拟真实开奖）."""
    random.seed(seed)
    records = []
    
    for i in range(n):
        # 模拟带有统计特征的开奖数据
        pos = []
        for p in range(3):
            # 某些数字出现频率较高（模拟热号）
            if random.random() < 0.15:
                digit = random.choice([2, 5, 8])  # 热号
            elif random.random() < 0.05:
                digit = random.choice([0, 4])  # 冷号
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


def run_comparison():
    """运行四策略对比."""
    print("=" * 80)
    print("福彩3D四策略对比运行")
    print("=" * 80)
    
    records = make_test_history(200, seed=42)
    print(f"\n历史数据：{len(records)} 期")
    
    strategies = {
        "历史均衡": FC3DBalancedStrategy(),
        "智能冷热号": FC3DSmartHotColdStrategy(),
        "遗漏号追踪": FC3DMissingNumberStrategy(),
        "集成策略": FC3DEnsembleStrategy(),
    }
    
    all_results = {}
    
    for name, strategy in strategies.items():
        print(f"\n{'='*60}")
        print(f"【{name}】")
        print(f"{'='*60}")
        
        tickets = strategy.generate(count=10, options={"history": records})
        
        print(f"\n生成号码：")
        for i, ticket in enumerate(tickets, 1):
            nums = ticket.groups["pos"]
            print(f"  第{i:2d}组: {nums[0]} {nums[1]} {nums[2]}")
        
        # 统计分析
        all_nums = []
        for ticket in tickets:
            all_nums.extend(ticket.groups["pos"])
        
        counter = Counter(all_nums)
        total = len(all_nums)
        
        # 数字频率
        print(f"\n数字频率分布：")
        for d in range(10):
            freq = counter.get(d, 0) / total
            bar = "█" * int(freq * 50)
            print(f"  {d}: {freq:.3f} {bar}")
        
        # 奇偶比
        odd_count = sum(1 for n in all_nums if n % 2 == 1)
        odd_ratio = odd_count / total
        print(f"\n奇偶比: {odd_ratio:.3f} ({'偏奇' if odd_ratio > 0.55 else '偏偶' if odd_ratio < 0.45 else '均衡'})")
        
        # 大小比
        high_count = sum(1 for n in all_nums if n >= 5)
        high_ratio = high_count / total
        print(f"大小比: {high_ratio:.3f} ({'偏大' if high_ratio > 0.55 else '偏小' if high_ratio < 0.45 else '均衡'})")
        
        # 均匀性
        probs = [counter.get(d, 0) / total for d in range(10)]
        import math
        entropy = -sum(p * math.log2(p) for p in probs if p > 0)
        max_entropy = math.log2(10)
        uniformity = entropy / max_entropy
        print(f"均匀性: {uniformity:.3f}")
        
        all_results[name] = {
            "tickets": tickets,
            "uniformity": uniformity,
            "odd_ratio": odd_ratio,
            "high_ratio": high_ratio,
        }
    
    # 总结对比
    print(f"\n{'='*80}")
    print("四策略效果对比总结")
    print(f"{'='*80}")
    
    print(f"\n{'策略':<12} {'均匀性':<10} {'奇偶比':<10} {'大小比':<10}")
    print("-" * 45)
    for name, result in all_results.items():
        print(f"{name:<12} {result['uniformity']:<10.3f} {result['odd_ratio']:<10.3f} {result['high_ratio']:<10.3f}")
    
    # 推荐
    best_uniformity = max(all_results.items(), key=lambda x: x[1]["uniformity"])
    print(f"\n🏆 均匀性最佳：{best_uniformity[0]} ({best_uniformity[1]['uniformity']:.3f})")


def run_ensemble_detailed():
    """详细运行集成策略."""
    print(f"\n{'='*80}")
    print("集成策略详细运行")
    print(f"{'='*80}")
    
    records = make_test_history(200, seed=42)
    strategy = FC3DEnsembleStrategy()
    
    # 测试不同配置
    configs = [
        {"name": "默认配置", "options": {}},
        {"name": "偏向热号", "options": {"hot_weight": 80, "cold_weight": 20}},
        {"name": "偏向冷号", "options": {"hot_weight": 20, "cold_weight": 80}},
        {"name": "低温度（集中）", "options": {"temperature": 3}},
        {"name": "高温度（分散）", "options": {"temperature": 20}},
    ]
    
    for config in configs:
        print(f"\n【{config['name']}】")
        
        tickets = strategy.generate(
            count=5,
            options={"history": records, **config["options"]}
        )
        
        for i, ticket in enumerate(tickets, 1):
            nums = ticket.groups["pos"]
            print(f"  第{i}组: {nums[0]} {nums[1]} {nums[2]}")
        
        # 显示权重
        if "weights" in ticket.details:
            weights = ticket.details["weights"]
            print(f"  权重: 均衡={weights['balanced']:.0%}, 冷热={weights['hot_cold']:.0%}, 遗漏={weights['missing']:.0%}")


if __name__ == "__main__":
    run_comparison()
    run_ensemble_detailed()
    
    print(f"\n{'='*80}")
    print("运行完成!")
    print(f"{'='*80}")
