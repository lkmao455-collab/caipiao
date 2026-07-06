"""蓝球 LSTM 预测模型（优化版）."""

from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import List, Tuple

import numpy as np

logger = logging.getLogger(__name__)

_torch_available = None


def _ensure_torch():
    global _torch_available
    if _torch_available is None:
        try:
            import torch
            _torch_available = True
        except ImportError:
            _torch_available = False
    if not _torch_available:
        raise ImportError("需要安装 PyTorch: pip install torch")


class BlueBallLSTM:
    """蓝球 LSTM 模型."""

    BLUE_COUNT = 16
    SEQ_LEN = 20

    def __init__(self, seq_len: int = 20, hidden_size: int = 64, num_layers: int = 2):
        _ensure_torch()
        self.seq_len = seq_len
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.is_trained = False
        self.model = None
        self._device = None
        self._build_model()

    def _build_model(self):
        import torch
        import torch.nn as nn

        self._device = torch.device("cpu")

        class LSTMModel(nn.Module):
            def __init__(self, blue_count, hidden_size, num_layers):
                super().__init__()
                input_size = blue_count + 5
                self.lstm = nn.LSTM(input_size, hidden_size, num_layers,
                                    batch_first=True, dropout=0.2)
                self.fc = nn.Linear(hidden_size, blue_count)

            def forward(self, x):
                lstm_out, _ = self.lstm(x)
                out = self.fc(lstm_out[:, -1, :])
                return out

        self.model = LSTMModel(self.BLUE_COUNT, self.hidden_size, self.num_layers).to(self._device)

    def _encode_blue_batch(self, blue_list: List[int]) -> np.ndarray:
        """批量编码蓝球为 one-hot 矩阵 (n, 16)."""
        n = len(blue_list)
        mat = np.zeros((n, self.BLUE_COUNT), dtype=np.float32)
        for i, num in enumerate(blue_list):
            if 1 <= num <= self.BLUE_COUNT:
                mat[i, num - 1] = 1.0
        return mat

    def _compute_missing_features(self, encoded_matrix: np.ndarray) -> np.ndarray:
        """向量化计算遗漏特征."""
        n = encoded_matrix.shape[0]
        missing = np.ones(self.BLUE_COUNT, dtype=np.float32)
        for num in range(self.BLUE_COUNT):
            col = encoded_matrix[:, num]
            last_idx = -1
            for i in range(n - 1, -1, -1):
                if col[i] > 0:
                    last_idx = i
                    break
            if last_idx >= 0:
                missing[num] = (n - 1 - last_idx) / max(n, 1)
        return np.array([
            missing.mean(), missing.std(), missing.max(), missing.min(),
            (missing > 0.5).sum() / self.BLUE_COUNT,
        ], dtype=np.float32)

    def _build_sequences(self, blue_list: List[int]) -> Tuple[np.ndarray, np.ndarray]:
        """向量化构建训练数据."""
        n = len(blue_list)
        if n < self.seq_len + 1:
            return np.array([]), np.array([])

        all_encoded = self._encode_blue_batch(blue_list)
        total_samples = n - self.seq_len
        X = np.zeros((total_samples, self.seq_len, self.BLUE_COUNT + 5), dtype=np.float32)
        y = np.zeros(total_samples, dtype=np.int64)

        for i in range(total_samples):
            seq_encoded = all_encoded[i:i + self.seq_len]
            missing_feat = self._compute_missing_features(seq_encoded)
            X[i, :, :self.BLUE_COUNT] = seq_encoded
            X[i, :, self.BLUE_COUNT:] = np.tile(missing_feat, (self.seq_len, 1))
            y[i] = blue_list[i + self.seq_len] - 1  # 类别索引 0-15

        return X, y

    def train(self, blue_list: List[int], epochs: int = 50, lr: float = 0.001,
              progress_callback=None):
        """训练 LSTM 模型."""
        import torch
        import torch.nn as nn
        from torch.utils.data import DataLoader, TensorDataset

        X, y = self._build_sequences(blue_list)
        if len(X) == 0:
            logger.warning("蓝球 LSTM 训练数据不足")
            return

        if progress_callback:
            progress_callback(f"蓝球LSTM: 准备数据 ({len(X)} 样本)")

        X_tensor = torch.FloatTensor(X).to(self._device)
        y_tensor = torch.LongTensor(y).to(self._device)
        dataset = TensorDataset(X_tensor, y_tensor)
        loader = DataLoader(dataset, batch_size=128, shuffle=True)

        optimizer = torch.optim.Adam(self.model.parameters(), lr=lr)
        criterion = nn.CrossEntropyLoss()

        self.model.train()
        for epoch in range(epochs):
            total_loss = 0
            for batch_X, batch_y in loader:
                optimizer.zero_grad()
                output = self.model(batch_X)
                loss = criterion(output, batch_y)
                loss.backward()
                optimizer.step()
                total_loss += loss.item()
            if (epoch + 1) % 10 == 0:
                avg_loss = total_loss / len(loader)
                if progress_callback:
                    progress_callback(f"蓝球LSTM: epoch {epoch+1}/{epochs}, loss={avg_loss:.4f}")
                logger.info("蓝球 LSTM epoch %d/%d, loss=%.4f", epoch + 1, epochs, avg_loss)

        self.is_trained = True
        if progress_callback:
            progress_callback("蓝球LSTM: 训练完成")
        logger.info("蓝球 LSTM 训练完成")

    def predict(self, blue_sequence: List[int]) -> np.ndarray:
        """预测下一期蓝球概率分布."""
        import torch

        if not self.is_trained:
            raise RuntimeError("模型尚未训练")

        if len(blue_sequence) < self.seq_len:
            blue_sequence = [0] * (self.seq_len - len(blue_sequence)) + blue_sequence

        seq = blue_sequence[-self.seq_len:]
        encoded = self._encode_blue_batch(seq)
        missing_feat = self._compute_missing_features(encoded)
        combined = np.concatenate([encoded, np.tile(missing_feat, (self.seq_len, 1))], axis=1)

        self.model.eval()
        with torch.no_grad():
            x = torch.FloatTensor(combined).unsqueeze(0).to(self._device)
            logits = self.model(x)
            proba = torch.softmax(logits, dim=-1).cpu().numpy().flatten()
        return proba

    def save(self, path: Path):
        data = {
            "model_state": self.model.state_dict(),
            "seq_len": self.seq_len,
            "hidden_size": self.hidden_size,
            "num_layers": self.num_layers,
            "is_trained": self.is_trained,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            pickle.dump(data, f)

    @classmethod
    def load(cls, path: Path) -> "BlueBallLSTM":
        with path.open("rb") as f:
            data = pickle.load(f)
        instance = cls(
            seq_len=data["seq_len"],
            hidden_size=data["hidden_size"],
            num_layers=data["num_layers"],
        )
        instance.model.load_state_dict(data["model_state"])
        instance.is_trained = data["is_trained"]
        return instance
