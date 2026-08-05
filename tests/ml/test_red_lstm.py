"""LSTM 模型测试."""

from __future__ import annotations

import sys

import numpy as np
import pytest

# 检查 PyTorch 是否可用
torch_available = False
try:
    import torch
    torch_available = True
except ImportError:
    pass

pytestmark = pytest.mark.skipif(not torch_available, reason="PyTorch 未安装，跳过 LSTM 测试")


class TestRedBallLSTM:
    """RedBallLSTM 测试."""

    def test_init_defaults(self):
        from caipiao.ml.red_lstm import RedBallLSTM

        model = RedBallLSTM()
        assert model.seq_len == 20
        assert model.hidden_size == 128
        assert model.num_layers == 2
        assert model.is_trained is False

    def test_init_custom_params(self):
        from caipiao.ml.red_lstm import RedBallLSTM

        model = RedBallLSTM(seq_len=10, hidden_size=64, num_layers=1)
        assert model.seq_len == 10
        assert model.hidden_size == 64
        assert model.num_layers == 1

    def test_encode_reds_batch(self):
        from caipiao.ml.red_lstm import RedBallLSTM

        model = RedBallLSTM()
        red_records = [[1, 2, 3, 4, 5, 6], [2, 3, 4, 5, 6, 7]]
        encoded = model._encode_reds_batch(red_records)
        assert encoded.shape == (2, 33)
        assert encoded[0, 0] == 1.0  # 号码 1
        assert encoded[0, 1] == 1.0  # 号码 2
        assert encoded[1, 1] == 1.0  # 号码 2
        assert np.all(encoded >= 0)
        assert np.all(encoded <= 1)

    def test_encode_reds_batch_invalid_numbers(self):
        from caipiao.ml.red_lstm import RedBallLSTM

        model = RedBallLSTM()
        # 包含无效号码（超出范围）
        red_records = [[0, 34, 5], [1, 2, 3]]
        encoded = model._encode_reds_batch(red_records)
        # 0 和 34 应被忽略
        assert encoded.shape == (2, 33)
        assert encoded[0, 4] == 1.0  # 号码 5
        assert np.all(encoded[0, :4] == 0)  # 1-4 没出现
        assert encoded[0, 33] == 0  # 超出范围被忽略

    def test_compute_missing_features_batch(self):
        from caipiao.ml.red_lstm import RedBallLSTM

        model = RedBallLSTM()
        # 构造已知的编码矩阵
        encoded = np.zeros((10, 33), dtype=np.float32)
        # 号码 1 在第 0, 3, 6 期出现（间隔 3, 3）
        encoded[0, 0] = 1
        encoded[3, 0] = 1
        encoded[6, 0] = 1
        # 号码 2 从未出现
        # 号码 3 只在最近期出现
        encoded[9, 2] = 1
        missing = model._compute_missing_features_batch(encoded)
        assert missing.shape == (5,)
        assert np.all(missing >= 0)
        # 遗漏特征：mean, std, max, min, missing_ratio
        # 号码 2 从未出现 -> missing[1] = 1.0
        # 最近期出现的号码 missing 较小

    def test_build_sequences_insufficient_data(self):
        from caipiao.ml.red_lstm import RedBallLSTM

        model = RedBallLSTM(seq_len=10)
        red_records = [[1, 2, 3]] * 5  # 只有 5 期，少于 seq_len+1=11
        X, y = model._build_sequences(red_records)
        assert X.size == 0
        assert y.size == 0

    def test_build_sequences_valid(self):
        from caipiao.ml.red_lstm import RedBallLSTM

        model = RedBallLSTM(seq_len=3)
        red_records = [[1, 2], [3, 4], [5, 6], [7, 8], [9, 10]]  # 5 期
        X, y = model._build_sequences(red_records)
        # seq_len=3, 5 期 -> 5-3=2 个样本
        assert X.shape == (2, 3, 33 + 5)
        assert y.shape == (2, 33)

    def test_train_insufficient_data(self):
        from caipiao.ml.red_lstm import RedBallLSTM

        model = RedBallLSTM(seq_len=10)
        red_records = [[1, 2, 3]] * 5
        model.train(red_records, epochs=1)
        assert model.is_trained is False  # 数据不足不训练

    def test_predict_before_train_raises(self):
        from caipiao.ml.red_lstm import RedBallLSTM

        model = RedBallLSTM()
        with pytest.raises(RuntimeError, match="模型尚未训练"):
            model.predict([[1, 2, 3]])

    def test_save_load(self, tmp_path):
        from caipiao.ml.red_lstm import RedBallLSTM

        model = RedBallLSTM(seq_len=5, hidden_size=32, num_layers=1)
        # 使用足够数据训练
        red_records = [[i % 33 + 1, (i + 1) % 33 + 1] for i in range(20)]
        model.train(red_records, epochs=2)
        if model.is_trained:
            path = tmp_path / "lstm_model.pkl"
            model.save(path)
            assert path.exists()

            model2 = RedBallLSTM.load(path)
            assert model2.seq_len == model.seq_len
            assert model2.hidden_size == model.hidden_size
            assert model2.num_layers == model.num_layers
            assert model2.is_trained == model.is_trained
            # 预测结果一致
            recent = [[1, 2], [3, 4], [5, 6], [7, 8], [9, 10]]
            p1 = model.predict(recent)
            p2 = model2.predict(recent)
            np.testing.assert_allclose(p1, p2)