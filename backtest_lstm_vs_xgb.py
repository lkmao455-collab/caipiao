"""回测30期：LSTM vs XGBoost 红球+蓝球对比."""
import sys
sys.path.insert(0, '.')

import numpy as np
from caipiao.ml.predictor import MLPredictor
from caipiao.ml.features import build_prediction_features
from caipiao.ml.red_lstm import RedBallLSTM
from caipiao.ml.blue_lstm import BlueBallLSTM
from caipiao.data.repository import DrawRepository
from caipiao.core.profile import SSQ
from pathlib import Path
import tempfile

repo = DrawRepository(Path('.caipiao/draws.json'), profile=SSQ)
records = repo.get_all()

lookback = 50
test_size = 30
seq_len = 20

train_records = records[:-test_size]
print(f"回测: 最近{test_size}期, 训练: {len(train_records)}期")
print()

# XGBoost
with tempfile.TemporaryDirectory() as tmpdir:
    xgb_path = Path(tmpdir) / 'xgb.pkl'
    xgb_pred = MLPredictor(train_records, lookback=lookback, model_path=xgb_path)
    xgb_pred.train()

    # LSTM
    red_lists = [r.red_balls for r in train_records]
    blue_list = [r.blue_ball for r in train_records if r.blue_ball is not None]

    red_lstm = RedBallLSTM(seq_len=seq_len)
    red_lstm.train(red_lists, epochs=30)

    blue_lstm = BlueBallLSTM(seq_len=seq_len)
    blue_lstm.train(blue_list, epochs=30)

    # 回测统计
    xgb_red_hits = {0:0, 1:0, 2:0, 3:0, 4:0, 5:0, 6:0}
    lstm_red_hits = {0:0, 1:0, 2:0, 3:0, 4:0, 5:0, 6:0}
    xgb_blue_hit = 0
    lstm_blue_hit = 0

    for i in range(test_size):
        current = records[:len(train_records) + i]
        actual_idx = len(train_records) + i
        actual_reds = set(records[actual_idx].red_balls)
        actual_blue = records[actual_idx].blue_ball

        # XGBoost 红球
        pred_X = build_prediction_features(current, lookback=lookback)
        red_p, blue_p = xgb_pred.model.predict_proba(pred_X)
        xgb_red = set(np.argsort(-red_p.flatten())[:6] + 1)
        xgb_red_hits[len(xgb_red & actual_reds)] += 1

        # XGBoost 蓝球
        xgb_blue = int(np.argmax(blue_p.flatten())) + 1
        if xgb_blue == actual_blue:
            xgb_blue_hit += 1

        # LSTM 红球
        cur_reds = [r.red_balls for r in current]
        lstm_red_p = red_lstm.predict(cur_reds[-seq_len:])
        lstm_red = set(np.argsort(-lstm_red_p)[:6] + 1)
        lstm_red_hits[len(lstm_red & actual_reds)] += 1

        # LSTM 蓝球
        cur_blues = [r.blue_ball for r in current if r.blue_ball is not None]
        lstm_blue_p = blue_lstm.predict(cur_blues[-seq_len:])
        lstm_blue = int(np.argmax(lstm_blue_p)) + 1
        if lstm_blue == actual_blue:
            lstm_blue_hit += 1

    total = test_size

    print("=== 红球命中率对比 ===")
    print(f"{'命中数':>6}  {'XGBoost':>10}  {'LSTM':>10}")
    for h in range(7):
        xgb_pct = xgb_red_hits[h] / total * 100
        lstm_pct = lstm_red_hits[h] / total * 100
        print(f"  {h}个:  {xgb_red_hits[h]:2d} ({xgb_pct:4.1f}%)  {lstm_red_hits[h]:2d} ({lstm_pct:4.1f}%)")

    xgb_avg = sum(h * xgb_red_hits[h] for h in range(7)) / total
    lstm_avg = sum(h * lstm_red_hits[h] for h in range(7)) / total
    print(f"  平均:  {xgb_avg:.2f}          {lstm_avg:.2f}")

    print()
    print("=== 蓝球命中率对比 ===")
    print(f"  XGBoost: {xgb_blue_hit}/{total} = {xgb_blue_hit/total*100:.1f}%")
    print(f"  LSTM:    {lstm_blue_hit}/{total} = {lstm_blue_hit/total*100:.1f}%")
    print(f"  随机:    ~{total/16:.0f}/{total} = {100/16:.1f}%")
