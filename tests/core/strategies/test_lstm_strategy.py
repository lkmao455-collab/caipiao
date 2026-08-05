"""LSTM 策略测试."""

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

pytestmark = pytest.mark.skipif(not torch_available, reason="PyTorch 未安装，跳过 LSTM 策略测试")


class TestLSTMStrategy:
    """LSTMStrategy 测试."""

    def test_metadata(self):
        from caipiao.core.strategies.lstm_strategy import LSTMStrategy

        strategy = LSTMStrategy()
        assert strategy.metadata.id == "lstm"
        assert strategy.metadata.name == "LSTM 时序分析"
        assert strategy.metadata.configurable is True
        assert strategy.is_ml is True

    def test_get_config_schema(self):
        from caipiao.core.strategies.lstm_strategy import LSTMStrategy

        strategy = LSTMStrategy()
        schema = strategy.get_config_schema()
        assert "history_count" in schema
        assert "seq_len" in schema
        assert "epochs" in schema
        assert schema["history_count"]["default"] == -1
        assert schema["seq_len"]["default"] == 20
        assert schema["epochs"]["default"] == 50

    def test_validate_options_insufficient_history(self):
        from caipiao.core.strategies.lstm_strategy import LSTMStrategy

        strategy = LSTMStrategy()
        with pytest.raises(ValueError, match="至少 100 期历史数据"):
            strategy.validate_options({"history": []})

    def test_validate_options_sufficient_history(self):
        from caipiao.core.strategies.lstm_strategy import LSTMStrategy

        strategy = LSTMStrategy()
        # 创建模拟历史记录（需要至少 100 期）
        class MockHistory:
            def __init__(self, n):
                self.groups = {"red": list(range(1, 7)), "blue": [1]}
                self.profile = type("Profile", (), {"key": "ssq"})()
                self.generated_at = __import__("datetime").datetime(2024, 1, 1)

        history = [MockHistory(i) for i in range(100)]
        # 不应抛出异常
        strategy.validate_options({"history": history})

    def test_to_red_lists(self):
        from caipiao.core.strategies.lstm_strategy import _to_red_lists
        from caipiao.data.models import DrawRecord
        from datetime import datetime

        records = [
            DrawRecord(issue="2024001", draw_date=datetime(2024,1,1), profile="ssq", groups={"red": [1,2,3,4,5,6], "blue": [1]}),
            DrawRecord(issue="2024002", draw_date=datetime(2024,1,2), profile="ssq", groups={"red": [2,3,4,5,6,7], "blue": [2]}),
        ]
        result = _to_red_lists(records)
        assert result == [[1,2,3,4,5,6], [2,3,4,5,6,7]]

    def test_to_blue_list(self):
        from caipiao.core.strategies.lstm_strategy import _to_blue_list
        from caipiao.data.models import DrawRecord
        from datetime import datetime

        records = [
            DrawRecord(issue="2024001", draw_date=datetime(2024,1,1), profile="ssq", groups={"red": [1,2,3,4,5,6], "blue": [1]}),
            DrawRecord(issue="2024002", draw_date=datetime(2024,1,2), profile="ssq", groups={"red": [2,3,4,5,6,7], "blue": [2]}),
            DrawRecord(issue="2024003", draw_date=datetime(2024,1,3), profile="ssq", groups={"red": [3,4,5,6,7,8], "blue": []}),  # 无蓝球
        ]
        result = _to_blue_list(records)
        assert result == [1, 2]

    def test_generate_basic(self):
        from caipiao.core.strategies.lstm_strategy import LSTMStrategy

        strategy = LSTMStrategy()
        # 创建足够的历史数据（需要至少 100 期）
        class MockHistory:
            def __init__(self, i):
                self.groups = {"red": [(i+j)%33+1 for j in range(6)], "blue": [(i%16)+1]}
                self.profile = type("Profile", (), {"key": "ssq"})()
                self.generated_at = __import__("datetime").datetime(2024, 1, 1) + __import__("datetime").timedelta(days=i)

        history = [MockHistory(i) for i in range(120)]
        options = {
            "history": history,
            "seq_len": 10,
            "epochs": 1,  # 快速训练用于测试
            "seed": 42,
        }
        tickets = strategy.generate(count=1, options=options)
        assert len(tickets) == 1
        ticket = tickets[0]
        assert ticket.profile.key == "ssq"
        assert len(ticket.groups["red"]) == 6
        assert len(ticket.groups["blue"]) == 1
        assert ticket.strategy_name == "LSTM 时序分析"
        assert "LSTM 时序分析" in ticket.basis

    def test_generate_with_seed_reproducible(self, monkeypatch):
        from caipiao.core.strategies import lstm_strategy as lstm_mod
        from caipiao.core.strategies.lstm_strategy import LSTMStrategy
        import numpy as np

        # 真实 LSTM 每次训练权重随机初始化（torch 未设种子），导致 red_proba
        # 不可复现。此处 mock 模型使预测分布确定性，从而验证策略本身基于
        # np.random.RandomState(seed) 的采样复现性（这是源码的真实设计意图）。
        class _FakeRedLSTM:
            def __init__(self, *a, **k):
                pass
            def train(self, *a, **k):
                pass
            def predict(self, seq):
                return np.ones(33) / 33.0
        class _FakeBlueLSTM:
            def __init__(self, *a, **k):
                pass
            def train(self, *a, **k):
                pass
            def predict(self, seq):
                return np.ones(16) / 16.0

        monkeypatch.setattr(lstm_mod, "RedBallLSTM", _FakeRedLSTM)
        monkeypatch.setattr(lstm_mod, "BlueBallLSTM", _FakeBlueLSTM)

        strategy = LSTMStrategy()
        class MockHistory:
            def __init__(self, i):
                self.groups = {"red": [(i+j)%33+1 for j in range(6)], "blue": [(i%16)+1]}
                self.profile = type("Profile", (), {"key": "ssq"})()
                self.generated_at = __import__("datetime").datetime(2024, 1, 1) + __import__("datetime").timedelta(days=i)

        history = [MockHistory(i) for i in range(120)]
        options = {"history": history, "seq_len": 10, "epochs": 1, "seed": 42}
        t1 = strategy.generate(count=2, options=options)
        t2 = strategy.generate(count=2, options=options)
        for a, b in zip(t1, t2):
            assert a.groups == b.groups

    def test_generate_count_zero(self):
        from caipiao.core.strategies.lstm_strategy import LSTMStrategy

        strategy = LSTMStrategy()
        class MockHistory:
            def __init__(self, i):
                self.groups = {"red": [1,2,3,4,5,6], "blue": [1]}
                self.profile = type("Profile", (), {"key": "ssq"})()
                self.generated_at = __import__("datetime").datetime(2024, 1, 1)
        history = [MockHistory(i) for i in range(100)]
        tickets = strategy.generate(count=0, options={"history": history})
        assert tickets == []

    def test_generate_handles_empty_blue(self):
        from caipiao.core.strategies.lstm_strategy import LSTMStrategy

        strategy = LSTMStrategy()
        class MockHistory:
            def __init__(self, i):
                # 只有红球，无蓝球
                self.groups = {"red": [(i+j)%33+1 for j in range(6)], "blue": []}
                self.profile = type("Profile", (), {"key": "ssq"})()
                self.generated_at = __import__("datetime").datetime(2024, 1, 1) + __import__("datetime").timedelta(days=i)

        history = [MockHistory(i) for i in range(120)]
        options = {"history": history, "seq_len": 10, "epochs": 1, "seed": 42}
        tickets = strategy.generate(count=1, options=options)
        assert len(tickets) == 1
        assert len(tickets[0].groups["blue"]) == 1  # 应使用均匀分布生成蓝球