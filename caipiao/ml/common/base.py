"""通用机器学习模型（按彩种档案驱动）.

支持任意 NumberGroup 结构：
- 组合组（如双色球红球、快乐8号码）：使用**顺序生成模型**，将不放回抽取
  建模为“给定已选号码，预测下一个号码”的多分类问题，更符合真实开奖机制。
- 单号码组（如双色球蓝球）：为每个候选号码训练二分类器。
- 按位组（如福彩3D）：为每个位置训练一个多分类器。

后端可以是 xgboost、lightgbm 或 catboost。
"""

from __future__ import annotations

import logging
import pickle
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.preprocessing import LabelEncoder

from ...core.profile import LotteryProfile, NumberGroup

logger = logging.getLogger(__name__)


# 后端工厂 -------------------------------------------------------------- #
def _create_xgb_classifier(temp_dir: str | None = None) -> Any:
    import xgboost as xgb

    return xgb.XGBClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        objective="binary:logistic",
        eval_metric="logloss",
        use_label_encoder=False,
        n_jobs=1,
        nthread=1,
        random_state=42,
        verbosity=0,
    )


def _create_lgbm_classifier(temp_dir: str | None = None) -> Any:
    import lightgbm as lgb

    return lgb.LGBMClassifier(
        n_estimators=100,
        max_depth=4,
        num_leaves=15,
        learning_rate=0.1,
        subsample=0.8,
        subsample_freq=1,
        colsample_bytree=0.8,
        objective="binary",
        n_jobs=1,
        num_threads=1,
        random_state=42,
        verbose=-1,
    )


def _create_catboost_classifier(temp_dir: str | None = None) -> Any:
    from catboost import CatBoostClassifier

    return CatBoostClassifier(
        iterations=100,
        depth=4,
        learning_rate=0.1,
        loss_function="Logloss",
        random_seed=42,
        verbose=False,
        thread_count=1,
        train_dir=temp_dir or "catboost_info",
    )


BACKENDS = {
    "xgboost": _create_xgb_classifier,
    "lightgbm": _create_lgbm_classifier,
    "catboost": _create_catboost_classifier,
}


class LotteryGenericModel:
    """基于 Profile 的通用彩票号码分析模型."""

    def __init__(
        self,
        profile: LotteryProfile,
        lookback: int = 50,
        backend: str = "xgboost",
        temp_dir: str | None = None,
    ) -> None:
        self.profile = profile
        self.lookback = lookback
        self.backend = backend
        self.temp_dir = temp_dir
        self.group_models: dict[str, list[Any]] = {}
        self._base_feature_dim: int | None = None
        self.is_trained = False

    def _create_classifier(self, positional: bool = False, num_class: int = 0) -> Any:
        factory = BACKENDS.get(self.backend, _create_xgb_classifier)
        clf = factory(temp_dir=self.temp_dir)
        if positional:
            if num_class <= 1:
                raise ValueError("按位组的 num_class 必须大于 1")
            if self.backend == "xgboost":
                clf.set_params(objective="multi:softprob", num_class=num_class)
            elif self.backend == "catboost":
                clf.set_params(loss_function="MultiClass", classes_count=num_class)
            else:
                clf.set_params(objective="multiclass", num_class=num_class)
        return clf

    @staticmethod
    def _is_combination_group(group: NumberGroup) -> bool:
        """是否需要用顺序生成模型建模不放回组合."""
        return not group.positional and group.count > 1

    def _build_sequence_input(
        self, base_x: np.ndarray, group: NumberGroup, mask: np.ndarray, step: int
    ) -> np.ndarray:
        """构造顺序生成模型的一个输入向量."""
        step_norm = step / max(group.count - 1, 1)
        return np.concatenate([base_x.flatten(), mask, [step_norm]]).astype(np.float32)

    def _build_sequence_training_data(
        self, X: np.ndarray, y: np.ndarray, group: NumberGroup
    ) -> tuple[np.ndarray, np.ndarray, LabelEncoder]:
        """从 one-hot 标签构造顺序生成训练数据.

        对每期开奖，将号码按升序排列，依次生成 count 个子样本：
        输入 = [历史特征, 已选号码 mask, 当前步数]
        标签 = 下一个号码的索引。
        """
        X_seq: list[np.ndarray] = []
        y_seq: list[int] = []
        for i in range(X.shape[0]):
            nums = [idx for idx, val in enumerate(y[i]) if val]
            nums.sort()
            mask = np.zeros(group.size, dtype=np.float32)
            for step, num_idx in enumerate(nums):
                X_seq.append(self._build_sequence_input(X[i], group, mask, step))
                y_seq.append(num_idx)
                mask[num_idx] = 1.0
        encoder = LabelEncoder()
        y_enc = encoder.fit_transform(y_seq)
        return np.array(X_seq), y_enc, encoder

    def fit(
        self,
        X: np.ndarray,
        y_dict: dict[str, np.ndarray],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> None:
        if X.shape[0] == 0:
            raise ValueError("训练数据为空")
        if X.ndim != 2:
            raise ValueError("X 必须是二维数组")
        self._base_feature_dim = X.shape[1]

        total_steps = 0
        plan: list[tuple[str, Any]] = []  # (group_key, task_description)
        for g in self.profile.groups:
            y = y_dict.get(g.key)
            if y is None or y.ndim != 2 or y.shape[0] != X.shape[0]:
                raise ValueError(f"组 {g.key} 标签缺失或维度与 X 不匹配")
            if g.positional:
                total_steps += g.count
                plan.append((g.key, "positional"))
            elif self._is_combination_group(g):
                total_steps += 1
                plan.append((g.key, "sequence"))
            else:
                total_steps += g.size
                plan.append((g.key, "binary"))

        current = 0
        self.group_models = {}
        for g in self.profile.groups:
            y = y_dict[g.key]
            models: list[Any] = []
            if g.positional:
                # 每个位置一个多分类器
                for pos in range(g.count):
                    y_pos = y[:, pos]
                    unique = np.unique(y_pos)
                    if len(unique) == 1:
                        val = int(unique[0])
                        if not (g.lo <= val <= g.hi):
                            raise ValueError(f"按位标签 {val} 超出范围 [{g.lo}, {g.hi}]")
                        const = np.zeros(g.size, dtype=np.float32)
                        const[val - g.lo] = 1.0
                        models.append(const)
                    else:
                        encoder = LabelEncoder()
                        y_enc = encoder.fit_transform(y_pos)
                        num_class = len(encoder.classes_)
                        model = self._create_classifier(positional=True, num_class=num_class)
                        model.fit(X, y_enc)
                        models.append((model, encoder))
                    current += 1
                    if progress_callback:
                        progress_callback(current, total_steps)
            elif self._is_combination_group(g):
                # 顺序生成：一个多分类器
                X_seq, y_seq, encoder = self._build_sequence_training_data(X, y, g)
                if len(X_seq) == 0:
                    raise ValueError(f"组 {g.key} 顺序生成训练数据为空")
                num_class = len(encoder.classes_)
                model = self._create_classifier(positional=True, num_class=num_class)
                model.fit(X_seq, y_seq)
                models.append(("sequence", model, encoder, g.count))
                current += 1
                if progress_callback:
                    progress_callback(current, total_steps)
            else:
                # 每个号码一个二分类器
                for i in range(g.size):
                    y_i = y[:, i]
                    unique = np.unique(y_i)
                    if len(unique) == 1:
                        val = float(unique[0])
                        if val not in (0.0, 1.0):
                            raise ValueError(f"二分类标签必须为 0/1， got {val}")
                        models.append(val)
                    else:
                        model = self._create_classifier()
                        pos = int(y_i.sum())
                        neg = y.shape[0] - pos
                        scale = neg / max(pos, 1)
                        model.set_params(scale_pos_weight=max(min(scale, 10.0), 0.1))
                        model.fit(X, y_i)
                        models.append(model)
                    current += 1
                    if progress_callback:
                        progress_callback(current, total_steps)
            self.group_models[g.key] = models

        self.is_trained = True
        logger.info("%s 通用模型训练完成", self.profile.name)

    def _predict_sequence_initial(
        self, model: Any, encoder: LabelEncoder, group: NumberGroup, X_pred: np.ndarray
    ) -> np.ndarray:
        """预测 step=0 时各号码概率，用于展示."""
        mask = np.zeros(group.size, dtype=np.float32)
        x = self._build_sequence_input(X_pred, group, mask, 0).reshape(1, -1)
        pred = model.predict_proba(x)[0]
        full = np.full(group.size, 0.05 / group.size, dtype=np.float32)
        for idx, cls in enumerate(encoder.classes_):
            full[int(cls)] = max(pred[idx], 0.0)
        full = full / full.sum()
        return full

    def predict_proba(self, X: np.ndarray) -> dict[str, np.ndarray]:
        if not self.is_trained:
            raise RuntimeError("模型尚未训练")
        if self._base_feature_dim is None:
            raise RuntimeError("模型未记录基础特征维度")

        result: dict[str, np.ndarray] = {}
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="X does not have valid feature names",
                category=UserWarning,
            )
            for g in self.profile.groups:
                models = self.group_models[g.key]
                if g.positional:
                    probs = []
                    for model in models:
                        if isinstance(model, np.ndarray):
                            proba = model
                        elif isinstance(model, tuple) and len(model) == 2:
                            clf, encoder = model
                            pred = clf.predict_proba(X)[0]
                            full = np.full(g.size, 0.05 / g.size, dtype=np.float32)
                            for idx, cls in enumerate(encoder.classes_):
                                full[int(cls) - g.lo] = max(pred[idx], 0.0)
                            full = full / full.sum()
                            proba = full
                        else:
                            pred = model.predict_proba(X)[0]
                            full = np.full(g.size, 0.05 / g.size, dtype=np.float32)
                            for idx in range(len(pred)):
                                if idx < g.size:
                                    full[idx] = max(pred[idx], 0.0)
                            full = full / full.sum()
                            proba = full
                        probs.append(proba)
                    result[g.key] = np.array(probs)
                elif self._is_combination_group(g):
                    # 顺序生成模型：返回 step=0 的初始概率
                    _tag, model, encoder, _ = models[0]
                    result[g.key] = self._predict_sequence_initial(model, encoder, g, X)
                else:
                    probs = []
                    for model in models:
                        if isinstance(model, (int, float)):
                            proba = float(model)
                        else:
                            proba = model.predict_proba(X)[0, 1]
                        probs.append(proba)
                    result[g.key] = np.array(probs)
        return result

    def sample_combination(
        self,
        X_pred: np.ndarray,
        group: NumberGroup,
        rng: np.random.RandomState,
    ) -> list[int]:
        """对组合组使用顺序生成模型采样一个合法组合."""
        if not self.is_trained:
            raise RuntimeError("模型尚未训练")
        if not self._is_combination_group(group):
            raise ValueError(f"组 {group.key} 不是组合组，不能使用顺序采样")
        models = self.group_models[group.key]
        _tag, model, encoder, count = models[0]
        if _tag != "sequence":
            raise RuntimeError(f"组 {group.key} 未使用顺序生成模型")

        selected: list[int] = []
        mask = np.zeros(group.size, dtype=np.float32)
        for step in range(count):
            x = self._build_sequence_input(X_pred, group, mask, step).reshape(1, -1)
            pred = model.predict_proba(x)[0]
            full = np.full(group.size, 0.05 / group.size, dtype=np.float32)
            for idx, cls in enumerate(encoder.classes_):
                full[int(cls)] = max(pred[idx], 0.0)
            # 已选号码概率置 0
            for idx in selected:
                full[idx] = 0.0
            s = full.sum()
            if s <= 0:
                # 退化：从剩余号码均匀采样
                remaining = [i for i in range(group.size) if i not in selected]
                full = np.zeros(group.size, dtype=np.float32)
                for i in remaining:
                    full[i] = 1.0 / max(len(remaining), 1)
            else:
                full = full / s
            next_idx = int(rng.choice(group.size, p=full))
            selected.append(next_idx)
            mask[next_idx] = 1.0
        return [group.lo + idx for idx in selected]

    def save(self, path: Path | str) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            pickle.dump(
                {
                    "profile_key": self.profile.key,
                    "group_models": self.group_models,
                    "lookback": self.lookback,
                    "backend": self.backend,
                    "is_trained": self.is_trained,
                    "base_feature_dim": self._base_feature_dim,
                },
                f,
            )
        logger.info("通用模型已保存到 %s", path)

    def load(self, path: Path | str) -> None:
        path = Path(path)
        with path.open("rb") as f:
            data = pickle.load(f)
        self.group_models = data["group_models"]
        self.lookback = data["lookback"]
        self.backend = data.get("backend", "xgboost")
        self.is_trained = data["is_trained"]
        self._base_feature_dim = data.get("base_feature_dim")
        logger.info("通用模型已从 %s 加载", path)
