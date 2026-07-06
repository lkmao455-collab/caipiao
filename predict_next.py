"""预测下一期双色球：红球XGBoost + 蓝球LSTM."""
import sys
sys.path.insert(0, '.')

import numpy as np
from caipiao.ml.predictor import MLPredictor
from caipiao.ml.features import build_prediction_features
from caipiao.ml.blue_lstm import BlueBallLSTM
from caipiao.data.repository import DrawRepository
from caipiao.core.profile import SSQ
from pathlib import Path
import tempfile

repo = DrawRepository(Path('.caipiao/draws.json'), profile=SSQ)
records = repo.get_all()

lookback = 3373
recent_blue_count = 1

print(f"最新一期: {records[-1].issue} ({records[-1].draw_date.date()}) 红球{records[-1].red_balls} 蓝球{records[-1].blue_ball}")
print(f"最近1期蓝球: {[r.blue_ball for r in records[-recent_blue_count:]]}（将剔除）")
print()

# 训练模型
with tempfile.TemporaryDirectory() as tmpdir:
    # XGBoost（红球）
    xgb_path = Path(tmpdir) / 'xgb_model.pkl'
    xgb_predictor = MLPredictor(records, lookback=lookback, model_path=xgb_path)
    xgb_predictor.train()

    # LSTM（蓝球）
    blue_seq = [r.blue_ball for r in records if r.blue_ball is not None]
    lstm = BlueBallLSTM(seq_len=20, hidden_size=64, num_layers=2)
    lstm.train(blue_seq, epochs=50)

    # XGBoost 红球概率
    red_proba, _ = xgb_predictor.model.predict_proba(
        build_prediction_features(records, lookback=lookback)
    )

    # LSTM 蓝球概率
    lstm_blue_proba = lstm.predict(blue_seq[-20:])

    # 红球概率排名
    red_ranked = sorted(enumerate(red_proba.flatten(), 1), key=lambda x: -x[1])
    print("=== 红球概率 TOP 15 (XGBoost) ===")
    for num, prob in red_ranked[:15]:
        bar = '#' * int(prob * 80)
        print(f"  {num:2d}: {prob:.4f} {bar}")

    # 蓝球概率排名（剔除近期）
    recent_blues = [r.blue_ball for r in records[-recent_blue_count:] if r.blue_ball is not None]
    blue_ranked = sorted(enumerate(lstm_blue_proba.flatten(), 1), key=lambda x: -x[1])
    blue_filtered = [(n, p) for n, p in blue_ranked if n not in recent_blues]
    print()
    print("=== 蓝球概率 TOP 8 (LSTM，已剔除近期) ===")
    for num, prob in blue_filtered[:8]:
        bar = '#' * int(prob * 80)
        print(f"  {num:2d}: {prob:.4f} {bar}")

    # 推荐号码
    print()
    print("=== 推荐号码（5组）===")
    for i in range(5):
        rng = np.random.RandomState(2026077 + i)
        # 红球：加权采样
        weights = red_proba.flatten() + 0.05
        weights = weights / weights.sum()
        reds = sorted(rng.choice(range(1, 34), size=6, replace=False, p=weights))
        # 蓝球：取概率最高的（已剔除近期）
        blues = [blue_filtered[0][0]]
        red_str = " ".join(f"{n:02d}" for n in reds)
        print(f"  第{i+1}组: 红球 {red_str}  蓝球 {blues[0]:02d}")

    # 综合推荐
    top6_red = [num for num, _ in red_ranked[:6]]
    top1_blue = blue_filtered[0][0]
    red_str = " ".join(f"{n:02d}" for n in sorted(top6_red))
    print()
    print(f"  综合推荐: 红球 {red_str}  蓝球 {top1_blue:02d}")
