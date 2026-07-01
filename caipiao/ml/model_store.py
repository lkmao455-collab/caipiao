"""XGBoost 模型文件的存储与新鲜度管理.

集中管理模型文件的命名、查找与「是否与当前数据匹配」的判断，
供 UI 训练流程与生成策略共用，避免各处重复实现。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from ..data.models import DrawRecord


def model_dir() -> Path:
    """模型保存目录（不存在时自动创建）."""
    d = Path.home() / ".caipiao" / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def compute_lookback(record_count: int) -> int:
    """根据历史记录总数确定回看期数.

    与生成策略保持一致：尽量使用更长历史，同时至少保留 100 期作为训练样本。
    """
    return max(50, record_count - 100)


def data_fingerprint(records: List[DrawRecord]) -> str:
    """基于记录数量与最新一期生成数据指纹.

    与 :class:`caipiao.ml.predictor.MLPredictor` 保持一致，用于判断模型是否过期。
    """
    if not records:
        return "empty"
    latest = max(records, key=lambda r: r.draw_date)
    return f"{len(records)}|{latest.issue}|{latest.draw_date.isoformat()}"


def _meta_path(model_path: Path) -> Path:
    """模型对应的元数据文件路径（与 MLPredictor._metadata_path 结果一致）."""
    return Path(str(model_path) + ".meta.json")


def _model_fingerprint(model_path: Path) -> Optional[str]:
    """读取模型元数据中的指纹；缺失或异常返回 None."""
    meta_path = _meta_path(model_path)
    if not meta_path.exists():
        return None
    try:
        with meta_path.open("r", encoding="utf-8") as f:
            return json.load(f).get("fingerprint")
    except Exception:  # noqa: BLE001
        return None


def new_model_path(
    lookback: int,
    directory: Optional[Path] = None,
    when: Optional[datetime] = None,
) -> Path:
    """生成带时间戳的新模型路径：``xgboost_lookback{lookback}_{YYYYMMDD_HHMMSS}.pkl``."""
    directory = directory or model_dir()
    ts = (when or datetime.now()).strftime("%Y%m%d_%H%M%S")
    return directory / f"xgboost_lookback{lookback}_{ts}.pkl"


def _candidate_models(lookback: int, directory: Path) -> List[Path]:
    """列出该 lookback 的所有候选模型（含旧的无时间戳命名）."""
    if not directory.exists():
        return []
    candidates = list(directory.glob(f"xgboost_lookback{lookback}_*.pkl"))
    legacy = directory / f"xgboost_lookback{lookback}.pkl"
    if legacy.exists():
        candidates.append(legacy)
    return candidates


def find_current_model(
    records: List[DrawRecord],
    lookback: int,
    directory: Optional[Path] = None,
) -> Optional[Path]:
    """返回与当前数据指纹匹配的、最新（按修改时间）的模型路径；无则 None."""
    directory = directory or model_dir()
    fingerprint = data_fingerprint(records)
    matching = [
        p
        for p in _candidate_models(lookback, directory)
        if _model_fingerprint(p) == fingerprint
    ]
    if not matching:
        return None
    return max(matching, key=lambda p: p.stat().st_mtime)


def is_model_current(
    records: List[DrawRecord],
    lookback: int,
    directory: Optional[Path] = None,
) -> bool:
    """当前数据是否已有匹配的最新模型."""
    return find_current_model(records, lookback, directory) is not None
