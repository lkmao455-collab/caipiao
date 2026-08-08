"""可视化平台：图表组件和仪表盘管理。"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..log import get_logger

logger = get_logger(__name__)


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
        self._register_default_templates()

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
        self._dashboards[dashboard.id] = dashboard
        return dashboard

    def get_dashboard(self, dashboard_id: str) -> Dashboard | None:
        return self._dashboards.get(dashboard_id)

    def list_dashboards(self, owner_id: str | None = None) -> list[Dashboard]:
        dashboards = list(self._dashboards.values())
        if owner_id:
            dashboards = [d for d in dashboards if d.owner_id == owner_id or d.is_public]
        return dashboards

    def delete_dashboard(self, dashboard_id: str) -> bool:
        if dashboard_id in self._dashboards:
            del self._dashboards[dashboard_id]
            return True
        return False

    def add_chart(self, dashboard_id: str, chart: ChartConfig) -> bool:
        dashboard = self._dashboards.get(dashboard_id)
        if dashboard:
            dashboard.charts.append(chart)
            dashboard.updated_at = time.time()
            return True
        return False

    def remove_chart(self, dashboard_id: str, chart_id: str) -> bool:
        dashboard = self._dashboards.get(dashboard_id)
        if dashboard:
            dashboard.charts = [c for c in dashboard.charts if c.id != chart_id]
            dashboard.updated_at = time.time()
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
