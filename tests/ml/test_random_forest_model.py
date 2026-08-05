"""随机森林模型测试."""

from __future__ import annotations

import numpy as np
import pytest

from caipiao.ml.random_forest_model import LotteryRandomForestModel


class TestLotteryRandomForestModel:
    """LotteryRandomForestModel 测试."""

    def test_init_defaults(self):
        model = LotteryRandomForestModel()
        assert model.lookback == 50
        assert model.is_trained is False

    def test_init_custom_lookback(self):
        model = LotteryRandomForestModel(lookback=30)
        assert model.lookback == 30

    def test_fit_basic(self):
        model = LotteryRandomForestModel(lookback=10)
        n_samples = 50
        n_features = 20
        X = np.random.rand(n_samples, n_features).astype(np.float32)
        y_red = np.zeros((n_samples, 33), dtype=np.float32)
        y_blue = np.zeros((n_samples, 16), dtype=np.float32)
        # 每期 6 个红球
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
        model = LotteryRandomForestModel()
        X = np.array([]).reshape(0, 10)
        y_red = np.array([]).reshape(0, 33)
        y_blue = np.array([]).reshape(0, 16)
        with pytest.raises(ValueError, match="训练数据为空"):
            model.fit(X, y_red, y_blue)

    def test_predict_proba_before_fit_raises(self):
        model = LotteryRandomForestModel()
        X = np.random.rand(1, 10)
        with pytest.raises(RuntimeError, match="模型尚未训练"):
            model.predict_proba(X)

    def test_predict_proba_after_fit(self):
        model = LotteryRandomForestModel(lookback=10)
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
        # 红球概率和为 1（概率分布）
        np.testing.assert_allclose(red_p.sum(), 1.0, rtol=1e-3)
        # 蓝球是独立二分类概率，不要求和为 1，只要求在 [0,1] 范围
        assert np.all(blue_p >= 0)
        assert np.all(blue_p <= 1)
        assert np.all(red_p >= 0)

    def test_sample_reds(self):
        model = LotteryRandomForestModel(lookback=10)
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
        model = LotteryRandomForestModel()
        X = np.random.rand(1, 10)
        rng = np.random.RandomState(42)
        with pytest.raises(RuntimeError, match="模型尚未训练"):
            model.sample_reds(X, 6, rng)

    def test_feature_importance_before_fit(self):
        model = LotteryRandomForestModel()
        red_imp, blue_imp = model.feature_importance()
        assert red_imp.size == 0
        assert blue_imp.size == 0

    def test_feature_importance_after_fit(self):
        model = LotteryRandomForestModel(lookback=10)
        n_samples = 40
        n_features = 10
        X = np.random.rand(n_samples, n_features).astype(np.float32)
        y_red = np.zeros((n_samples, 33), dtype=np.float32)
        y_blue = np.zeros((n_samples, 16), dtype=np.float32)
        for i in range(n_samples):
            reds = np.random.choice(33, 6, replace=False)
            y_red[i, reds] = 1.0
            blue = np.random.randint(0, 16)
            y_blue[i, blue] = 1.0
        model.fit(X, y_red, y_blue)
        red_imp, blue_imp = model.feature_importance()
        assert red_imp.size > 0
        assert blue_imp.size > 0
        # 重要性非负
        assert np.all(red_imp >= 0)
        assert np.all(blue_imp >= 0)

    def test_save_load(self, tmp_path):
        model = LotteryRandomForestModel(lookback=10)
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
        path = tmp_path / "rf_model.pkl"
        model.save(path)
        assert path.exists()
        # 加载到新实例
        model2 = LotteryRandomForestModel()
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
        model = LotteryRandomForestModel()
        base_x = np.array([1.0, 2.0, 3.0])
        mask = np.zeros(33, dtype=np.float32)
        mask[5] = 1.0
        result = model._build_sequence_input(base_x, mask, step=2)
        expected_len = 3 + 33 + 1  # base_x + mask + step_norm
        assert result.shape == (expected_len,)
        # step_norm = 2 / max(6-1, 1) = 2/5 = 0.4
        assert result[-1] == pytest.approx(0.4)

    def test_build_sequence_training_data(self):
        model = LotteryRandomForestModel()
        n_samples = 10
        n_features = 5
        X = np.random.rand(n_samples, n_features).astype(np.float32)
        y_red = np.zeros((n_samples, 33), dtype=np.float32)
        for i in range(n_samples):
            reds = np.random.choice(33, 6, replace=False)
            y_red[i, reds] = 1.0
        X_seq, y_seq, encoder = model._build_sequence_training_data(X, y_red)
        # 每期 6 个红球 -> n_samples * 6 个训练样本
        assert X_seq.shape[0] == n_samples * 6
        assert y_seq.shape[0] == n_samples * 6
        assert len(encoder.classes_) <= 33  # 实际出现的类别数