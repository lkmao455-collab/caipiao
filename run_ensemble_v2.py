"""运行福彩3D三策略融合，展示实际效果."""

from datetime import datetime, timedelta
import random
import math
from collections import Counter
from caipiao.core.strategies.lotteries.fc3d import (
    FC3DEnsembleStrategy,
    FC3DBalancedStrategy,
    FC3DSmartHotColdStrategy,
    FC3DMissingNumberStrategy,
)
from caipiao.data.models import DrawRecord


def make_realistic_history(n=200, seed=42):
    """创建更真实的测试历史数据."""
    random.seed(seed)
    records = []
    
    # 模拟一些统计特征
    hot_digits = [2, 5, 8]  # 热号
    cold_digits = [0, 4]    # 冷号
    
    for i in range(n):
        pos = []
        for p in range(3):
            rand = random.random()
            if rand < 0.15:  # 15%概率选热号
                digit = random.choice(hot_digits)
            elif rand < 0.20:  # 5%概率选冷号
                digit = random.choice(cold_digits)
            else:
                digit = random.randint(0, 9)
            pos.append(digit)
        
        records.append(DrawRecord(
            issue=f'2024{i:03d}',
            draw_date=datetime(2024, 1, 1) + timedelta(days=i),
            profile='3d',
            groups={'pos': pos}
        ))
    
    return records


def analyze_tickets(tickets, name):
    """分析生成的号码."""
    all_nums = []
    for ticket in tickets:
        all_nums.extend(ticket.groups['pos'])
    
    counter = Counter(all_nums)
    total = len(all_nums)
    
    # 频率分布
    freq = {d: counter.get(d, 0) / total for d in range(10)}
    
    # 奇偶比
    odd_count = sum(1 for n in all_nums if n % 2 == 1)
    odd_ratio = odd_count / total
    
    # 大小比
    high_count = sum(1 for n in all_nums if n >= 5)
    high_ratio = high_count / total
    
    # 均匀性（熵）
    probs = [freq[d] for d in range(10)]
    entropy = -sum(p * math.log2(p) for p in probs if p > 0)
    max_entropy = math.log2(10)
    uniformity = entropy / max_entropy
    
    # 和值统计
    sums = [sum(ticket.groups['pos']) for ticket in tickets]
    avg_sum = sum(sums) / len(sums)
    
    # 跨度统计
    spans = [max(ticket.groups['pos']) - min(ticket.groups['pos']) for ticket in tickets]
    avg_span = sum(spans) / len(spans)
    
    return {
        'name': name,
        'freq': freq,
        'odd_ratio': odd_ratio,
        'high_ratio': high_ratio,
        'uniformity': uniformity,
        'avg_sum': avg_sum,
        'avg_span': avg_span,
    }


def print_analysis(analysis):
    """打印分析结果."""
    print(f"\n【{analysis['name']}】")
    print(f"  奇偶比: {analysis['odd_ratio']:.3f} ({'偏奇' if analysis['odd_ratio'] > 0.55 else '偏偶' if analysis['odd_ratio'] < 0.45 else '均衡'})")
    print(f"  大小比: {analysis['high_ratio']:.3f} ({'偏大' if analysis['high_ratio'] > 0.55 else '偏小' if analysis['high_ratio'] < 0.45 else '均衡'})")
    print(f"  均匀性: {analysis['uniformity']:.3f}")
    print(f"  平均和值: {analysis['avg_sum']:.1f}")
    print(f"  平均跨度: {analysis['avg_span']:.1f}")
    
    # 频率条形图
    print(f"  数字频率:")
    for d in range(10):
        freq = analysis['freq'][d]
        bar = '█' * int(freq * 50)
        print(f"    {d}: {freq:.3f} {bar}")


def run_full_comparison():
    """运行完整的策略对比."""
    print("=" * 80)
    print("福彩3D三策略融合实际效果测试")
    print("=" * 80)
    
    # 创建历史数据
    records = make_realistic_history(200, seed=42)
    print(f"\n历史数据: {len(records)} 期")
    
    # 策略列表
    strategies = {
        '历史均衡': FC3DBalancedStrategy(),
        '智能冷热号': FC3DSmartHotColdStrategy(),
        '遗漏号追踪': FC3DMissingNumberStrategy(),
        '三策略融合': FC3DEnsembleStrategy(),
    }
    
    # 运行各策略
    all_results = {}
    all_analyses = {}
    
    for name, strategy in strategies.items():
        print(f"\n{'='*60}")
        print(f"运行 {name}")
        print(f"{'='*60}")
        
        tickets = strategy.generate(count=20, options={'history': records})
        
        # 显示生成的号码
        print(f"\n生成号码 (前10组):")
        for i, ticket in enumerate(tickets[:10], 1):
            nums = ticket.groups['pos']
            print(f"  第{i:2d}组: {nums[0]} {nums[1]} {nums[2]}")
        
        # 分析
        analysis = analyze_tickets(tickets, name)
        all_analyses[name] = analysis
        all_results[name] = tickets
        
        # 显示分析结果
        print_analysis(analysis)
    
    # 总结对比
    print(f"\n{'='*80}")
    print("四策略效果对比总结")
    print(f"{'='*80}")
    
    print(f"\n{'策略':<12} {'均匀性':<10} {'奇偶比':<10} {'大小比':<10} {'平均和值':<10} {'平均跨度':<10}")
    print("-" * 65)
    for name, analysis in all_analyses.items():
        print(f"{name:<12} {analysis['uniformity']:<10.3f} {analysis['odd_ratio']:<10.3f} {analysis['high_ratio']:<10.3f} {analysis['avg_sum']:<10.1f} {analysis['avg_span']:<10.1f}")
    
    # 找出最佳策略
    best_uniformity = max(all_analyses.items(), key=lambda x: x[1]['uniformity'])
    best_balance = min(all_analyses.items(), key=lambda x: abs(x[1]['odd_ratio'] - 0.5) + abs(x[1]['high_ratio'] - 0.5))
    
    print(f"\n🏆 均匀性最佳: {best_uniformity[0]} ({best_uniformity[1]['uniformity']:.3f})")
    print(f"🏆 奇偶大小最均衡: {best_balance[0]}")
    
    # 三策略融合的详细信息
    ensemble_tickets = all_results['三策略融合']
    details0 = ensemble_tickets[0].details
    if 'pos_weights' in details0:
        print(f"\n📊 三策略融合逐位权重分配:")
        for pos in range(3):
            w = details0['pos_weights'][pos]
            print(f"  第{pos+1}位: 历史均衡={w['balanced']:.1%}, "
                  f"智能冷热号={w['hot_cold']:.1%}, 遗漏号追踪={w['missing']:.1%}")
    elif 'weights' in details0:
        weights = details0['weights']
        print(f"\n📊 三策略融合权重分配(三位平均):")
        print(f"  历史均衡: {weights['balanced']:.1%}")
        print(f"  智能冷热号: {weights['hot_cold']:.1%}")
        print(f"  遗漏号追踪: {weights['missing']:.1%}")


def run_ensemble_configs():
    """测试三策略融合的不同配置."""
    print(f"\n{'='*80}")
    print("三策略融合不同配置测试")
    print(f"{'='*80}")
    
    records = make_realistic_history(200, seed=42)
    strategy = FC3DEnsembleStrategy()
    
    configs = [
        {'name': '默认配置', 'options': {}},
        {'name': '偏向热号', 'options': {'hot_weight': 80, 'cold_weight': 20}},
        {'name': '偏向冷号', 'options': {'hot_weight': 20, 'cold_weight': 80}},
        {'name': '低温度（集中）', 'options': {'temperature': 3}},
        {'name': '高温度（分散）', 'options': {'temperature': 20}},
        {'name': '关闭自适应', 'options': {'adaptive': False}},
    ]
    
    for config in configs:
        print(f"\n【{config['name']}】")
        
        tickets = strategy.generate(count=10, options={'history': records, **config['options']})
        
        # 显示号码
        print(f"  生成号码:")
        for i, ticket in enumerate(tickets[:5], 1):
            nums = ticket.groups['pos']
            print(f"    第{i}组: {nums[0]} {nums[1]} {nums[2]}")
        
        # 分析
        analysis = analyze_tickets(tickets, config['name'])
        print(f"  均匀性: {analysis['uniformity']:.3f}, 奇偶比: {analysis['odd_ratio']:.3f}, 大小比: {analysis['high_ratio']:.3f}")
        
        # 显示权重
        weights = tickets[0].details.get("avg_weights") or tickets[0].details.get("weights")
        if weights:
            print(f"  权重: 均衡={weights['balanced']:.0%}, 冷热={weights['hot_cold']:.0%}, 遗漏={weights['missing']:.0%}")


if __name__ == "__main__":
    run_full_comparison()
    run_ensemble_configs()
    
    print(f"\n{'='*80}")
    print("测试完成!")
    print(f"{'='*80}")
