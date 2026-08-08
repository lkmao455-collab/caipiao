"""高级报表系统：自定义报表生成和导出。"""

from __future__ import annotations

import csv
import io
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..log import get_logger

logger = get_logger(__name__)


@dataclass
class ReportColumn:
    key: str
    label: str
    type: str = "text"  # text, number, date, percent
    width: int | None = None
    formatter: str | None = None


@dataclass
class ReportFilter:
    field: str
    operator: str  # eq, ne, gt, lt, gte, lte, contains, in
    value: Any


@dataclass
class ReportConfig:
    id: str
    name: str
    description: str = ""
    columns: list[ReportColumn] = field(default_factory=list)
    filters: list[ReportFilter] = field(default_factory=list)
    sort_by: str = ""
    sort_order: str = "asc"
    group_by: str = ""
    chart_type: str = ""  # bar, line, pie, none
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class ReportResult:
    config: ReportConfig
    data: list[dict[str, Any]]
    summary: dict[str, Any] = field(default_factory=dict)
    generated_at: float = field(default_factory=time.time)


class ReportEngine:
    """报表引擎：生成和导出报表。"""

    def __init__(self):
        self._configs: dict[str, ReportConfig] = {}
        self._data_sources: dict[str, Any] = {}

    def register_data_source(self, name: str, data: list[dict]):
        """注册数据源。"""
        self._data_sources[name] = data

    def create_config(self, config: ReportConfig) -> ReportConfig:
        """创建报表配置。"""
        self._configs[config.id] = config
        return config

    def get_config(self, config_id: str) -> ReportConfig | None:
        return self._configs.get(config_id)

    def list_configs(self) -> list[ReportConfig]:
        return list(self._configs.values())

    def delete_config(self, config_id: str) -> bool:
        if config_id in self._configs:
            del self._configs[config_id]
            return True
        return False

    def generate_report(self, config_id: str, data_source: str) -> ReportResult | None:
        """生成报表。"""
        config = self._configs.get(config_id)
        if not config:
            return None

        data = self._data_sources.get(data_source, [])
        if not data:
            return None

        # 应用过滤
        filtered = self._apply_filters(data, config.filters)

        # 应用排序
        if config.sort_by:
            filtered.sort(
                key=lambda x: x.get(config.sort_by, ""),
                reverse=config.sort_order == "desc",
            )

        # 应用分组
        if config.group_by:
            filtered = self._group_data(filtered, config.group_by)

        # 计算摘要
        summary = self._calculate_summary(filtered, config)

        return ReportResult(
            config=config,
            data=filtered,
            summary=summary,
        )

    def _apply_filters(self, data: list[dict], filters: list[ReportFilter]) -> list[dict]:
        """应用过滤条件。"""
        result = data
        for f in filters:
            field_val = f.field
            op = f.operator
            value = f.value

            if op == "eq":
                result = [r for r in result if r.get(field_val) == value]
            elif op == "ne":
                result = [r for r in result if r.get(field_val) != value]
            elif op == "gt":
                result = [r for r in result if (r.get(field_val) or 0) > value]
            elif op == "lt":
                result = [r for r in result if (r.get(field_val) or 0) < value]
            elif op == "gte":
                result = [r for r in result if (r.get(field_val) or 0) >= value]
            elif op == "lte":
                result = [r for r in result if (r.get(field_val) or 0) <= value]
            elif op == "contains":
                result = [r for r in result if value in str(r.get(field_val, ""))]
            elif op == "in":
                result = [r for r in result if r.get(field_val) in value]

        return result

    def _group_data(self, data: list[dict], group_by: str) -> list[dict]:
        """分组聚合。"""
        groups: dict[str, list[dict]] = {}
        for item in data:
            key = str(item.get(group_by, "unknown"))
            if key not in groups:
                groups[key] = []
            groups[key].append(item)

        result = []
        for key, items in groups.items():
            row = {group_by: key, "count": len(items)}
            # 聚合数值字段
            for item in items:
                for k, v in item.items():
                    if k != group_by and isinstance(v, (int, float)):
                        if f"{k}_sum" not in row:
                            row[f"{k}_sum"] = 0
                            row[f"{k}_avg"] = 0
                            row[f"{k}_min"] = v
                            row[f"{k}_max"] = v
                        row[f"{k}_sum"] += v
                        row[f"{k}_min"] = min(row[f"{k}_min"], v)
                        row[f"{k}_max"] = max(row[f"{k}_max"], v)
            # 计算平均值
            for k in list(row.keys()):
                if k.endswith("_sum"):
                    base = k[:-4]
                    row[f"{base}_avg"] = row[k] / row["count"] if row["count"] > 0 else 0
            result.append(row)

        return result

    def _calculate_summary(self, data: list[dict], config: ReportConfig) -> dict:
        """计算摘要统计。"""
        if not data:
            return {"total_rows": 0}

        summary: dict[str, Any] = {"total_rows": len(data)}

        for col in config.columns:
            if col.type == "number":
                values = [r.get(col.key, 0) for r in data if isinstance(r.get(col.key), (int, float))]
                if values:
                    summary[f"{col.key}_sum"] = sum(values)
                    summary[f"{col.key}_avg"] = sum(values) / len(values)
                    summary[f"{col.key}_min"] = min(values)
                    summary[f"{col.key}_max"] = max(values)

        return summary

    def export_csv(self, result: ReportResult) -> str:
        """导出为 CSV。"""
        output = io.StringIO()
        if not result.data:
            return ""

        headers = [col.label for col in result.config.columns]
        writer = csv.writer(output)
        writer.writerow(headers)

        for row in result.data:
            values = [row.get(col.key, "") for col in result.config.columns]
            writer.writerow(values)

        return output.getvalue()

    def export_json(self, result: ReportResult) -> str:
        """导出为 JSON。"""
        return json.dumps({
            "config": {
                "name": result.config.name,
                "description": result.config.description,
            },
            "summary": result.summary,
            "data": result.data,
        }, ensure_ascii=False, indent=2)


# 全局报表引擎
_report_engine: ReportEngine | None = None


def get_report_engine() -> ReportEngine:
    global _report_engine
    if _report_engine is None:
        _report_engine = ReportEngine()
    return _report_engine
