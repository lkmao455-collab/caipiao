"""通用机器学习模型（按彩种档案驱动）.

支持任意 NumberGroup 结构：
- 组合组：为号池中每个号码训练一个二分类器；
- 按位组：为每个位置训练一个多分类器。

后端可以是 xgboost、lightgbm 或 catboost。
"""

from __future__ import annotations

import logging
import pickle
import warnings
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
from sklearn.multioutput import MultiOutputClassifier
from sklearn.preprocessing import LabelEncoder

from ..core.profile import LotteryProfile, NumberGroup

logger = logging.getLogger(__name__)


# 后端工厂 -------------------------------------------------------------- #
def _create_xgb_classifier(temp_dir: Optional[str] = None) -> Any:
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


def _create_lgbm_classifier(temp_dir: Optional[str] = None) -> Any:
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


def _create_catboost_classifier(temp_dir: Optional[str] = None) -> Any:
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
        temp_dir: Optional[str] = None,
    ) -> None:
        self.profile = profile
        self.lookback = lookback
        self.backend = backend
        self.temp_dir = temp_dir
        self.group_models: Dict[str, List[Any]] = {}
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

    def fit(
        self,
        X: np.ndarray,
        y_dict: Dict[str, np.ndarray],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        if X.shape[0] == 0:
            raise ValueError("训练数据为空")
        if X.ndim != 2:
            raise ValueError("X 必须是二维数组")

        total_steps = 0
        plan: List[Tuple[str, Any]] = []  # (group_key, task_description)
        for g in self.profile.groups:
            y = y_dict.get(g.key)
            if y is None or y.ndim != 2 or y.shape[0] != X.shape[0]:
                raise ValueError(f"组 {g.key} 标签缺失或维度与 X 不匹配")
            if g.positional:
                total_steps += g.count
                plan.append((g.key, "positional"))
            else:
                total_steps += g.size
                plan.append((g.key, "binary"))

        current = 0
        self.group_models = {}
        for g in self.profile.groups:
            y = y_dict[g.key]
            models: List[Any] = []
            if g.positional:
                # 每个位置一个多分类器
                for pos in range(g.count):
                    y_pos = y[:, pos]
                    unique = np.unique(y_pos)
                    if len(unique) == 1:
                        # 退化：该位置所有样本标签相同，使用常数概率
                        val = int(unique[0])
                        if not (g.lo <= val <= g.hi):
                            raise ValueError(f"按位标签 {val} 超出范围 [{g.lo}, {g.hi}]")
                        const = np.zeros(g.size, dtype=np.float32)
                        const[val - g.lo] = 1.0
                        models.append(const)
                    else:
                        # 训练数据中可能未出现全部类别，使用 LabelEncoder 将实际类别
                        # 映射为连续索引，避免 LightGBM/CatBoost 报
                        # "Found only N unique classes in the data, but have defined M classes" 警告，
                        # 同时防止 LightGBM 丢弃未出现类别导致概率维度错误。
                        encoder = LabelEncoder()
                        y_enc = encoder.fit_transform(y_pos)
                        num_class = len(encoder.classes_)
                        model = self._create_classifier(positional=True, num_class=num_class)
                        model.fit(X, y_enc)
                        models.append((model, encoder))
                    current += 1
                    if progress_callback:
                        progress_callback(current, total_steps)
            else:
                # 每个号码一个二分类器
                for i in range(g.size):
                    y_i = y[:, i]
                    unique = np.unique(y_i)
                    if len(unique) == 1:
                        # 退化：该号码所有样本标签相同
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

    def predict_proba(self, X: np.ndarray) -> Dict[str, np.ndarray]:
        if not self.is_trained:
            raise RuntimeError("模型尚未训练")

        result: Dict[str, np.ndarray] = {}
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
                            pred = clf.predict_proba(X)[0]  # shape (num_class,)
                            # 映射回完整号码空间，缺失类别给一个很小的基线概率
                            full = np.full(g.size, 0.05 / g.size, dtype=np.float32)
                            for idx, cls in enumerate(encoder.classes_):
                                full[int(cls) - g.lo] = max(pred[idx], 0.0)
                            full = full / full.sum()
                            proba = full
                        else:
                            # 旧格式缓存：裸分类器，无 encoder；直接用 predict_proba
                            pred = model.predict_proba(X)[0]
                            full = np.full(g.size, 0.05 / g.size, dtype=np.float32)
                            for idx in range(len(pred)):
                                if idx < g.size:
                                    full[idx] = max(pred[idx], 0.0)
                            full = full / full.sum()
                            proba = full
                        probs.append(proba)
                    result[g.key] = np.array(probs)  # shape (count, size)
                else:
                    probs = []
                    for model in models:
                        if isinstance(model, (int, float)):
                            proba = float(model)
                        else:
                            proba = model.predict_proba(X)[0, 1]
                        probs.append(proba)
                    result[g.key] = np.array(probs)  # shape (size,)
        return result

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
        logger.info("通用模型已从 %s 加载", path)
