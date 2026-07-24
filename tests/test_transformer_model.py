"""Transformer 模型测试."""

import pytest
import numpy as np


def _torch_available() -> bool:
    """检查 PyTorch 是否可用."""
    try:
        import torch
        return True
    except ImportError:
        return False


class TestTransformerModel:
    """Transformer 模型基础测试."""

    def test_import(self):
        """测试模块导入."""
        from caipiao.ml.transformer_model import LotteryTransformerModel
        assert LotteryTransformerModel is not None

    def test_torch_availability(self):
        """测试 PyTorch 可用性检查."""
        from caipiao.ml.transformer_model import LotteryTransformerModel
        model = LotteryTransformerModel(lookback=50)
        # 无论 PyTorch 是否安装，都应该能创建模型对象
        assert model is not None
        assert model.lookback == 50

    @pytest.mark.skipif(
        not _torch_available(),
        reason="PyTorch 未安装"
    )
    def test_create_classifier(self):
        """测试创建分类器."""
        from caipiao.ml.transformer_model import LotteryTransformerModel
        model = LotteryTransformerModel(lookback=50)
        clf = model._create_transformer_classifier(input_dim=100, num_class=33)
        assert clf is not None

    @pytest.mark.skipif(
        not _torch_available(),
        reason="PyTorch 未安装"
    )
    def test_create_binary_classifier(self):
        """测试创建二分类器."""
        from caipiao.ml.transformer_model import LotteryTransformerModel
        model = LotteryTransformerModel(lookback=50)
        clf = model._create_binary_classifier(input_dim=100)
        assert clf is not None

    @pytest.mark.skipif(
        not _torch_available(),
        reason="PyTorch 未安装"
    )
    def test_build_sequence_input(self):
        """测试构建序列输入."""
        from caipiao.ml.transformer_model import LotteryTransformerModel
        model = LotteryTransformerModel(lookback=50)
        base_x = np.random.randn(100).astype(np.float32)
        mask = np.zeros(33, dtype=np.float32)
        result = model._build_sequence_input(base_x, mask, 0)
        assert result.shape == (134,)  # 100 + 33 + 1
        assert result.dtype == np.float32

    @pytest.mark.skipif(
        not _torch_available(),
        reason="PyTorch 未安装"
    )
    def test_build_sequence_training_data(self):
        """测试构建序列训练数据."""
        from caipiao.ml.transformer_model import LotteryTransformerModel
        model = LotteryTransformerModel(lookback=50)
        X = np.random.randn(10, 100).astype(np.float32)
        y_red = np.zeros((10, 33), dtype=np.int32)
        for i in range(10):
            nums = np.random.choice(33, 6, replace=False)
            y_red[i, nums] = 1

        X_seq, y_seq, encoder = model._build_sequence_training_data(X, y_red)
        assert X_seq.shape[0] == 60  # 10 samples * 6 red balls
        assert X_seq.shape[1] == 134  # 100 + 33 + 1
        assert len(encoder.classes_) == 33
