"""预测接下来5期双色球：红球XGBoost + 蓝球LSTM，结果保存到文件."""
import sys
sys.path.insert(0, '.')

import numpy as np
from caipiao.ml.predictor import MLPredictor
from caipiao.ml.features import build_prediction_features
from caipiao.ml.blue_lstm import BlueBallLSTM
from caipiao.data.repository import DrawRepository
from caipiao.core.profile import SSQ
from pathlib import Path
from datetime import datetime
import tempfile

repo = DrawRepository(Path('.caipiao/draws.json'), profile=SSQ)
records = repo.get_all()

lookback = 3373
periods = 5

# 期号推算：2026077 ~ 2026081
last_issue = int(records[-1].issue)
start_issue = last_issue + 1

print(f"历史数据: {len(records)} 期，最新: {records[-1].issue}")
print(f"预测范围: {start_issue} ~ {start_issue + periods - 1} 期")
print()

# 训练模型
with tempfile.TemporaryDirectory() as tmpdir:
    xgb_path = Path(tmpdir) / 'xgb_model.pkl'
    xgb_predictor = MLPredictor(records, lookback=lookback, model_path=xgb_path)
    xgb_predictor.train()

    blue_seq = [r.blue_ball for r in records if r.blue_ball is not None]
    lstm = BlueBallLSTM(seq_len=20, hidden_size=64, num_layers=2)
    lstm.train(blue_seq, epochs=50)

    # XGBoost 红球概率
    red_proba, _ = xgb_predictor.model.predict_proba(
        build_prediction_features(records, lookback=lookback)
    )

    # 预测5期
    output_lines = []
    output_lines.append("=" * 70)
    output_lines.append(f"双色球预测报告（红球XGBoost + 蓝球LSTM）")
    output_lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    output_lines.append(f"训练数据: {len(records)} 期（截至 {records[-1].issue}）")
    output_lines.append(f"预测期数: {start_issue} ~ {start_issue + periods - 1}")
    output_lines.append("=" * 70)
    output_lines.append("")

    # 模拟逐期预测（每期更新蓝球序列）
    current_blue_seq = blue_seq[:]

    for p in range(periods):
        issue = f"{start_issue + p:07d}"

        # LSTM 蓝球概率（基于当前序列）
        lstm_blue_proba = lstm.predict(current_blue_seq[-20:])

        # 剔除上期蓝球
        recent_blue = current_blue_seq[-1] if current_blue_seq else 0
        blue_ranked = sorted(enumerate(lstm_blue_proba.flatten(), 1), key=lambda x: -x[1])
        blue_filtered = [(n, p_) for n, p_ in blue_ranked if n != recent_blue]

        # 红球概率（始终用最新数据）
        red_ranked = sorted(enumerate(red_proba.flatten(), 1), key=lambda x: -x[1])

        # 综合推荐
        top6_red = sorted([num for num, _ in red_ranked[:6]])
        top1_blue = blue_filtered[0][0]

        # 5组推荐
        rng = np.random.RandomState(2026077 + p)
        red_weights = red_proba.flatten() + 0.05
        red_weights = red_weights / red_weights.sum()

        output_lines.append(f"第 {p+1} 期：{issue}")
        output_lines.append("-" * 50)

        # 红球概率
        output_lines.append("  红球概率 TOP 5 (XGBoost):")
        for num, prob in red_ranked[:5]:
            bar = '#' * int(prob * 50)
            output_lines.append(f"    {num:2d}: {prob:.4f} {bar}")

        # 蓝球概率
        output_lines.append("  蓝球概率 TOP 5 (LSTM):")
        for num, prob in blue_filtered[:5]:
            bar = '#' * int(prob * 50)
            output_lines.append(f"    {num:2d}: {prob:.4f} {bar}")

        # 推荐号码
        output_lines.append("  推荐号码:")
        for i in range(5):
            reds = sorted(rng.choice(range(1, 34), size=6, replace=False, p=red_weights))
            red_str = " ".join(f"{n:02d}" for n in reds)
            output_lines.append(f"    第{i+1}组: 红球 {red_str}  蓝球 {top1_blue:02d}")

        red_str = " ".join(f"{n:02d}" for n in top6_red)
        output_lines.append(f"    综合: 红球 {red_str}  蓝球 {top1_blue:02d}")
        output_lines.append("")

        # 模拟下一期的蓝球序列（用预测蓝球继续推演）
        current_blue_seq.append(top1_blue)

    output_lines.append("=" * 70)
    output_lines.append("说明:")
    output_lines.append("  - 红球使用 XGBoost 模型预测（增强特征463维）")
    output_lines.append("  - 蓝球使用 LSTM 模型预测（时序建模）")
    output_lines.append("  - 蓝球已剔除上期相同号码")
    output_lines.append("  - 仅供参考，彩票为随机事件，不保证中奖")
    output_lines.append("=" * 70)

    # 输出到控制台
    report = "\n".join(output_lines)
    print(report)

    # 保存到文件
    save_path = Path("prediction_report.txt")
    save_path.write_text(report, encoding="utf-8")
    print(f"\n报告已保存到: {save_path.absolute()}")
