"""回测30期：对比 XGBoost vs XGBoost+LSTM 蓝球预测."""
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

lookback = 50
test_size = 30
recent_blue_count = 1

train_records = records[:-test_size]
blue_seq_train = [r.blue_ball for r in train_records if r.blue_ball is not None]

print(f"回测范围: 第{records[-test_size].issue} ~ 第{records[-1].issue}期")
print(f"训练蓝球序列: {len(blue_seq_train)} 期")
print()

# 训练两个模型
with tempfile.TemporaryDirectory() as tmpdir:
    # XGBoost
    xgb_path = Path(tmpdir) / 'xgb_model.pkl'
    xgb_predictor = MLPredictor(train_records, lookback=lookback, model_path=xgb_path)
    xgb_predictor.train()

    # LSTM
    lstm = BlueBallLSTM(seq_len=20, hidden_size=64, num_layers=2)
    lstm.train(blue_seq_train, epochs=50)

    # 回测
    xgb_blue_hit = 0
    lstm_blue_hit = 0
    combined_blue_hit = 0
    total = test_size

    for i in range(test_size):
        current_records = records[:len(train_records) + i]
        pred_X = build_prediction_features(current_records, lookback=lookback)
        if pred_X.size == 0:
            continue

        # XGBoost 预测
        red_proba, xgb_blue_proba = xgb_predictor.model.predict_proba(pred_X)

        # LSTM 预测
        current_blue_seq = [r.blue_ball for r in current_records if r.blue_ball is not None]
        lstm_blue_proba = lstm.predict(current_blue_seq[-20:])

        # 融合: 70% XGBoost + 30% LSTM
        combined_proba = 0.7 * xgb_blue_proba.flatten() + 0.3 * lstm_blue_proba

        # 剔除近期蓝球
        recent_blues = [r.blue_ball for r in current_records[-recent_blue_count:] if r.blue_ball is not None]

        def pick_blue(proba):
            ranked = np.argsort(-proba)
            for idx in ranked:
                num = idx + 1
                if num not in recent_blues:
                    return num
            return int(ranked[0]) + 1

        xgb_blue = pick_blue(xgb_blue_proba.flatten())
        lstm_blue = pick_blue(lstm_blue_proba)
        combined_blue = pick_blue(combined_proba)

        # 实际结果
        actual_idx = len(train_records) + i
        actual_blue = records[actual_idx].blue_ball
        issue = records[actual_idx].issue

        xgb_match = "✓" if xgb_blue == actual_blue else " "
        lstm_match = "✓" if lstm_blue == actual_blue else " "
        comb_match = "✓" if combined_blue == actual_blue else " "

        if xgb_blue == actual_blue: xgb_blue_hit += 1
        if lstm_blue == actual_blue: lstm_blue_hit += 1
        if combined_blue == actual_blue: combined_blue_hit += 1

        print(f"  {issue}  XGB:{xgb_blue:2d}{xgb_match}  LSTM:{lstm_blue:2d}{lstm_match}  融合:{combined_blue:2d}{comb_match}  实际:{actual_blue}")

    print()
    print("=== 蓝球命中率对比 ===")
    print(f"  XGBoost:     {xgb_blue_hit}/{total} = {xgb_blue_hit/total*100:.1f}%")
    print(f"  LSTM:        {lstm_blue_hit}/{total} = {lstm_blue_hit/total*100:.1f}%")
    print(f"  融合(7:3):   {combined_blue_hit}/{total} = {combined_blue_hit/total*100:.1f}%")
    print(f"  随机基线:    ~{total/16:.0f}/{total} = {100/16:.1f}%")
