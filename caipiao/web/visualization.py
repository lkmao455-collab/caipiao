"""可视化平台：图表组件和仪表盘管理。"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..log import get_logger
from . import db as _webdb

logger = get_logger(__name__)


def _dashboard_to_dict(d: Dashboard) -> dict[str, Any]:
    return {
        "id": d.id,
        "name": d.name,
        "description": d.description,
        "charts": [
            {
                "id": c.id,
                "name": c.name,
                "chart_type": c.chart_type,
                "data_source": c.data_source,
                "query": c.query,
                "options": c.options,
                "position": c.position,
                "refresh_interval": c.refresh_interval,
                "created_at": c.created_at,
            }
            for c in d.charts
        ],
        "layout": d.layout,
        "theme": d.theme,
        "is_public": d.is_public,
        "owner_id": d.owner_id,
        "created_at": d.created_at,
        "updated_at": d.updated_at,
    }


def _dict_to_dashboard(data: dict[str, Any]) -> Dashboard:
    return Dashboard(
        id=data["id"],
        name=data["name"],
        description=data.get("description", ""),
        charts=[
            ChartConfig(
                id=c["id"],
                name=c["name"],
                chart_type=c["chart_type"],
                data_source=c.get("data_source", ""),
                query=c.get("query", ""),
                options=c.get("options", {}),
                position=c.get("position", {}),
                refresh_interval=c.get("refresh_interval", 0),
                created_at=c.get("created_at", time.time),
            )
            for c in data.get("charts", [])
        ],
        layout=data.get("layout", "grid"),
        theme=data.get("theme", "light"),
        is_public=data.get("is_public", False),
        owner_id=data.get("owner_id", ""),
        created_at=data.get("created_at", time.time),
        updated_at=data.get("updated_at", time.time),
    )


@dataclass
class ChartConfig:
    id: str
    name: str
    chart_type: str  # bar, line, pie, scatter, heatmap, gauge, radar
    data_source: str = ""
    query: str = ""
    options: dict[str, Any] = field(default_factory=dict)
    position: dict[str, int] = field(default_factory=dict)  # x, y, w, h
    refresh_interval: int = 0
    created_at: float = field(default_factory=time.time)


@dataclass
class Dashboard:
    id: str
    name: str
    description: str = ""
    charts: list[ChartConfig] = field(default_factory=list)
    layout: str = "grid"  # grid, flex, free
    theme: str = "light"
    is_public: bool = False
    owner_id: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class VisualizationTemplate:
    id: str
    name: str
    description: str = ""
    chart_type: str = ""
    default_options: dict[str, Any] = field(default_factory=dict)
    category: str = ""


class VisualizationPlatform:
    """可视化平台：管理仪表盘和图表。"""

    def __init__(self):
        self._dashboards: dict[str, Dashboard] = {}
        self._templates: dict[str, VisualizationTemplate] = {}
        self._loaded = False
        self._loaded_db_url: str | None = None
        self._register_default_templates()

    def _ensure_loaded(self) -> None:
        _webdb._ensure_engine()
        url = _webdb._db_url()
        if self._loaded and self._loaded_db_url == url:
            return
        self._dashboards = {}
        from .models import DashboardRow

        with _webdb._SessionLocal() as session:
            for row in session.query(DashboardRow).all():
                try:
                    self._dashboards[row.id] = _dict_to_dashboard(
                        json.loads(row.data_json)
                    )
                except Exception as exc:
                    logger.error("加载仪表盘 %s 失败: %s", row.id, exc)
        self._loaded = True
        self._loaded_db_url = url

    def _persist_dashboard(self, dashboard_id: str) -> None:
        from .models import DashboardRow

        d = self._dashboards.get(dashboard_id)
        with _webdb._SessionLocal() as session:
            row = session.get(DashboardRow, dashboard_id)
            if d is None:
                if row is not None:
                    session.delete(row)
                    session.commit()
                return
            data = json.dumps(_dashboard_to_dict(d), ensure_ascii=False)
            if row is None:
                session.add(
                    DashboardRow(
                        id=dashboard_id,
                        name=d.name,
                        description=d.description,
                        owner_id=d.owner_id or None,
                        data_json=data,
                        updated_at=d.updated_at,
                    )
                )
            else:
                row.data_json = data
                row.name = d.name
                row.description = d.description
                row.owner_id = d.owner_id or None
                row.updated_at = d.updated_at
            session.commit()

    def _register_default_templates(self):
        templates = [
            VisualizationTemplate(
                id="freq_bar",
                name="频率柱状图",
                description="号码频率分布",
                chart_type="bar",
                default_options={"orientation": "vertical", "show_values": True},
                category="频率分析",
            ),
            VisualizationTemplate(
                id="trend_line",
                name="趋势折线图",
                description="号码趋势变化",
                chart_type="line",
                default_options={"smooth": True, "show_dots": True},
                category="趋势分析",
            ),
            VisualizationTemplate(
                id="distribution_pie",
                name="分布饼图",
                description="奇偶/大小分布",
                chart_type="pie",
                default_options={"donut": False, "show_percent": True},
                category="分布分析",
            ),
            VisualizationTemplate(
                id="correlation_scatter",
                name="相关性散点图",
                description="号码相关性分析",
                chart_type="scatter",
                default_options={"show_trendline": True},
                category="相关性分析",
            ),
            VisualizationTemplate(
                id="heatmap_grid",
                name="热力图",
                description="号码热度分布",
                chart_type="heatmap",
                default_options={"color_scheme": "blues"},
                category="热度分析",
            ),
            VisualizationTemplate(
                id="gauge_meter",
                name="仪表盘",
                description="实时指标展示",
                chart_type="gauge",
                default_options={"min": 0, "max": 100},
                category="实时监控",
            ),
            VisualizationTemplate(
                id="radar_chart",
                name="雷达图",
                description="多维度对比",
                chart_type="radar",
                default_options={"filled": True},
                category="对比分析",
            ),
        ]
        for t in templates:
            self._templates[t.id] = t

    def create_dashboard(self, dashboard: Dashboard) -> Dashboard:
        self._ensure_loaded()
        self._dashboards[dashboard.id] = dashboard
        self._persist_dashboard(dashboard.id)
        return dashboard

    def get_dashboard(self, dashboard_id: str) -> Dashboard | None:
        self._ensure_loaded()
        return self._dashboards.get(dashboard_id)

    def list_dashboards(self, owner_id: str | None = None) -> list[Dashboard]:
        self._ensure_loaded()
        dashboards = list(self._dashboards.values())
        if owner_id:
            dashboards = [d for d in dashboards if d.owner_id == owner_id or d.is_public]
        return dashboards

    def delete_dashboard(self, dashboard_id: str) -> bool:
        self._ensure_loaded()
        if dashboard_id in self._dashboards:
            del self._dashboards[dashboard_id]
            self._persist_dashboard(dashboard_id)
            return True
        return False

    def add_chart(self, dashboard_id: str, chart: ChartConfig) -> bool:
        self._ensure_loaded()
        dashboard = self._dashboards.get(dashboard_id)
        if dashboard:
            dashboard.charts.append(chart)
            dashboard.updated_at = time.time()
            self._persist_dashboard(dashboard_id)
            return True
        return False

    def remove_chart(self, dashboard_id: str, chart_id: str) -> bool:
        self._ensure_loaded()
        dashboard = self._dashboards.get(dashboard_id)
        if dashboard:
            dashboard.charts = [c for c in dashboard.charts if c.id != chart_id]
            dashboard.updated_at = time.time()
            self._persist_dashboard(dashboard_id)
            return True
        return False

    def get_templates(self, category: str | None = None) -> list[VisualizationTemplate]:
        templates = list(self._templates.values())
        if category:
            templates = [t for t in templates if t.category == category]
        return templates

    def get_template(self, template_id: str) -> VisualizationTemplate | None:
        return self._templates.get(template_id)

    def create_chart_from_template(self, template_id: str, name: str) -> ChartConfig | None:
        template = self._templates.get(template_id)
        if not template:
            return None
        return ChartConfig(
            id=str(uuid.uuid4())[:8],
            name=name,
            chart_type=template.chart_type,
            options=template.default_options.copy(),
        )


# 全局可视化平台
_platform: VisualizationPlatform | None = None


def get_visualization_platform() -> VisualizationPlatform:
    global _platform
    if _platform is None:
        _platform = VisualizationPlatform()
    return _platform
