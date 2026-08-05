"""马尔可夫链模型测试."""

from __future__ import annotations

import numpy as np
import pytest

from caipiao.ml.markov_model import MarkovChainModel


class TestMarkovChainModel:
    """MarkovChainModel 测试."""

    def test_init_default_order(self):
        model = MarkovChainModel()
        assert model.order == 2
        assert model.is_trained is False

    def test_init_custom_order(self):
        model = MarkovChainModel(order=1)
        assert model.order == 1

    def test_fit_basic(self):
        model = MarkovChainModel(order=1)
        red_sequences = [[1, 2, 3, 4, 5, 6], [2, 3, 4, 5, 6, 7], [3, 4, 5, 6, 7, 8]]
        blue_sequences = [1, 2, 3]
        model.fit(red_sequences, blue_sequences, red_count=10, blue_count=5)
        assert model.is_trained is True
        assert model.red_transition is not None
        assert model.blue_transition is not None
        assert model.red_transition.shape == (10, 10)
        assert model.blue_transition.shape == (5, 5)

    def test_fit_insufficient_data_returns_uniform(self):
        model = MarkovChainModel(order=2)
        red_sequences = [[1, 2, 3]]
        blue_sequences = [1]
        model.fit(red_sequences, blue_sequences, red_count=5, blue_count=3)
        assert model.is_trained is True
        # 与均匀分布接近（平滑后）
        red_sum = model.red_transition.sum(axis=1)
        blue_sum = model.blue_transition.sum(axis=1)
        np.testing.assert_allclose(red_sum, 1.0, rtol=1e-5)
        np.testing.assert_allclose(blue_sum, 1.0, rtol=1e-5)

    def test_predict_proba_before_fit_raises(self):
        model = MarkovChainModel()
        with pytest.raises(RuntimeError, match="模型尚未训练"):
            model.predict_proba()

    def test_predict_proba_after_fit(self):
        model = MarkovChainModel(order=1)
        red_sequences = [[1, 2, 3, 4, 5, 6]] * 20
        blue_sequences = [1] * 20
        model.fit(red_sequences, blue_sequences, red_count=33, blue_count=16)
        red_p, blue_p = model.predict_proba(lookback=10)
        assert red_p.shape == (33,)
        assert blue_p.shape == (16,)
        # 概率和应为 1
        np.testing.assert_allclose(red_p.sum(), 1.0, rtol=1e-5)
        np.testing.assert_allclose(blue_p.sum(), 1.0, rtol=1e-5)
        # 所有概率非负
        assert np.all(red_p >= 0)
        assert np.all(blue_p >= 0)

    def test_predict_proba_different_lookback(self):
        model = MarkovChainModel(order=1)
        red_sequences = [[1, 2, 3, 4, 5, 6]] * 30
        blue_sequences = [1] * 30
        model.fit(red_sequences, blue_sequences, red_count=10, blue_count=5)
        red_p1, blue_p1 = model.predict_proba(lookback=5)
        red_p2, blue_p2 = model.predict_proba(lookback=20)
        assert red_p1.shape == red_p2.shape
        assert blue_p1.shape == blue_p2.shape
        # 不同 lookback 可能产生不同结果（但都是有效概率分布）

    def test_to_binary_sequence(self):
        model = MarkovChainModel()
        sequences = [[1, 3, 5], [2, 4]]
        result = model._to_binary_sequence(sequences, size=6)
        assert len(result) == 2
        assert result[0].shape == (6,)
        # 第一个序列：1,3,5 -> index 0,2,4 = 1
        assert result[0][0] == 1.0
        assert result[0][2] == 1.0
        assert result[0][4] == 1.0
        assert result[0][1] == 0.0
        assert result[0][3] == 0.0
        assert result[0][5] == 0.0

    def test_to_onehot_sequence(self):
        model = MarkovChainModel()
        sequences = [1, 3, 5]
        result = model._to_onehot_sequence(sequences, size=6)
        assert len(result) == 3
        for vec in result:
            assert vec.shape == (6,)
        assert result[0][0] == 1.0
        assert result[1][2] == 1.0
        assert result[2][4] == 1.0

    def test_build_transition_properties(self):
        model = MarkovChainModel(order=1)
        # 使用足够数据
        red_sequences = [[i % 6 + 1 for i in range(6)] for _ in range(30)]
        blue_sequences = [i % 5 + 1 for i in range(30)]
        model.fit(red_sequences, blue_sequences, red_count=6, blue_count=5)
        # 转移矩阵每行和为 1
        for row in model.red_transition:
            np.testing.assert_allclose(row.sum(), 1.0, rtol=1e-5)
        for row in model.blue_transition:
            np.testing.assert_allclose(row.sum(), 1.0, rtol=1e-5)
        # 初始概率和为 1
        np.testing.assert_allclose(model.red_initial.sum(), 1.0, rtol=1e-5)
        np.testing.assert_allclose(model.blue_initial.sum(), 1.0, rtol=1e-5)

    def test_smoothing_effect(self):
        # 平滑参数影响：大平滑 -> 更接近均匀
        model_low = MarkovChainModel(order=1)
        model_high = MarkovChainModel(order=1)
        red_sequences = [[1, 2, 3]] * 20
        blue_sequences = [1] * 20
        model_low.fit(red_sequences, blue_sequences, red_count=5, blue_count=3, smoothing=0.001)
        model_high.fit(red_sequences, blue_sequences, red_count=5, blue_count=3, smoothing=0.5)
        # 高平滑下分布更均匀（熵更大或方差更小）
        var_low = np.var(model_low.red_transition)
        var_high = np.var(model_high.red_transition)
        assert var_high <= var_low + 1e-6  # 允许数值误差