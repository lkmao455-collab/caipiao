"""福彩3D三策略融合 - 三种配置对比."""

from datetime import datetime, timedelta
import random
import math
from collections import Counter
from caipiao.core.strategies.lotteries.fc3d import FC3DEnsembleStrategy
from caipiao.data.models import DrawRecord


def make_history(n=200, seed=42):
    """创建历史数据."""
    random.seed(seed)
    records = []
    hot_digits = [2, 5, 8]
    cold_digits = [0, 4]

    for i in range(n):
        pos = []
        for p in range(3):
            rand = random.random()
            if rand < 0.15:
                digit = random.choice(hot_digits)
            elif rand < 0.20:
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


def analyze(tickets, hot_digits, cold_digits):
    """分析号码."""
    all_nums = []
    for ticket in tickets:
        all_nums.extend(ticket.groups['pos'])

    counter = Counter(all_nums)
    total = len(all_nums)

    freq = {d: counter.get(d, 0) / total for d in range(10)}
    odd_count = sum(1 for n in all_nums if n % 2 == 1)
    odd_ratio = odd_count / total
    high_count = sum(1 for n in all_nums if n >= 5)
    high_ratio = high_count / total

    probs = [freq[d] for d in range(10)]
    entropy = -sum(p * math.log2(p) for p in probs if p > 0)
    max_entropy = math.log2(10)
    uniformity = entropy / max_entropy

    hot_count = sum(counter.get(d, 0) for d in hot_digits)
    cold_count = sum(counter.get(d, 0) for d in cold_digits)

    return {
        'tickets': tickets,
        'freq': freq,
        'odd_ratio': odd_ratio,
        'high_ratio': high_ratio,
        'uniformity': uniformity,
        'hot_count': hot_count,
        'cold_count': cold_count,
    }


def run_comparison():
    """运行三种配置对比."""
    records = make_history(200, seed=42)
    hot_digits = [2, 5, 8]
    cold_digits = [0, 4]
    strategy = FC3DEnsembleStrategy()

    configs = [
        {'name': '热号为主', 'hot_weight': 80, 'cold_weight': 20},
        {'name': '冷号为主', 'hot_weight': 20, 'cold_weight': 80},
        {'name': '均衡配置', 'hot_weight': 50, 'cold_weight': 50},
    ]

    all_results = {}

    for config in configs:
        tickets = strategy.generate(
            count=20,
            options={
                'history': records,
                'hot_weight': config['hot_weight'],
                'cold_weight': config['cold_weight'],
                'temperature': 5,
            }
        )
        all_results[config['name']] = analyze(tickets, hot_digits, cold_digits)

    # 输出结果
    print('=' * 70)
    print('福彩3D三策略融合 - 三种配置对比')
    print('=' * 70)

    for config_name in ['热号为主', '冷号为主', '均衡配置']:
        result = all_results[config_name]
        print()
        print('【' + config_name + '】')
        print('-' * 50)
        print('生成号码:')
        for i, ticket in enumerate(result['tickets'][:10], 1):
            nums = ticket.groups['pos']
            print('  第%2d组: %d %d %d' % (i, nums[0], nums[1], nums[2]))
        print('  ... (共20组)')
        print()
        hot_pct = result['hot_count'] / 60 * 100
        cold_pct = result['cold_count'] / 60 * 100
        print('统计:')
        print('  热号(2,5,8): %d次 (%.1f%%)' % (result['hot_count'], hot_pct))
        print('  冷号(0,4): %d次 (%.1f%%)' % (result['cold_count'], cold_pct))
        print('  奇偶比: %.3f' % result['odd_ratio'])
        print('  大小比: %.3f' % result['high_ratio'])
        print('  均匀性: %.3f' % result['uniformity'])

    # 总结对比
    print()
    print('=' * 70)
    print('三种配置对比总结')
    print('=' * 70)
    print()
    print('%-10s %-12s %-12s %-10s %-10s %-10s' % ('配置', '热号占比', '冷号占比', '奇偶比', '大小比', '均匀性'))
    print('-' * 65)
    for config_name in ['热号为主', '冷号为主', '均衡配置']:
        r = all_results[config_name]
        hot_pct = r['hot_count'] / 60 * 100
        cold_pct = r['cold_count'] / 60 * 100
        print('%-10s %-10.1f%% %-10.1f%% %-10.3f %-10.3f %-10.3f' % (
            config_name, hot_pct, cold_pct, r['odd_ratio'], r['high_ratio'], r['uniformity']
        ))

    print()
    print('使用建议:')
    print('  - 热号为主: 相信趋势延续，追热号(2,5,8)')
    print('  - 冷号为主: 相信冷号回补，追冷号(0,4)')
    print('  - 均衡配置: 保守策略，各数字分布均匀')


if __name__ == '__main__':
    run_comparison()
