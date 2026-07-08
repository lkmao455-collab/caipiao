"""Transformer 时序预测策略 - 支持双色球和福彩3D.

使用可训练的 Transformer Encoder 模型学习历史 one-hot 序列到下一期号码
概率的映射。与原来的随机权重实现不同，本实现会在每次生成时基于传入的
历史数据训练一个轻量 Transformer，然后输出概率供上层做不放回加权采样。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ....data.models import DrawRecord
from ...profile import LotteryProfile, SSQ
from .base import _AdvancedBase

logger = logging.getLogger(__name__)

_torch_available = None


def _ensure_torch():
    global _torch_available
    if _torch_available is None:
        try:
            import torch  # noqa: F401
            _torch_available = True
        except ImportError:
            _torch_available = False
    if not _torch_available:
        raise ImportError("需要安装 PyTorch: pip install torch")


class _SimpleTransformer:
    """轻量 Transformer 模型封装，训练与预测一体化."""

    def __init__(self, size: int, d_model: int, seq_len: int,
                 nhead: int = 4, num_layers: int = 2, epochs: int = 20,
                 lr: float = 0.001, batch_size: int = 32) -> None:
        _ensure_torch()
        import torch
        import torch.nn as nn

        self.size = size
        self.d_model = d_model
        self.seq_len = seq_len
        self.epochs = epochs
        self.lr = lr
        self.batch_size = batch_size
        self._device = torch.device("cpu")

        class TransformerModel(nn.Module):
            def __init__(self, input_size, d_model, nhead, num_layers):
                super().__init__()
                self.embedding = nn.Linear(input_size, d_model)
                layer = nn.TransformerEncoderLayer(
                    d_model=d_model, nhead=nhead, dropout=0.1, batch_first=True
                )
                self.encoder = nn.TransformerEncoder(layer, num_layers=num_layers)
                self.fc = nn.Linear(d_model, input_size)
                self.sigmoid = nn.Sigmoid()

            def forward(self, x):
                x = self.embedding(x)
                x = self.encoder(x)
                x = x[:, -1, :]
                x = self.fc(x)
                return self.sigmoid(x)

        self.model = TransformerModel(size, d_model, nhead, num_layers).to(self._device)
        self._is_trained = False

    def fit(self, sequences: List[np.ndarray]) -> None:
        """训练模型.

        sequences: 按时间排序的每期 one-hot 向量列表。
        """
        import torch
        import torch.nn as nn
        from torch.utils.data import DataLoader, TensorDataset

        if len(sequences) <= self.seq_len:
            logger.warning("Transformer 训练数据不足")
            return

        X_list, y_list = [], []
        for i in range(len(sequences) - self.seq_len):
            X_list.append(np.array(sequences[i:i + self.seq_len], dtype=np.float32))
            y_list.append(np.array(sequences[i + self.seq_len], dtype=np.float32))
        X_arr = np.array(X_list, dtype=np.float32)
        y_arr = np.array(y_list, dtype=np.float32)

        X_tensor = torch.FloatTensor(X_arr).to(self._device)
        y_tensor = torch.FloatTensor(y_arr).to(self._device)
        dataset = TensorDataset(X_tensor, y_tensor)
        loader = DataLoader(dataset, batch_size=self.batch_size, shuffle=True)

        optimizer = torch.optim.Adam(self.model.parameters(), lr=self.lr)
        criterion = nn.BCELoss()

        self.model.train()
        for epoch in range(self.epochs):
            total_loss = 0.0
            for batch_x, batch_y in loader:
                optimizer.zero_grad()
                output = self.model(batch_x)
                loss = criterion(output, batch_y)
                loss.backward()
                optimizer.step()
                total_loss += loss.item()
            if (epoch + 1) % 5 == 0:
                logger.info("Transformer epoch %d/%d, loss=%.4f", epoch + 1, self.epochs, total_loss / max(len(loader), 1))

        self._is_trained = True

    def predict(self, recent_sequences: List[np.ndarray]) -> np.ndarray:
        """预测下一期各号码出现概率."""
        import torch

        if not self._is_trained:
            raise RuntimeError("模型尚未训练")

        seq = recent_sequences[-self.seq_len:]
        if len(seq) < self.seq_len:
            seq = [np.zeros(self.size, dtype=np.float32)] * (self.seq_len - len(seq)) + seq
        x = torch.FloatTensor(np.array([seq], dtype=np.float32)).to(self._device)
        self.model.eval()
        with torch.no_grad():
            proba = self.model(x).cpu().numpy().flatten()
        return proba


class TransformerStrategy(_AdvancedBase):
    """基于 Transformer 自注意力机制的时序预测策略."""

    _id_base = "transformer"
    _name_base = "Transformer 时序预测"
    _description = "基于可训练 Transformer Encoder 学习历史 one-hot 序列规律，输出下一期号码概率。"

    def __init__(self, profile: LotteryProfile | None = None) -> None:
        super().__init__(profile)

    def get_config_schema(self) -> Dict[str, Any]:
        schema = super().get_config_schema()
        schema.update({
            "seq_len": {
                "type": "int",
                "label": "输入序列长度",
                "default": 20,
                "min": 10,
                "max": 50,
            },
            "d_model": {
                "type": "int",
                "label": "模型维度",
                "default": 64,
                "min": 32,
                "max": 128,
            },
            "epochs": {
                "type": "int",
                "label": "训练轮数",
                "default": 20,
                "min": 5,
                "max": 100,
            },
        })
        return schema

    def _compute_probabilities(
        self, records: List[DrawRecord], options: Dict[str, Any]
    ) -> Tuple[np.ndarray, str]:
        seq_len = int(options.get("seq_len", 20))
        d_model = int(options.get("d_model", 64))
        epochs = int(options.get("epochs", 20))

        group = self._profile.primary_group
        size = group.hi - group.lo + 1
        pick = group.count

        sequences = []
        for r in records:
            vec = np.zeros(size, dtype=np.float64)
            for n in r.groups.get(group.key, []):
                if group.lo <= n <= group.hi:
                    vec[n - group.lo] = 1.0
            sequences.append(vec)

        if len(sequences) < seq_len:
            proba = np.ones(size) / size
            if group.positional:
                proba = np.tile(proba, (pick, 1))
            basis = f"Transformer（{self._profile.name}）：数据不足，使用均匀概率。注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
            return proba, basis

        nhead = 4
        # d_model 必须能被 nhead 整除
        d_model = (d_model // nhead) * nhead
        if d_model < nhead:
            d_model = nhead

        transformer = _SimpleTransformer(
            size=size,
            d_model=d_model,
            seq_len=seq_len,
            nhead=nhead,
            num_layers=2,
            epochs=epochs,
            batch_size=32,
        )
        transformer.fit(sequences)
        proba = transformer.predict(sequences)

        s = proba.sum()
        if s > 0:
            proba = proba / s
        else:
            proba = np.ones(size) / size

        if group.positional:
            proba = np.tile(proba, (pick, 1))

        basis = f"Transformer（{self._profile.name}）：序列长度 {seq_len}，模型维度 {d_model}，训练 {epochs} 轮。注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
        return proba, basis
