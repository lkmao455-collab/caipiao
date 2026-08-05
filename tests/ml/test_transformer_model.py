"""Transformer 模型测试."""

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

pytestmark = pytest.mark.skipif(not torch_available, reason="PyTorch 未安装，跳过 Transformer 测试")


class TestLotteryTransformerModel:
    """LotteryTransformerModel 测试."""

    def test_init_defaults(self):
        from caipiao.ml.transformer_model import LotteryTransformerModel

        model = LotteryTransformerModel()
        assert model.lookback == 50
        assert model.is_trained is False

    def test_init_custom_lookback(self):
        from caipiao.ml.transformer_model import LotteryTransformerModel

        model = LotteryTransformerModel(lookback=30)
        assert model.lookback == 30

    def test_check_torch(self):
        from caipiao.ml.transformer_model import LotteryTransformerModel

        model = LotteryTransformerModel()
        assert model._torch_available is True
        assert model._device is not None

    def test_build_sequence_input(self):
        from caipiao.ml.transformer_model import LotteryTransformerModel

        model = LotteryTransformerModel()
        base_x = np.array([1.0, 2.0, 3.0])
        mask = np.zeros(33, dtype=np.float32)
        mask[5] = 1.0
        result = model._build_sequence_input(base_x, mask, step=2)
        expected_len = 3 + 33 + 1
        assert result.shape == (expected_len,)
        assert result[-1] == pytest.approx(0.4)

    def test_build_sequence_training_data(self):
        from caipiao.ml.transformer_model import LotteryTransformerModel

        model = LotteryTransformerModel()
        n_samples = 10
        n_features = 5
        X = np.random.rand(n_samples, n_features).astype(np.float32)
        y_red = np.zeros((n_samples, 33), dtype=np.float32)
        for i in range(n_samples):
            reds = np.random.choice(33, 6, replace=False)
            y_red[i, reds] = 1.0
        X_seq, y_seq, encoder = model._build_sequence_training_data(X, y_red)
        assert X_seq.shape[0] == n_samples * 6
        assert y_seq.shape[0] == n_samples * 6
        assert len(encoder.classes_) <= 33

    def test_fit_predict_basic(self):
        from caipiao.ml.transformer_model import LotteryTransformerModel

        model = LotteryTransformerModel(lookback=10)
        n_samples = 30
        n_features = 8
        X = np.random.rand(n_samples, n_features).astype(np.float32)
        y_red = np.zeros((n_samples, 33), dtype=np.float32)
        y_blue = np.zeros((n_samples, 16), dtype=np.float32)
        for i in range(n_samples):
            reds = np.random.choice(33, 6, replace=False)
            y_red[i, reds] = 1.0
            blue = np.random.randint(0, 16)
            y_blue[i, blue] = 1.0
        model.fit(X, y_red, y_blue, epochs=1)
        assert model.is_trained is True

        X_test = np.random.rand(1, n_features).astype(np.float32)
        red_p, blue_p = model.predict_proba(X_test)
        assert red_p.shape == (33,)
        assert blue_p.shape == (16,)
        np.testing.assert_allclose(red_p.sum(), 1.0, rtol=1e-3)
        assert np.all(blue_p >= 0)
        assert np.all(blue_p <= 1)

    def test_sample_reds(self):
        from caipiao.ml.transformer_model import LotteryTransformerModel

        model = LotteryTransformerModel(lookback=10)
        n_samples = 40
        n_features = 8
        X = np.random.rand(n_samples, n_features).astype(np.float32)
        y_red = np.zeros((n_samples, 33), dtype=np.float32)
        y_blue = np.zeros((n_samples, 16), dtype=np.float32)
        for i in range(n_samples):
            reds = np.random.choice(33, 6, replace=False)
            y_red[i, reds] = 1.0
            blue = np.random.randint(0, 16)
            y_blue[i, blue] = 1.0
        model.fit(X, y_red, y_blue, epochs=1)
        X_test = np.random.rand(1, n_features).astype(np.float32)
        rng = np.random.RandomState(42)
        sampled = model.sample_reds(X_test, count=6, rng=rng)
        assert len(sampled) == 6
        assert len(set(sampled)) == 6
        assert all(1 <= n <= 33 for n in sampled)

    def test_save_load(self, tmp_path):
        from caipiao.ml.transformer_model import LotteryTransformerModel

        model = LotteryTransformerModel(lookback=10)
        n_samples = 20
        n_features = 6
        X = np.random.rand(n_samples, n_features).astype(np.float32)
        y_red = np.zeros((n_samples, 33), dtype=np.float32)
        y_blue = np.zeros((n_samples, 16), dtype=np.float32)
        for i in range(n_samples):
            reds = np.random.choice(33, 6, replace=False)
            y_red[i, reds] = 1.0
            blue = np.random.randint(0, 16)
            y_blue[i, blue] = 1.0
        model.fit(X, y_red, y_blue, epochs=1)
        path = tmp_path / "transformer_model.pkl"
        model.save(path)
        assert path.exists()

        model2 = LotteryTransformerModel()
        model2.load(path)
        assert model2.lookback == model.lookback
        assert model2.is_trained == model.is_trained
        X_test = np.random.rand(1, n_features).astype(np.float32)
        red_p1, blue_p1 = model.predict_proba(X_test)
        red_p2, blue_p2 = model2.predict_proba(X_test)
        np.testing.assert_allclose(red_p1, red_p2)
        np.testing.assert_allclose(blue_p1, blue_p2)

    def test_predict_before_fit_raises(self):
        from caipiao.ml.transformer_model import LotteryTransformerModel

        model = LotteryTransformerModel()
        X = np.random.rand(1, 10)
        with pytest.raises(RuntimeError, match="模型尚未训练"):
            model.predict_proba(X)