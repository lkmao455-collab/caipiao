"""机器学习模型文件的存储与新鲜度管理.

集中管理模型文件的命名、查找与「是否与当前数据匹配」的判断，
供 UI 训练流程与生成策略共用，避免各处重复实现。

各类模型（XGBoost、LightGBM 等）通过 ``prefix`` 区分文件命名，
文件名中同时包含训练参数与预测目标日期，提高缓存命中率，
避免相同参数下重复训练模型。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ...data.models import DrawRecord
from ...utils import app_data_dir

logger = logging.getLogger(__name__)


def model_dir() -> Path:
    """模型保存目录（位于应用数据目录下；不存在时自动创建）.

    若环境变量 ``CAIPIAO_MODEL_DIR`` 已设置，则优先使用该路径，
    以便批量回测 worker 将各进程的模型缓存隔离到独立临时目录。
    """
    env_dir = os.environ.get("CAIPIAO_MODEL_DIR")
    if env_dir:
        d = Path(env_dir)
    else:
        d = app_data_dir() / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def compute_lookback(record_count: int) -> int:
    """根据历史记录总数确定回看期数.

    与生成策略保持一致：尽量使用更长历史，同时至少保留 100 期作为训练样本。
    当记录数较少时，保证返回值至少为 1 且不超过 record_count - 1，避免 lookback=0
    导致特征工程抛出异常。
    """
    if record_count <= 1:
        return 0
    raw = max(50, record_count - 100)
    return max(1, min(raw, record_count - 1))


def data_fingerprint(records: list[DrawRecord]) -> str:
    """基于记录数量与最新一期生成数据指纹.

    版本前缀 v2 表示顺序组合生成模型；旧版模型会被视为过期并重新训练。
    """
    if not records:
        return "empty"
    latest = max(records, key=lambda r: r.draw_date)
    return f"v2|{len(records)}|{latest.issue}|{latest.draw_date.isoformat()}"


def _meta_path(model_path: Path) -> Path:
    """模型对应的元数据文件路径（与 MLPredictor._metadata_path 结果一致）."""
    return Path(str(model_path) + ".meta.json")


def _model_fingerprint(model_path: Path) -> str | None:
    """读取模型元数据中的指纹；缺失或异常返回 None."""
    meta_path = _meta_path(model_path)
    if not meta_path.exists():
        return None
    try:
        with meta_path.open("r", encoding="utf-8") as f:
            return json.load(f).get("fingerprint")
    except Exception:  # noqa: BLE001
        return None


def _model_meta(model_path: Path) -> dict[str, Any]:
    """读取模型元数据；缺失或异常返回空字典."""
    meta_path = _meta_path(model_path)
    if not meta_path.exists():
        return {}
    try:
        with meta_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


def _format_prediction_date(records: list[DrawRecord]) -> str:
    """返回模型预测目标日期的字符串（用于文件名）."""
    if not records:
        return "nodate"
    latest = max(records, key=lambda r: r.draw_date)
    return latest.draw_date.strftime("%Y%m%d")


def _format_params(options: dict[str, Any] | None) -> str:
    """把关键参数编码为文件名片段.

    只选取影响模型训练的参数（如 history_count），不影响训练的生成参数
    （如 diversity_boost、max_red_overlap）不纳入文件名，确保缓存能被正确命中。
    """
    options = options or {}
    parts = []
    history_count = options.get("history_count", -1)
    if isinstance(history_count, int) and history_count > 0:
        parts.append(f"hist{history_count}")
    if not parts:
        return "default"
    return "_".join(parts)


def new_model_path(
    records: list[DrawRecord],
    lookback: int,
    directory: Path | None = None,
    when: datetime | None = None,
    prefix: str = "xgboost",
    options: dict[str, Any] | None = None,
) -> Path:
    """生成带参数和目标日期的模型路径.

    文件名格式：
    ``{prefix}_{predict_date}_{params}_lookback{lookback}_{YYYYMMDD_HHMMSS}.pkl``

    其中：
    - predict_date：训练数据最新一期的开奖日期（模型要预测的就是下一期）。
    - params：影响训练/预测的关键策略参数（如 diversity_boost、max_red_overlap）。
    - lookback：特征回看期数。
    - timestamp：训练完成时间。
    """
    directory = directory or model_dir()
    predict_date = _format_prediction_date(records)
    params = _format_params(options)
    ts = (when or datetime.now(timezone.utc).astimezone()).strftime("%Y%m%d_%H%M%S")
    return directory / f"{prefix}_{predict_date}_{params}_lookback{lookback}_{ts}.pkl"


def _candidate_models(
    records: list[DrawRecord],
    lookback: int,
    directory: Path,
    prefix: str = "xgboost",
    options: dict[str, Any] | None = None,
) -> list[Path]:
    """列出与当前参数/日期匹配的候选模型."""
    if not directory.exists():
        return []
    predict_date = _format_prediction_date(records)
    params = _format_params(options)
    pattern = f"{prefix}_{predict_date}_{params}_lookback{lookback}_*.pkl"
    candidates = list(directory.glob(pattern))
    # 兼容旧命名
    legacy = directory / f"{prefix}_lookback{lookback}.pkl"
    if legacy.exists():
        candidates.append(legacy)
    return candidates


def find_current_model(
    records: list[DrawRecord],
    lookback: int,
    directory: Path | None = None,
    prefix: str = "xgboost",
    options: dict[str, Any] | None = None,
) -> Path | None:
    """返回与当前数据指纹匹配的、最新（按修改时间）的模型路径；无则 None."""
    directory = directory or model_dir()
    fingerprint = data_fingerprint(records)
    matching = [
        p
        for p in _candidate_models(records, lookback, directory, prefix, options)
        if _model_fingerprint(p) == fingerprint
    ]
    if not matching:
        return None
    return max(matching, key=lambda p: p.stat().st_mtime)


def is_model_current(
    records: list[DrawRecord],
    lookback: int,
    directory: Path | None = None,
    prefix: str = "xgboost",
    options: dict[str, Any] | None = None,
) -> bool:
    """当前数据是否已有匹配的最新模型."""
    return find_current_model(records, lookback, directory, prefix, options) is not None


def needs_incremental_update(
    records: list[DrawRecord],
    lookback: int,
    directory: Path | None = None,
    prefix: str = "xgboost",
    options: dict[str, Any] | None = None,
    max_incremental: int = 5,
) -> tuple[bool, int]:
    """检查是否需要增量更新。

    Args:
        records: 当前全部记录。
        lookback: 回看期数。
        directory: 模型目录。
        prefix: 模型文件前缀。
        options: 策略选项。
        max_incremental: 最大增量更新次数（超过则需要全量训练）。

    Returns:
        (需要增量, 新增记录数)。如果不需要增量或无法增量，返回 (False, 0)。
    """
    model_path = find_current_model(records, lookback, directory, prefix, options)
    if model_path is None:
        return False, 0

    meta = _model_meta(model_path)
    record_count_in_model = meta.get("record_count", 0)
    new_count = len(records) - record_count_in_model

    if new_count <= 0:
        return False, 0

    if new_count > max_incremental:
        logger.info("新增 %d 条记录超过阈值 %d，需要全量训练", new_count, max_incremental)
        return False, 0

    return True, new_count


def model_info(model_path: Path) -> dict[str, Any]:
    """读取模型的元数据信息摘要."""
    meta = _model_meta(model_path)
    try:
        mtime = model_path.stat().st_mtime
    except FileNotFoundError:
        mtime = 0.0
    info = {
        "path": str(model_path),
        "name": model_path.name,
        "modified": datetime.fromtimestamp(mtime, tz=timezone.utc).astimezone().isoformat(),
    }
    info.update(meta)
    return info
