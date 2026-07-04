"""XGBoost 模型训练与预测."""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import numpy as np
import xgboost as xgb
from sklearn.multioutput import MultiOutputClassifier

logger = logging.getLogger(__name__)


def _save_booster(model: xgb.XGBClassifier, directory: Path) -> None:
    """保存 XGBoost 分类器到目录（原生 save_model + JSON 元数据）."""
    directory.mkdir(parents=True, exist_ok=True)
    model.save_model(str(directory / "model.json"))
    meta = {
        "type": "XGBClassifier",
        "classes_": model.classes_.tolist() if hasattr(model, "classes_") else [],
        "n_features_in": int(getattr(model, "n_features_in_", 0)),
    }
    with (directory / "meta.json").open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def _load_booster(directory: Path) -> xgb.XGBClassifier:
    """从目录加载 XGBoost 分类器."""
    clf = xgb.XGBClassifier()
    clf.load_model(str(directory / "model.json"))
    meta_path = directory / "meta.json"
    if meta_path.exists():
        with meta_path.open("r", encoding="utf-8") as f:
            meta = json.load(f)
        if "classes_" in meta:
            clf.classes_ = np.array(meta["classes_"])
    return clf


def _save_multioutput(moc: MultiOutputClassifier, directory: Path) -> None:
    """保存 MultiOutputClassifier 包装器到目录."""
    directory.mkdir(parents=True, exist_ok=True)
    estimator_dirs = []
    for idx, est in enumerate(moc.estimators_):
        est_dir = directory / f"estimator_{idx:02d}"
        _save_booster(est, est_dir)
        estimator_dirs.append(str(est_dir.relative_to(directory)))
    with (directory / "meta.json").open("w", encoding="utf-8") as f:
        json.dump({"type": "MultiOutputClassifier", "estimators": estimator_dirs}, f, ensure_ascii=False, indent=2)


def _load_multioutput(directory: Path) -> MultiOutputClassifier:
    """从目录加载 MultiOutputClassifier 包装器."""
    with (directory / "meta.json").open("r", encoding="utf-8") as f:
        meta = json.load(f)
    estimators = [_load_booster(directory / p) for p in meta["estimators"]]
    moc = MultiOutputClassifier(xgb.XGBClassifier(), n_jobs=1)
    moc.estimators_ = estimators
    return moc


class LotteryXGBoostModel:
    """基于 XGBoost 的彩票号码分析模型.

    为每个红球和每个蓝球训练二分类器，输出下一期出现的概率。
    """

    def __init__(self, lookback: int = 50, temp_dir: Optional[str] = None) -> None:
        self.lookback = lookback
        self.temp_dir = temp_dir
        self.red_models: List[xgb.XGBClassifier] = []
        self.blue_model: Optional[MultiOutputClassifier] = None
        self.is_trained = False

    def _create_classifier(self) -> xgb.XGBClassifier:
        """创建 XGBoost 分类器."""
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

    def fit(
        self,
        X: np.ndarray,
        y_red: np.ndarray,
        y_blue: np.ndarray,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        """训练模型.

        Args:
            X: 特征矩阵 (samples, features)
            y_red: 红球标签 (samples, 33)
            y_blue: 蓝球标签 (samples, 16)
            progress_callback: 可选进度回调，签名为 ``callback(current, total)``，
                每训练完一个分类器调用一次，用于界面进度展示。
        """
        if X.shape[0] == 0:
            raise ValueError("训练数据为空")
        if y_red.ndim != 2 or y_blue.ndim != 2:
            raise ValueError("y_red/y_blue 必须是二维数组")

        # 总步数 = 33 个红球分类器 + 1 个蓝球多输出分类器
        total = int(y_red.shape[1]) + 1

        # 训练 33 个红球二分类器
        self.red_models = []
        for i in range(y_red.shape[1]):
            model = self._create_classifier()
            # 处理类别不平衡：正样本很少
            pos = int(y_red[:, i].sum())
            neg = y_red.shape[0] - pos
            scale = neg / max(pos, 1)
            model.set_params(scale_pos_weight=min(scale, 10.0))
            model.fit(X, y_red[:, i])
            self.red_models.append(model)
            if progress_callback is not None:
                progress_callback(i + 1, total)
            logger.debug("红球 %02d 模型训练完成", i + 1)

        # 训练蓝球多输出分类器
        blue_clf = self._create_classifier().set_params(scale_pos_weight=5.0)
        self.blue_model = MultiOutputClassifier(blue_clf, n_jobs=1)
        self.blue_model.fit(X, y_blue)
        if progress_callback is not None:
            progress_callback(total, total)

        self.is_trained = True
        logger.info("XGBoost 模型训练完成")

    def predict_proba(
        self, X: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """预测下一期各号码出现概率.

        Returns:
            red_proba: 红球概率 (33,)
            blue_proba: 蓝球概率 (16,)
        """
        if not self.is_trained:
            raise RuntimeError("模型尚未训练")

        def _binary_proba(model):
            probs = model.predict_proba(X)[0]
            return probs[1] if probs.shape[0] > 1 else float(model.classes_[0] == 1)

        red_proba = np.array([_binary_proba(model) for model in self.red_models])
        blue_proba = np.array([_binary_proba(est) for est in self.blue_model.estimators_])
        return red_proba, blue_proba

    def save(self, path: Path | str) -> None:
        """保存模型到文件.

        使用 XGBoost 原生 ``save_model`` 格式，避免 pickle 跨版本兼容性问题。
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_root = Path(tempfile.mkdtemp(prefix="lottery_model_save_"))
        try:
            model_root = tmp_root / "model"
            model_root.mkdir(parents=True, exist_ok=True)
            red_dirs = []
            for idx, model in enumerate(self.red_models):
                d = model_root / f"red_{idx:02d}"
                _save_booster(model, d)
                red_dirs.append(str(d.relative_to(model_root)))
            blue_dir = model_root / "blue"
            _save_multioutput(self.blue_model, blue_dir)
            manifest = {
                "version": 2,
                "lookback": self.lookback,
                "is_trained": self.is_trained,
                "red_models": red_dirs,
                "blue_model": str(blue_dir.relative_to(model_root)),
            }
            with (model_root / "manifest.json").open("w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)

            # 打包为压缩文件，避免外部路径依赖
            archive = shutil.make_archive(
                base_name=str(tmp_root / "archive"),
                format="gztar",
                root_dir=str(model_root),
            )
            shutil.copyfile(archive, str(path))
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)
        logger.info("模型已保存到 %s", path)

    def load(self, path: Path | str) -> None:
        """从文件加载模型.

        优先加载原生 ``save_model`` 格式；遇到旧版 pickle 文件时删除并抛出异常，
        让上层重新训练。
        """
        path = Path(path)
        tmp_root = Path(tempfile.mkdtemp(prefix="lottery_model_load_"))
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

            self.lookback = manifest["lookback"]
            self.is_trained = manifest["is_trained"]
            self.red_models = [
                _load_booster(tmp_root / d) for d in manifest["red_models"]
            ]
            self.blue_model = _load_multioutput(tmp_root / manifest["blue_model"])
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)
        logger.info("模型已从 %s 加载", path)
