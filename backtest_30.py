"""回测最近30期（剔除近期蓝球，每期重新预测）."""
import sys
sys.path.insert(0, '.')

import numpy as np
from caipiao.ml.predictor import MLPredictor
from caipiao.ml.features import build_prediction_features
from caipiao.data.repository import DrawRepository
from caipiao.core.profile import SSQ
from pathlib import Path
import tempfile

repo = DrawRepository(Path('.caipiao/draws.json'), profile=SSQ)
records = repo.get_all()

lookback = 50
test_size = 30
recent_blue_count = 1

print(f"回测范围: 第{records[-test_size].issue} ~ 第{records[-1].issue}期")
print(f"训练数据: 前{len(records)-test_size}期")
print()

train_records = records[:-test_size]
with tempfile.TemporaryDirectory() as tmpdir:
    model_path = Path(tmpdir) / 'bt_model.pkl'
    predictor = MLPredictor(train_records, lookback=lookback, model_path=model_path)
    predictor.train()

    red_hit_counts = {0:0, 1:0, 2:0, 3:0, 4:0, 5:0, 6:0}
    blue_hit = 0
    results = []

    for i in range(test_size):
        # 用截至当前期的数据构建预测特征
        current_records = records[:len(train_records) + i]
        pred_X = build_prediction_features(current_records, lookback=lookback)
        if pred_X.size == 0:
            continue

        # 直接用模型预测（不走predictor.predict，避免用旧records）
        red_proba, blue_proba = predictor.model.predict_proba(pred_X)

        # 红球：取概率最高的6个
        red_predicted = set(np.argsort(-red_proba.flatten())[:6] + 1)

        # 蓝球：剔除近期出现过的，取概率最高的
        recent_blues = [r.blue_ball for r in current_records[-recent_blue_count:] if r.blue_ball is not None]
        blue_ranked = np.argsort(-blue_proba.flatten())
        blue_predicted = None
        for idx in blue_ranked:
            num = idx + 1
            if num not in recent_blues:
                blue_predicted = num
                break
        if blue_predicted is None:
            blue_predicted = int(blue_ranked[0]) + 1

        # 实际结果
        actual_idx = len(train_records) + i
        actual_reds = set(records[actual_idx].red_balls)
        actual_blue = records[actual_idx].blue_ball
        issue = records[actual_idx].issue

        red_hits = len(red_predicted & actual_reds)
        red_hit_counts[red_hits] += 1
        blue_match = 1 if blue_predicted == actual_blue else 0
        blue_hit += blue_match

        results.append({
            'issue': issue,
            'predicted_red': sorted(red_predicted),
            'actual_red': sorted(actual_reds),
            'red_hits': red_hits,
            'predicted_blue': blue_predicted,
            'actual_blue': actual_blue,
            'blue_match': blue_match,
        })

    # 输出详细结果
    print(f"{'期号':>8}  {'预测红球':<20}  {'实际红球':<20}  {'红球':>4}  {'预测蓝':>4}  {'实际蓝':>4}  {'蓝球':>4}")
    print("-" * 85)
    for r in results:
        pred_str = " ".join(f"{n:02d}" for n in r['predicted_red'])
        act_str = " ".join(f"{n:02d}" for n in r['actual_red'])
        blue_mark = "✓" if r['blue_match'] else " "
        print(f"{r['issue']:>8}  {pred_str:<20}  {act_str:<20}  {r['red_hits']:>4}   {r['predicted_blue']:>3}   {r['actual_blue']:>3}   {blue_mark:>3}")

    # 汇总
    total = len(results)
    print()
    print("=== 红球命中率 ===")
    for hits in range(7):
        count = red_hit_counts[hits]
        pct = count / total * 100
        bar = '#' * int(pct)
        print(f"  {hits}个命中: {count:2d}期 ({pct:5.1f}%) {bar}")

    total_hits = sum(h * red_hit_counts[h] for h in range(7))
    avg_hits = total_hits / total
    print(f"  平均每期命中: {avg_hits:.2f} 个红球")

    print()
    print(f"=== 蓝球命中率 ===")
    print(f"  命中: {blue_hit}/{total} = {blue_hit/total*100:.1f}%")

    # 奖级模拟
    print()
    print("=== 奖级模拟 ===")
    prize_counts = {'一等奖': 0, '二等奖': 0, '三等奖': 0, '四等奖': 0, '五等奖': 0, '六等奖': 0, '未中奖': 0}
    for r in results:
        rh = r['red_hits']
        bh = r['blue_match']
        if rh == 6 and bh == 1: prize_counts['一等奖'] += 1
        elif rh == 6: prize_counts['二等奖'] += 1
        elif rh == 5 and bh == 1: prize_counts['三等奖'] += 1
        elif rh == 5 or (rh == 4 and bh == 1): prize_counts['四等奖'] += 1
        elif rh == 4 or (rh == 3 and bh == 1): prize_counts['五等奖'] += 1
        elif bh == 1: prize_counts['六等奖'] += 1
        else: prize_counts['未中奖'] += 1

    for level, count in prize_counts.items():
        if count > 0:
            print(f"  {level}: {count}次")
