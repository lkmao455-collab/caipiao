"""最优参数/锁定参数持久化."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..utils import app_data_dir


logger = logging.getLogger(__name__)


@dataclass
class LockedParameter:
    strategy_id: str
    param_name: str
    param_value: Any
    source: str  # "scan", "user", "default"
    locked_at: str
    stability_score: float = 0.0
    cv_mean_prize: float = 0.0
    cv_std_prize: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "LockedParameter":
        return cls(
            strategy_id=data.get("strategy_id", ""),
            param_name=data.get("param_name", ""),
            param_value=data.get("param_value"),
            source=data.get("source", "user"),
            locked_at=data.get("locked_at", ""),
            stability_score=data.get("stability_score", 0.0),
            cv_mean_prize=data.get("cv_mean_prize", 0.0),
            cv_std_prize=data.get("cv_std_prize", 0.0),
        )


@dataclass
class OptimalParamsConfig:
    profile_key: str
    locked: List[LockedParameter] = field(default_factory=list)
    last_scan_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "profile_key": self.profile_key,
            "locked": [p.to_dict() for p in self.locked],
            "last_scan_at": self.last_scan_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OptimalParamsConfig":
        return cls(
            profile_key=data.get("profile_key", ""),
            locked=[LockedParameter.from_dict(p) for p in data.get("locked", [])],
            last_scan_at=data.get("last_scan_at"),
        )


class OptimalParamStore:
    """管理每个彩种的最优锁定参数。"""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self._base_dir = (data_dir or app_data_dir()) / "optimal_params"
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, profile_key: str) -> Path:
        return self._base_dir / f"{profile_key}.json"

    def load(self, profile_key: str) -> OptimalParamsConfig:
        path = self._path(profile_key)
        if not path.exists():
            return OptimalParamsConfig(profile_key=profile_key)
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return OptimalParamsConfig.from_dict(data)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("读取最优参数文件失败 %s: %s", path, exc)
            if path.exists():
                backup_path = path.with_suffix(
                    f".corrupted-{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
                )
                try:
                    path.rename(backup_path)
                    logger.info("已备份损坏文件到 %s", backup_path)
                except OSError as rename_exc:
                    logger.error("备份损坏文件失败: %s", rename_exc)
            return OptimalParamsConfig(profile_key=profile_key)

    def save(self, config: OptimalParamsConfig) -> None:
        path = self._path(config.profile_key)
        with path.open("w", encoding="utf-8") as f:
            json.dump(config.to_dict(), f, ensure_ascii=False, indent=2)

    def lock(
        self,
        profile_key: str,
        strategy_id: str,
        param_name: str,
        param_value: Any,
        source: str = "user",
        stability_score: float = 0.0,
        cv_mean_prize: float = 0.0,
        cv_std_prize: float = 0.0,
    ) -> None:
        config = self.load(profile_key)
        # 去重：同一 strategy + param 只保留最新
        config.locked = [
            p
            for p in config.locked
            if not (p.strategy_id == strategy_id and p.param_name == param_name)
        ]
        config.locked.append(
            LockedParameter(
                strategy_id=strategy_id,
                param_name=param_name,
                param_value=param_value,
                source=source,
                locked_at=datetime.now().isoformat(),
                stability_score=stability_score,
                cv_mean_prize=cv_mean_prize,
                cv_std_prize=cv_std_prize,
            )
        )
        config.last_scan_at = datetime.now().isoformat()
        self.save(config)

    def unlock(self, profile_key: str, strategy_id: str, param_name: str) -> None:
        config = self.load(profile_key)
        config.locked = [
            p
            for p in config.locked
            if not (p.strategy_id == strategy_id and p.param_name == param_name)
        ]
        self.save(config)

    def get_locked(self, profile_key: str, strategy_id: str) -> Dict[str, Any]:
        config = self.load(profile_key)
        return {
            p.param_name: p.param_value
            for p in config.locked
            if p.strategy_id == strategy_id
        }

    def apply_defaults(
        self, profile_key: str, strategy_id: str, schema: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """将锁定参数覆盖到 schema 的 default 值中。"""
        locked = self.get_locked(profile_key, strategy_id)
        if not locked:
            return schema
        new_schema = {}
        for key, meta in schema.items():
            new_meta = dict(meta)
            if key in locked:
                new_meta["default"] = locked[key]
            new_schema[key] = new_meta
        return new_schema
