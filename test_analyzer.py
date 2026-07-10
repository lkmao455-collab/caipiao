"""测试三策略统一分析框架."""

from datetime import datetime, timedelta
import random
from caipiao.core.strategies.lotteries.fc3d.analyzer import FC3DAnalyzer, format_report
from caipiao.data.models import DrawRecord


def make_test_history(n=100, seed=42):
    """创建测试历史数据."""
    random.seed(seed)
    records = []
    
    for i in range(n):
        # 生成带有一定规律的号码
        if random.random() < 0.3:  # 30%概率偏向某些数字
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


def test_analyzer():
    """测试分析框架."""
    print("=" * 80)
    print("测试三策略统一分析框架")
    print("=" * 80)
    
    # 创建测试数据
    records = make_test_history(100, seed=42)
    print(f"\n创建测试数据：{len(records)} 期")
    
    # 创建分析器
    analyzer = FC3DAnalyzer(records, lookback=100)
    
    # 生成对比报告
    print("\n运行三策略对比分析...")
    report = analyzer.generate_comparison_report(count=5)
    
    # 格式化输出
    formatted_report = format_report(report)
    print(formatted_report)
    
    # 测试单个策略运行
    print("\n" + "=" * 80)
    print("测试单个策略运行")
    print("=" * 80)
    
    for strategy_name in ["balanced", "smart_hot_cold", "missing_number"]:
        result = analyzer.run_strategy(strategy_name, count=3)
        print(f"\n【{strategy_name}】")
        print(f"  执行时间：{result.execution_time:.3f}秒")
        print(f"  生成号码：")
        for i, ticket in enumerate(result.tickets[:3], 1):
            nums = ticket["numbers"]
            print(f"    第{i}组: {nums[0]} {nums[1]} {nums[2]}")


def test_custom_options():
    """测试自定义参数."""
    print("\n" + "=" * 80)
    print("测试自定义参数")
    print("=" * 80)
    
    records = make_test_history(100, seed=42)
    analyzer = FC3DAnalyzer(records, lookback=100)
    
    # 自定义参数
    custom_options = {
        "balanced": {"temperature": 5},
        "smart_hot_cold": {"hot_weight": 80, "cold_weight": 20},
        "missing_number": {"z_threshold": 258},
    }
    
    report = analyzer.generate_comparison_report(count=3, options=custom_options)
    formatted_report = format_report(report)
    print(formatted_report)


def test_distance_calculation():
    """测试策略间距离计算."""
    print("\n" + "=" * 80)
    print("测试策略间距离计算")
    print("=" * 80)
    
    records = make_test_history(100, seed=42)
    analyzer = FC3DAnalyzer(records, lookback=100)
    
    # 运行所有策略
    results = analyzer.run_all_strategies(count=10)
    
    # 对比分析
    comparison = analyzer.compare_strategies(results)
    
    print("\n策略间距离矩阵：")
    for (name1, name2), distance in comparison["distance_matrix"].items():
        if name1 < name2:
            print(f"  {name1} vs {name2}: {distance:.4f}")
    
    print("\n策略评分：")
    for name, score in sorted(
        comparison["scores"].items(), key=lambda x: x[1], reverse=True
    ):
        print(f"  {name}: {score:.3f}")
    
    print(f"\n最佳策略：{comparison['best_strategy']}")


if __name__ == "__main__":
    test_analyzer()
    test_custom_options()
    test_distance_calculation()
    
    print("\n" + "=" * 80)
    print("所有测试完成!")
    print("=" * 80)
