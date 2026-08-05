"""红球 LSTM 预测模型（优化版）."""

from __future__ import annotations

import logging
import pickle
from pathlib import Path

import numpy as np

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


class RedBallLSTM:
    """红球 LSTM 模型."""

    RED_COUNT = 33
    SEQ_LEN = 20

    def __init__(self, seq_len: int = 20, hidden_size: int = 128, num_layers: int = 2):
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
        from torch import nn

        self._device = torch.device("cpu")

        class LSTMModel(nn.Module):
            def __init__(self, red_count, hidden_size, num_layers):
                super().__init__()
                input_size = red_count + 5
                self.lstm = nn.LSTM(input_size, hidden_size, num_layers,
                                    batch_first=True, dropout=0.2)
                self.fc1 = nn.Linear(hidden_size, hidden_size // 2)
                self.relu = nn.ReLU()
                self.dropout = nn.Dropout(0.2)
                self.fc2 = nn.Linear(hidden_size // 2, red_count)
                self.sigmoid = nn.Sigmoid()

            def forward(self, x):
                lstm_out, _ = self.lstm(x)
                out = self.fc1(lstm_out[:, -1, :])
                out = self.relu(out)
                out = self.dropout(out)
                out = self.fc2(out)
                return self.sigmoid(out)

        self.model = LSTMModel(self.RED_COUNT, self.hidden_size, self.num_layers).to(self._device)

    def _encode_reds_batch(self, red_records: list[list[int]]) -> np.ndarray:
        """批量编码红球记录为 one-hot 矩阵 (n, 33)."""
        n = len(red_records)
        mat = np.zeros((n, self.RED_COUNT), dtype=np.float32)
        for i, reds in enumerate(red_records):
            for num in reds:
                if 1 <= num <= self.RED_COUNT:
                    mat[i, num - 1] = 1.0
        return mat

    def _compute_missing_features_batch(self, encoded_matrix: np.ndarray) -> np.ndarray:
        """向量化计算遗漏特征，输入 (seq_len, 33)，输出 (5,)."""
        n = encoded_matrix.shape[0]
        missing = np.ones(self.RED_COUNT, dtype=np.float32)
        for num in range(self.RED_COUNT):
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
            (missing > 0.5).sum() / self.RED_COUNT,
        ], dtype=np.float32)

    def _build_sequences(self, red_records: list[list[int]]) -> tuple[np.ndarray, np.ndarray]:
        """向量化构建训练数据."""
        n = len(red_records)
        if n < self.seq_len + 1:
            return np.array([]), np.array([])

        # 一次性编码所有记录
        all_encoded = self._encode_reds_batch(red_records)  # (n, 33)

        total_samples = n - self.seq_len
        X = np.zeros((total_samples, self.seq_len, self.RED_COUNT + 5), dtype=np.float32)
        y = np.zeros((total_samples, self.RED_COUNT), dtype=np.float32)

        for i in range(total_samples):
            start = i
            end = i + self.seq_len
            seq_encoded = all_encoded[start:end]  # (seq_len, 33)
            missing_feat = self._compute_missing_features_batch(seq_encoded)
            X[i, :, :self.RED_COUNT] = seq_encoded
            X[i, :, self.RED_COUNT:] = np.tile(missing_feat, (self.seq_len, 1))
            y[i] = all_encoded[end]

        return X, y

    def train(self, red_records: list[list[int]], epochs: int = 50, lr: float = 0.001,
              progress_callback=None):
        """训练模型."""
        import torch
        from torch import nn
        from torch.utils.data import DataLoader, TensorDataset

        X, y = self._build_sequences(red_records)
        if len(X) == 0:
            logger.warning("红球 LSTM 训练数据不足")
            return

        if progress_callback:
            progress_callback(f"红球LSTM: 准备数据 ({len(X)} 样本)")

        X_tensor = torch.FloatTensor(X).to(self._device)
        y_tensor = torch.FloatTensor(y).to(self._device)
        dataset = TensorDataset(X_tensor, y_tensor)
        loader = DataLoader(dataset, batch_size=128, shuffle=True)

        optimizer = torch.optim.Adam(self.model.parameters(), lr=lr)
        criterion = nn.BCELoss()

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
                    progress_callback(f"红球LSTM: epoch {epoch+1}/{epochs}, loss={avg_loss:.4f}")
                logger.info("红球 LSTM epoch %d/%d, loss=%.4f", epoch + 1, epochs, avg_loss)

        self.is_trained = True
        if progress_callback:
            progress_callback("红球LSTM: 训练完成")
        logger.info("红球 LSTM 训练完成")

    def predict(self, recent_draws: list[list[int]]) -> np.ndarray:
        """预测下一期各红球出现概率."""
        import torch

        if not self.is_trained:
            raise RuntimeError("模型尚未训练")

        if len(recent_draws) < self.seq_len:
            recent_draws = [[] for _ in range(self.seq_len - len(recent_draws))] + recent_draws

        seq = recent_draws[-self.seq_len:]
        encoded = self._encode_reds_batch(seq)
        missing_feat = self._compute_missing_features_batch(encoded)
        combined = np.concatenate([encoded, np.tile(missing_feat, (self.seq_len, 1))], axis=1)

        self.model.eval()
        with torch.no_grad():
            x = torch.FloatTensor(combined).unsqueeze(0).to(self._device)
            proba = self.model(x).cpu().numpy().flatten()
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
    def load(cls, path: Path) -> RedBallLSTM:
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
