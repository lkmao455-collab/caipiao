"""通用机器学习模型（按彩种档案驱动）.

支持任意 NumberGroup 结构：
- 组合组：为号池中每个号码训练一个二分类器；
- 按位组：为每个位置训练一个多分类器。

后端可以是 xgboost、lightgbm 或 catboost。
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
import warnings
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
from sklearn.multioutput import MultiOutputClassifier

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

# 原生保存/加载辅助函数 ---------------------------------------------------- #


def _is_xgboost_model(model: Any) -> bool:
    try:
        import xgboost as xgb
        return isinstance(model, xgb.XGBClassifier)
    except Exception:  # noqa: BLE001
        return False


def _is_lightgbm_model(model: Any) -> bool:
    try:
        import lightgbm as lgb
        return isinstance(model, lgb.LGBMClassifier)
    except Exception:  # noqa: BLE001
        return False


def _is_catboost_model(model: Any) -> bool:
    try:
        from catboost import CatBoostClassifier
        return isinstance(model, CatBoostClassifier)
    except Exception:  # noqa: BLE001
        return False


def _save_native_model(model: Any, directory: Path) -> Dict[str, Any]:
    """保存单个原生模型到目录，返回描述字典."""
    directory.mkdir(parents=True, exist_ok=True)
    if _is_xgboost_model(model):
        model.save_model(str(directory / "model.json"))
        return {"type": "xgboost"}
    if _is_lightgbm_model(model):
        model.booster_.save_model(str(directory / "model.txt"))
        return {"type": "lightgbm"}
    if _is_catboost_model(model):
        model.save_model(str(directory / "model.cbm"))
        return {"type": "catboost"}
    raise TypeError(f"不支持的原生模型类型: {type(model)}")


def _load_native_model(meta: Dict[str, Any], backend: str) -> Any:
    """从描述字典加载单个原生模型."""
    directory = Path(meta["path"])
    model_type = meta.get("type", backend)
    if model_type == "xgboost":
        import xgboost as xgb
        clf = xgb.XGBClassifier()
        clf.load_model(str(directory / "model.json"))
        return clf
    if model_type == "lightgbm":
        import lightgbm as lgb
        clf = lgb.LGBMClassifier()
        clf = lgb.Booster(model_file=str(directory / "model.txt"))
        return clf
    if model_type == "catboost":
        from catboost import CatBoostClassifier
        clf = CatBoostClassifier()
        clf.load_model(str(directory / "model.cbm"))
        return clf
    raise TypeError(f"不支持的模型类型: {model_type}")


def _save_model(model: Any, directory: Path, root: Path) -> Dict[str, Any]:
    """保存单个模型（可能是常数退化模型或真实模型）."""
    directory.mkdir(parents=True, exist_ok=True)
    if isinstance(model, np.ndarray):
        np.save(directory / "constant.npy", model)
        return {"type": "constant_array", "path": str(directory.relative_to(root))}
    if isinstance(model, (int, float)):
        with (directory / "constant.json").open("w", encoding="utf-8") as f:
            json.dump({"value": float(model)}, f)
        return {"type": "constant_scalar", "path": str(directory.relative_to(root))}
    meta = _save_native_model(model, directory)
    meta["path"] = str(directory.relative_to(root))
    return meta


def _load_model(meta: Dict[str, Any], backend: str, root: Path) -> Any:
    """加载单个模型."""
    model_type = meta.get("type")
    directory = root / meta["path"]
    if model_type == "constant_array":
        return np.load(directory / "constant.npy")
    if model_type == "constant_scalar":
        with (directory / "constant.json").open("r", encoding="utf-8") as f:
            return json.load(f)["value"]
    return _load_native_model(meta, backend)


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
                        model = self._create_classifier(positional=True, num_class=g.size)
                        model.fit(X, y_pos)
                        models.append(model)
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
                        else:
                            proba = model.predict_proba(X)[0]
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
        """保存模型到文件.

        使用各后端原生 save_model 格式，避免 pickle 跨版本兼容性问题。
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_root = Path(tempfile.mkdtemp(prefix="lottery_generic_model_save_"))
        try:
            model_root = tmp_root / "model"
            model_root.mkdir(parents=True, exist_ok=True)
            group_meta: Dict[str, List[Dict[str, Any]]] = {}
            for g_key, models in self.group_models.items():
                group_dir = model_root / g_key
                group_meta[g_key] = []
                for idx, model in enumerate(models):
                    d = group_dir / f"model_{idx:04d}"
                    group_meta[g_key].append(_save_model(model, d, model_root))

            manifest = {
                "version": 2,
                "profile_key": self.profile.key,
                "lookback": self.lookback,
                "backend": self.backend,
                "is_trained": self.is_trained,
                "groups": group_meta,
            }
            with (model_root / "manifest.json").open("w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)

            archive = shutil.make_archive(
                base_name=str(tmp_root / "archive"),
                format="gztar",
                root_dir=str(model_root),
            )
            shutil.copyfile(archive, str(path))
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)
        logger.info("通用模型已保存到 %s", path)

    def load(self, path: Path | str) -> None:
        """从文件加载模型.

        优先加载原生 save_model 格式；遇到旧版 pickle 文件时删除并抛出异常，
        让上层重新训练。
        """
        path = Path(path)
        tmp_root = Path(tempfile.mkdtemp(prefix="lottery_generic_model_load_"))
        try:
            try:
                shutil.unpack_archive(str(path), extract_dir=str(tmp_root), format="gztar")
            except Exception as exc:  # noqa: BLE001
                logger.warning("模型文件不是新版压缩格式，删除旧模型: %s", exc)
                path.unlink(missing_ok=True)
                raise RuntimeError("旧模型格式不兼容，将重新训练") from exc

            manifest_path = tmp_root / "manifest.json"
            if not manifest_path.exists():
                raise RuntimeError("模型压缩包中缺少 manifest.json")
            with manifest_path.open("r", encoding="utf-8") as f:
                manifest = json.load(f)
            if manifest.get("version") != 2:
                raise RuntimeError(f"不支持的模型版本: {manifest.get('version')}")

            self.profile_key = manifest["profile_key"]
            self.lookback = manifest["lookback"]
            self.backend = manifest["backend"]
            self.is_trained = manifest["is_trained"]
            self.group_models = {}
            for g_key, meta_list in manifest["groups"].items():
                self.group_models[g_key] = [
                    _load_model(m, self.backend, tmp_root) for m in meta_list
                ]
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)
        logger.info("通用模型已从 %s 加载", path)
