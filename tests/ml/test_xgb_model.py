"""XGBoost 模型测试."""

from __future__ import annotations

import numpy as np
import pytest

from caipiao.ml.model import LotteryXGBoostModel


class TestLotteryXGBoostModel:
    """LotteryXGBoostModel 测试."""

    def test_init_defaults(self):
        model = LotteryXGBoostModel()
        assert model.lookback == 50
        assert model.is_trained is False

    def test_init_custom_lookback(self):
        model = LotteryXGBoostModel(lookback=30)
        assert model.lookback == 30

    def test_fit_basic(self):
        model = LotteryXGBoostModel(lookback=10)
        n_samples = 50
        n_features = 20
        X = np.random.rand(n_samples, n_features).astype(np.float32)
        y_red = np.zeros((n_samples, 33), dtype=np.float32)
        y_blue = np.zeros((n_samples, 16), dtype=np.float32)
        for i in range(n_samples):
            reds = np.random.choice(33, 6, replace=False)
            y_red[i, reds] = 1.0
            blue = np.random.randint(0, 16)
            y_blue[i, blue] = 1.0
        model.fit(X, y_red, y_blue)
        assert model.is_trained is True
        assert model.red_sequence_model is not None
        assert model.blue_model is not None
        assert model.red_sequence_encoder is not None
        assert model._base_feature_dim == n_features

    def test_fit_empty_data_raises(self):
        model = LotteryXGBoostModel()
        X = np.array([]).reshape(0, 10)
        y_red = np.array([]).reshape(0, 33)
        y_blue = np.array([]).reshape(0, 16)
        with pytest.raises(ValueError, match="训练数据为空"):
            model.fit(X, y_red, y_blue)

    def test_fit_wrong_dim_raises(self):
        model = LotteryXGBoostModel()
        X = np.random.rand(10, 5)
        y_red = np.zeros((10, 33))
        y_blue = np.zeros((10, 16))
        y_red_1d = np.array([1, 2, 3, 4, 5])
        with pytest.raises(ValueError, match="二维数组"):
            model.fit(X, y_red_1d, y_blue)

    def test_predict_proba_before_fit_raises(self):
        model = LotteryXGBoostModel()
        X = np.random.rand(1, 10)
        with pytest.raises(RuntimeError, match="模型尚未训练"):
            model.predict_proba(X)

    def test_predict_proba_after_fit(self):
        model = LotteryXGBoostModel(lookback=10)
        n_samples = 50
        n_features = 15
        X = np.random.rand(n_samples, n_features).astype(np.float32)
        y_red = np.zeros((n_samples, 33), dtype=np.float32)
        y_blue = np.zeros((n_samples, 16), dtype=np.float32)
        for i in range(n_samples):
            reds = np.random.choice(33, 6, replace=False)
            y_red[i, reds] = 1.0
            blue = np.random.randint(0, 16)
            y_blue[i, blue] = 1.0
        model.fit(X, y_red, y_blue)
        X_test = np.random.rand(1, n_features).astype(np.float32)
        red_p, blue_p = model.predict_proba(X_test)
        assert red_p.shape == (33,)
        assert blue_p.shape == (16,)
        # 红球概率和为 1
        np.testing.assert_allclose(red_p.sum(), 1.0, rtol=1e-3)
        # 蓝球是独立二分类概率，在 [0,1] 范围
        assert np.all(blue_p >= 0)
        assert np.all(blue_p <= 1)
        assert np.all(red_p >= 0)

    def test_sample_reds(self):
        model = LotteryXGBoostModel(lookback=10)
        n_samples = 60
        n_features = 12
        X = np.random.rand(n_samples, n_features).astype(np.float32)
        y_red = np.zeros((n_samples, 33), dtype=np.float32)
        y_blue = np.zeros((n_samples, 16), dtype=np.float32)
        for i in range(n_samples):
            reds = np.random.choice(33, 6, replace=False)
            y_red[i, reds] = 1.0
            blue = np.random.randint(0, 16)
            y_blue[i, blue] = 1.0
        model.fit(X, y_red, y_blue)
        X_test = np.random.rand(1, n_features).astype(np.float32)
        rng = np.random.RandomState(42)
        sampled = model.sample_reds(X_test, count=6, rng=rng)
        assert len(sampled) == 6
        assert len(set(sampled)) == 6  # 无重复
        assert all(1 <= n <= 33 for n in sampled)

    def test_sample_reds_before_fit_raises(self):
        model = LotteryXGBoostModel()
        X = np.random.rand(1, 10)
        rng = np.random.RandomState(42)
        with pytest.raises(RuntimeError, match="模型尚未训练"):
            model.sample_reds(X, 6, rng)

    def test_save_load(self, tmp_path):
        model = LotteryXGBoostModel(lookback=10)
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
        model.fit(X, y_red, y_blue)
        path = tmp_path / "xgb_model.pkl"
        model.save(path)
        assert path.exists()
        # 加载到新实例
        model2 = LotteryXGBoostModel()
        model2.load(path)
        assert model2.is_trained is True
        assert model2.lookback == model.lookback
        # 预测结果应一致
        X_test = np.random.rand(1, n_features).astype(np.float32)
        red_p1, blue_p1 = model.predict_proba(X_test)
        red_p2, blue_p2 = model2.predict_proba(X_test)
        np.testing.assert_allclose(red_p1, red_p2)
        np.testing.assert_allclose(blue_p1, blue_p2)

    def test_build_sequence_input(self):
        model = LotteryXGBoostModel()
        base_x = np.array([1.0, 2.0, 3.0])
        mask = np.zeros(33, dtype=np.float32)
        mask[5] = 1.0
        result = model._build_sequence_input(base_x, mask, step=2)
        expected_len = 3 + 33 + 1
        assert result.shape == (expected_len,)
        assert result[-1] == pytest.approx(0.4)

    def test_build_sequence_training_data(self):
        model = LotteryXGBoostModel()
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

    def test_incremental_fit(self):
        model = LotteryXGBoostModel(lookback=10)
        n_samples = 30
        n_features = 10
        # 使用固定的类别分布，避免类别数变化
        X1 = np.random.rand(n_samples, n_features).astype(np.float32)
        y_red1 = np.zeros((n_samples, 33), dtype=np.float32)
        y_blue1 = np.zeros((n_samples, 16), dtype=np.float32)
        # 只使用前 10 个红球，确保类别固定
        for i in range(n_samples):
            reds = np.random.choice(10, 6, replace=False)
            y_red1[i, reds] = 1.0
            blue = np.random.randint(0, 8)
            y_blue1[i, blue] = 1.0
        model.fit(X1, y_red1, y_blue1)
        assert model.is_trained is True

        # 增量训练：新数据，使用相同的类别范围
        X2 = np.random.rand(20, n_features).astype(np.float32)
        y_red2 = np.zeros((20, 33), dtype=np.float32)
        y_blue2 = np.zeros((20, 16), dtype=np.float32)
        for i in range(20):
            reds = np.random.choice(10, 6, replace=False)
            y_red2[i, reds] = 1.0
            blue = np.random.randint(0, 8)
            y_blue2[i, blue] = 1.0
        model.fit(X2, y_red2, y_blue2, incremental=True)
        assert model.is_trained is True