"""Transformer 模型训练与预测（顺序组合生成版）.

为双色球红球建模为不放回顺序生成问题：
给定历史窗口特征和已选红球，预测下一个红球号码。
蓝球仍按 16 个二分类器建模（每期只开 1 个蓝球）。
"""

from __future__ import annotations

import logging
import pickle
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import torch
from torch import nn

if TYPE_CHECKING:
    from sklearn.preprocessing import LabelEncoder

logger = logging.getLogger(__name__)

RED_COUNT = 33
BLUE_COUNT = 16
RED_PICK = 6


class LotteryTransformerModel:
    """基于 Transformer 的彩票号码分析模型.

    红球：顺序生成模型，输入包含历史特征、已选红球 mask、当前步数。
    蓝球：为每个蓝球训练二分类器，输出下一期出现的概率。
    """

    def __init__(self, lookback: int = 50, temp_dir: str | None = None) -> None:
        self.lookback = lookback
        self.temp_dir = temp_dir
        self.red_sequence_model = None
        self.red_sequence_encoder = None
        self.blue_model = None
        self._base_feature_dim: int | None = None
        self.is_trained = False
        self._device = None
        self._torch_available = False
        self._check_torch()

    def _check_torch(self) -> None:
        """检查 PyTorch 是否可用."""
        try:
            import torch
            self._torch_available = True
            self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            logger.info("Transformer 模型使用设备: %s", self._device)
        except ImportError:
            self._torch_available = False
            logger.warning("PyTorch 未安装，Transformer 模型不可用")

    def _build_sequence_input(
        self, base_x: np.ndarray, mask: np.ndarray, step: int
    ) -> np.ndarray:
        """构造红球顺序生成模型的一个输入向量."""
        step_norm = step / max(RED_PICK - 1, 1)
        return np.concatenate([base_x.flatten(), mask, [step_norm]]).astype(np.float32)

    def _build_sequence_training_data(
        self, X: np.ndarray, y_red: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, LabelEncoder]:
        """从 one-hot 红球标签构造顺序生成训练数据."""
        from sklearn.preprocessing import LabelEncoder

        X_seq: list[np.ndarray] = []
        y_seq: list[int] = []
        for i in range(X.shape[0]):
            nums = [idx for idx, val in enumerate(y_red[i]) if val]
            nums.sort()
            mask = np.zeros(RED_COUNT, dtype=np.float32)
            for step, num_idx in enumerate(nums):
                X_seq.append(self._build_sequence_input(X[i], mask, step))
                y_seq.append(num_idx)
                mask[num_idx] = 1.0
        encoder = LabelEncoder()
        y_enc = encoder.fit_transform(y_seq)
        return np.array(X_seq), y_enc, encoder

    def _create_transformer_classifier(self, input_dim: int, num_class: int):
        """创建 Transformer 分类器."""
        if not self._torch_available:
            raise RuntimeError("PyTorch 未安装，无法创建 Transformer 模型")

        import torch

        class TransformerClassifier(nn.Module):
            def __init__(self, input_dim: int, num_class: int):
                super().__init__()
                self.embedding = nn.Linear(input_dim, 128)
                self.pos_encoding = nn.Parameter(torch.randn(1, 1, 128) * 0.1)
                encoder_layer = nn.TransformerEncoderLayer(
                    d_model=128, nhead=4, dim_feedforward=256, dropout=0.1, batch_first=True
                )
                self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=2)
                self.classifier = nn.Linear(128, num_class)

            def forward(self, x):
                if x.dim() == 2:
                    x = x.unsqueeze(1)
                x = self.embedding(x) + self.pos_encoding
                x = self.transformer(x)
                x = x.mean(dim=1)
                return self.classifier(x)

        return TransformerClassifier(input_dim, num_class)

    def _create_binary_classifier(self, input_dim: int):
        """创建二分类器（用于蓝球）."""
        if not self._torch_available:
            raise RuntimeError("PyTorch 未安装，无法创建 Transformer 模型")


        class BinaryClassifier(nn.Module):
            def __init__(self, input_dim: int):
                super().__init__()
                self.embedding = nn.Linear(input_dim, 128)
                self.pos_encoding = nn.Parameter(torch.randn(1, 1, 128) * 0.1)
                encoder_layer = nn.TransformerEncoderLayer(
                    d_model=128, nhead=4, dim_feedforward=256, dropout=0.1, batch_first=True
                )
                self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=2)
                self.classifier = nn.Linear(128, 1)

            def forward(self, x):
                if x.dim() == 2:
                    x = x.unsqueeze(1)
                x = self.embedding(x) + self.pos_encoding
                x = self.transformer(x)
                x = x.mean(dim=1)
                return self.classifier(x)

        return BinaryClassifier(input_dim)

    def fit(
        self,
        X: np.ndarray,
        y_red: np.ndarray,
        y_blue: np.ndarray,
        progress_callback: Callable[[int, int], None] | None = None,
        incremental: bool = False,
    ) -> None:
        """训练模型."""
        if not self._torch_available:
            raise RuntimeError("PyTorch 未安装，无法训练 Transformer 模型")

        import torch
        from torch.utils.data import DataLoader, TensorDataset

        if X.shape[0] == 0:
            raise ValueError("训练数据为空")
        if y_red.ndim != 2 or y_blue.ndim != 2:
            raise ValueError("y_red/y_blue 必须是二维数组")
        self._base_feature_dim = X.shape[1]

        total = 2  # 红球顺序模型 + 蓝球多输出模型

        # 训练红球顺序生成模型
        X_seq, y_seq, encoder = self._build_sequence_training_data(X, y_red)
        num_class = len(encoder.classes_)
        input_dim = X_seq.shape[1]

        self.red_sequence_model = self._create_transformer_classifier(input_dim, num_class)
        self.red_sequence_model.to(self._device)
        self.red_sequence_encoder = encoder

        # 训练红球模型
        X_tensor = torch.FloatTensor(X_seq).to(self._device)
        y_tensor = torch.LongTensor(y_seq).to(self._device)
        dataset = TensorDataset(X_tensor, y_tensor)
        dataloader = DataLoader(dataset, batch_size=64, shuffle=True)

        optimizer = torch.optim.Adam(self.red_sequence_model.parameters(), lr=0.001)
        criterion = nn.CrossEntropyLoss()

        self.red_sequence_model.train()
        for epoch in range(50):
            for batch_x, batch_y in dataloader:
                optimizer.zero_grad()
                output = self.red_sequence_model(batch_x)
                loss = criterion(output, batch_y)
                loss.backward()
                optimizer.step()

        if progress_callback is not None:
            progress_callback(1, total)
        logger.debug("红球顺序生成模型训练完成")

        # 训练蓝球多输出分类器
        self.blue_model = []
        X_tensor = torch.FloatTensor(X).to(self._device)

        for i in range(y_blue.shape[1]):
            blue_clf = self._create_binary_classifier(input_dim)
            blue_clf.to(self._device)

            y_tensor = torch.FloatTensor(y_blue[:, i]).to(self._device)
            dataset = TensorDataset(X_tensor, y_tensor)
            dataloader = DataLoader(dataset, batch_size=64, shuffle=True)

            optimizer = torch.optim.Adam(blue_clf.parameters(), lr=0.001)
            criterion = nn.BCEWithLogitsLoss()

            blue_clf.train()
            for epoch in range(50):
                for batch_x, batch_y in dataloader:
                    optimizer.zero_grad()
                    output = blue_clf(batch_x).squeeze()
                    loss = criterion(output, batch_y)
                    loss.backward()
                    optimizer.step()

            self.blue_model.append(blue_clf)

        if progress_callback is not None:
            progress_callback(total, total)

        self.is_trained = True
        logger.info("Transformer 模型训练完成 (%s)", "增量" if incremental else "全量")

    def _predict_sequence_initial(self, X: np.ndarray) -> np.ndarray:
        """预测 step=0 时各红球概率，用于展示."""
        import torch

        if not self.is_trained:
            raise RuntimeError("模型尚未训练")

        mask = np.zeros(RED_COUNT, dtype=np.float32)
        x = self._build_sequence_input(X, mask, 0).reshape(1, -1)
        x_tensor = torch.FloatTensor(x).to(self._device)

        self.red_sequence_model.eval()
        with torch.no_grad():
            pred = self.red_sequence_model(x_tensor).cpu().numpy()[0]

        encoder = self.red_sequence_encoder
        full = np.full(RED_COUNT, 0.05 / RED_COUNT, dtype=np.float32)
        for idx, cls in enumerate(encoder.classes_):
            full[int(cls)] = max(pred[idx], 0.0)
        full = full / full.sum()
        return full

    def predict_proba(
        self, X: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        """预测下一期各号码出现概率.

        Returns:
            red_proba: 33 个红球初始概率（step=0）
            blue_proba: 16 个蓝球概率
        """
        import torch

        if not self.is_trained:
            raise RuntimeError("模型尚未训练")

        red_proba = self._predict_sequence_initial(X)

        X_tensor = torch.FloatTensor(X).to(self._device)
        blue_proba = []
        for model in self.blue_model:
            model.eval()
            with torch.no_grad():
                pred = model(X_tensor).cpu().numpy()[0]
                prob = 1.0 / (1.0 + np.exp(-pred))  # sigmoid
                blue_proba.append(float(prob))
        blue_proba = np.array(blue_proba)

        return red_proba, blue_proba

    def sample_reds(
        self,
        X_pred: np.ndarray,
        count: int,
        rng: np.random.RandomState,
    ) -> list[int]:
        """使用顺序生成模型采样 count 个不重复红球."""
        import torch

        if not self.is_trained:
            raise RuntimeError("模型尚未训练")

        encoder = self.red_sequence_encoder
        selected: list[int] = []
        mask = np.zeros(RED_COUNT, dtype=np.float32)

        self.red_sequence_model.eval()
        for step in range(count):
            x = self._build_sequence_input(X_pred, mask, step).reshape(1, -1)
            x_tensor = torch.FloatTensor(x).to(self._device)

            with torch.no_grad():
                pred = self.red_sequence_model(x_tensor).cpu().numpy()[0]

            full = np.full(RED_COUNT, 0.05 / RED_COUNT, dtype=np.float32)
            for idx, cls in enumerate(encoder.classes_):
                full[int(cls)] = max(pred[idx], 0.0)
            for idx in selected:
                full[idx] = 0.0
            s = full.sum()
            if s <= 0:
                remaining = [i for i in range(RED_COUNT) if i not in selected]
                full = np.zeros(RED_COUNT, dtype=np.float32)
                for i in remaining:
                    full[i] = 1.0 / max(len(remaining), 1)
            else:
                full = full / s
            next_idx = int(rng.choice(RED_COUNT, p=full))
            selected.append(next_idx)
            mask[next_idx] = 1.0

        return [idx + 1 for idx in selected]

    def save(self, path: Path | str) -> None:
        """保存模型到文件."""

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # 保存 PyTorch 模型状态
        red_state = self.red_sequence_model.state_dict() if self.red_sequence_model else None
        blue_states = [m.state_dict() for m in self.blue_model] if self.blue_model else None

        with path.open("wb") as f:
            pickle.dump(
                {
                    "red_sequence_model_state": red_state,
                    "red_sequence_encoder": self.red_sequence_encoder,
                    "blue_model_states": blue_states,
                    "lookback": self.lookback,
                    "is_trained": self.is_trained,
                    "base_feature_dim": self._base_feature_dim,
                    "input_dim": self.red_sequence_model.embedding.in_features if self.red_sequence_model else None,
                    "num_class": len(self.red_sequence_encoder.classes_) if self.red_sequence_encoder else None,
                },
                f,
            )
        logger.info("Transformer 模型已保存到 %s", path)

    def load(self, path: Path | str) -> None:
        """从文件加载模型."""

        path = Path(path)
        with path.open("rb") as f:
            data = pickle.load(f)

        input_dim = data.get("input_dim")
        num_class = data.get("num_class")

        if input_dim and num_class:
            self.red_sequence_model = self._create_transformer_classifier(input_dim, num_class)
            self.red_sequence_model.to(self._device)
            if data["red_sequence_model_state"]:
                self.red_sequence_model.load_state_dict(data["red_sequence_model_state"])

        self.red_sequence_encoder = data["red_sequence_encoder"]

        if data.get("blue_model_states"):
            self.blue_model = []
            for state in data["blue_model_states"]:
                blue_clf = self._create_binary_classifier(input_dim)
                blue_clf.to(self._device)
                blue_clf.load_state_dict(state)
                self.blue_model.append(blue_clf)

        self.lookback = data["lookback"]
        self.is_trained = data["is_trained"]
        self._base_feature_dim = data.get("base_feature_dim")
        logger.info("Transformer 模型已从 %s 加载", path)
