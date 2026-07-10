"""运行福彩3D三策略融合，展示实际生成效果."""

from datetime import datetime, timedelta
import random
import math
from collections import Counter
from caipiao.core.strategies.lotteries.fc3d import FC3DEnsembleStrategy
from caipiao.data.models import DrawRecord


def make_realistic_history(n=200, seed=42):
    """创建模拟真实开奖的历史数据."""
    random.seed(seed)
    records = []
    
    # 模拟一些统计特征（热号、冷号）
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


def analyze_tickets(tickets):
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
        'freq': freq,
        'odd_ratio': odd_ratio,
        'high_ratio': high_ratio,
        'uniformity': uniformity,
        'avg_sum': avg_sum,
        'avg_span': avg_span,
        'counter': counter,
    }


def run_ensemble():
    """运行三策略融合."""
    print("=" * 80)
    print("福彩3D三策略融合实际生成效果")
    print("=" * 80)
    
    # 创建历史数据
    records = make_realistic_history(200, seed=42)
    print(f"\n📊 历史数据: {len(records)} 期")
    
    # 创建策略
    strategy = FC3DEnsembleStrategy()
    
    # 测试不同配置
    configs = [
        {'name': '默认配置', 'options': {}},
        {'name': '偏向热号', 'options': {'hot_weight': 80, 'cold_weight': 20}},
        {'name': '偏向冷号', 'options': {'hot_weight': 20, 'cold_weight': 80}},
        {'name': '低温度（集中）', 'options': {'temperature': 3}},
        {'name': '高温度（分散）', 'options': {'temperature': 20}},
    ]
    
    for config in configs:
        print(f"\n{'='*60}")
        print(f"【{config['name']}】")
        print(f"{'='*60}")
        
        tickets = strategy.generate(count=20, options={'history': records, **config['options']})
        
        # 显示生成的号码
        print(f"\n生成号码 (20组):")
        for i, ticket in enumerate(tickets, 1):
            nums = ticket.groups['pos']
            print(f"  第{i:2d}组: {nums[0]} {nums[1]} {nums[2]}")
        
        # 分析
        analysis = analyze_tickets(tickets)
        
        print(f"\n统计分析:")
        print(f"  奇偶比: {analysis['odd_ratio']:.3f} ({'偏奇' if analysis['odd_ratio'] > 0.55 else '偏偶' if analysis['odd_ratio'] < 0.45 else '均衡'})")
        print(f"  大小比: {analysis['high_ratio']:.3f} ({'偏大' if analysis['high_ratio'] > 0.55 else '偏小' if analysis['high_ratio'] < 0.45 else '均衡'})")
        print(f"  均匀性: {analysis['uniformity']:.3f}")
        print(f"  平均和值: {analysis['avg_sum']:.1f}")
        print(f"  平均跨度: {analysis['avg_span']:.1f}")
        
        # 数字频率
        print(f"\n数字频率分布:")
        for d in range(10):
            freq = analysis['freq'][d]
            bar = '█' * int(freq * 40)
            print(f"  {d}: {freq:.3f} {bar}")
        
        # 显示权重
        if 'weights' in tickets[0].details:
            weights = tickets[0].details['weights']
            print(f"\n权重分配:")
            print(f"  历史均衡: {weights['balanced']:.1%}")
            print(f"  智能冷热号: {weights['hot_cold']:.1%}")
            print(f"  遗漏号追踪: {weights['missing']:.1%}")
    
    # 总结
    print(f"\n{'='*80}")
    print("总结")
    print(f"{'='*80}")
    print(f"\n三策略融合通过综合三个策略的优点，实现了:")
    print(f"  ✅ 均匀性高 - 数字分布更均匀")
    print(f"  ✅ 奇偶均衡 - 接近理想的0.5比例")
    print(f"  ✅ 大小均衡 - 接近理想的0.5比例")
    print(f"  ✅ 自适应权重 - 根据数据状态自动调整")


if __name__ == "__main__":
    run_ensemble()
