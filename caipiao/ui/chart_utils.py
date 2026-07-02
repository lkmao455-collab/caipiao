"""图表生成工具.

用于把 XGBoost 预测概率渲染为折线图，并支持在可缩放拖动的 QGraphicsView 中查看。
"""

from __future__ import annotations

import base64
import io
from typing import List

from PySide6.QtCore import QByteArray, QEvent, Qt
from PySide6.QtGui import QPainter, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QDialog,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import matplotlib

matplotlib.use("Agg")  # 无头后端，适合服务器/后台生成

import matplotlib.pyplot as plt


def _configure_matplotlib_fonts() -> None:
    """配置中文字体，避免标签乱码."""
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def _plot_single(
    ax,
    probabilities: List[float],
    title: str,
    xlabel: str,
    color: str,
    highlight_top_n: int = 0,
) -> None:
    """在指定 Axes 上绘制单张概率折线图."""
    numbers = list(range(1, len(probabilities) + 1))
    ax.plot(
        numbers,
        probabilities,
        color=color,
        marker="o",
        markersize=5,
        linewidth=2,
        label="Predicted probability",
    )

    if highlight_top_n > 0:
        top_indices = sorted(
            range(len(probabilities)), key=lambda i: probabilities[i], reverse=True
        )[:highlight_top_n]
        ax.scatter(
            [numbers[i] for i in top_indices],
            [probabilities[i] for i in top_indices],
            color="orange",
            s=100,
            zorder=5,
            label=f"Top {highlight_top_n}",
        )

    ax.set_title(title, fontsize=14)
    ax.set_xlabel(xlabel, fontsize=12)
    ax.set_ylabel("Probability", fontsize=12)
    ax.set_xticks(numbers)
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend(loc="upper right", fontsize=10)
    ax.set_ylim(bottom=0)


def build_group_probability_chart_pixmap(
    group_probabilities: List[tuple[str, List[float], str, int, str]],
    lookback: int | str = "-",
    diversity_boost: int | str = "-",
    model_name: str = "XGBoost",
) -> QPixmap:
    """生成任意彩种号码组概率折线图的 QPixmap.

    Args:
        group_probabilities: [(标题, 概率列表, 颜色, 高亮前N个, x轴标签), ...]
        lookback: 回看期数。
        diversity_boost: 多样性增强系数。
        model_name: 模型名称，用于总标题。
    """
    _configure_matplotlib_fonts()

    n = len(group_probabilities)
    fig, axes = plt.subplots(n, 1, figsize=(12, 5 * n), dpi=150)
    if n == 1:
        axes = [axes]
    for ax, (title, probs, color, highlight, xlabel) in zip(axes, group_probabilities):
        _plot_single(ax, probs, title=title, xlabel=xlabel, color=color, highlight_top_n=highlight)

    fig.suptitle(
        f"{model_name} Prediction Probability Charts (lookback={lookback}, diversity={diversity_boost})",
        fontsize=16,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.97])

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)

    pixmap = QPixmap()
    pixmap.loadFromData(QByteArray(buf.read()))
    return pixmap


def build_group_probability_charts_html(
    group_probabilities: List[tuple[str, List[float], str, int, str]],
    lookback: int | str = "-",
    diversity_boost: int | str = "-",
    model_name: str = "XGBoost",
) -> str:
    """生成适合 PDF/打印的通用概率折线图 HTML（base64 图片）."""
    _configure_matplotlib_fonts()

    n = len(group_probabilities)
    fig, axes = plt.subplots(n, 1, figsize=(10, 4 * n), dpi=120)
    if n == 1:
        axes = [axes]
    for ax, (title, probs, color, highlight, xlabel) in zip(axes, group_probabilities):
        _plot_single(ax, probs, title=title, xlabel=xlabel, color=color, highlight_top_n=highlight)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("ascii")

    return f"""
    <div style="font-family: 'Microsoft YaHei', sans-serif; font-size: 14px;">
        <h3 style="color:#0A2540;margin:8px 0;">
            {model_name} 预测概率折线图（回看 {lookback} 期，多样性增强 {diversity_boost}）
        </h3>
        <p style="color:#666;font-size:12px;margin:4px 0;">
            橙色标记为每组概率最高的推荐号码。
        </p>
        <p><img src="data:image/png;base64,{b64}" width="100%"></p>
        <p style="color:#888;font-size:11px;margin-top:6px;">
            注：概率为模型基于历史数据的预测倾向，数值越高被采样选中的可能性越大，但不代表未来开奖概率。
        </p>
    </div>
    """


def build_probability_chart_pixmap(
    red_probabilities: List[float],
    blue_probabilities: List[float],
    lookback: int | str = "-",
    diversity_boost: int | str = "-",
) -> QPixmap:
    """双色球专用：生成红球+蓝球组合概率折线图（兼容旧接口）."""
    return build_group_probability_chart_pixmap(
        [
            ("Red Balls Probability", red_probabilities, "#D32F2F", 6, "Red Ball Number (1-33)"),
            ("Blue Balls Probability", blue_probabilities, "#1976D2", 1, "Blue Ball Number (1-16)"),
        ],
        lookback=lookback,
        diversity_boost=diversity_boost,
        model_name="XGBoost",
    )


def build_probability_charts_html(
    red_probabilities: List[float],
    blue_probabilities: List[float],
    lookback: int | str = "-",
    diversity_boost: int | str = "-",
) -> str:
    """双色球专用：生成红球+蓝球概率折线图 HTML（兼容旧接口）."""
    return build_group_probability_charts_html(
        [
            ("Red Balls Probability", red_probabilities, "#D32F2F", 6, "Red Ball Number (1-33)"),
            ("Blue Balls Probability", blue_probabilities, "#1976D2", 1, "Blue Ball Number (1-16)"),
        ],
        lookback=lookback,
        diversity_boost=diversity_boost,
        model_name="XGBoost",
    )


class ChartGraphicsView(QGraphicsView):
    """支持鼠标滚轮缩放和拖拽平移的图表视图."""

    def __init__(self, pixmap: QPixmap, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pixmap = pixmap

        scene = QGraphicsScene(self)
        self._item = QGraphicsPixmapItem(pixmap)
        scene.addItem(self._item)
        scene.setSceneRect(self._item.boundingRect())
        self.setScene(scene)

        self.setRenderHints(
            self.renderHints()
            | QPainter.RenderHint.SmoothPixmapTransform
            | QPainter.RenderHint.Antialiasing
        )
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)

        self._min_scale = 0.1
        self._max_scale = 10.0

    def wheelEvent(self, event: QWheelEvent) -> None:
        """鼠标滚轮缩放."""
        if event.angleDelta().y() > 0:
            factor = 1.2
        else:
            factor = 1 / 1.2

        current_scale = self.transform().m11()
        new_scale = current_scale * factor
        if new_scale < self._min_scale:
            factor = self._min_scale / current_scale
        elif new_scale > self._max_scale:
            factor = self._max_scale / current_scale

        self.scale(factor, factor)

    def fit_to_window(self) -> None:
        """缩放至铺满整个视图."""
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.IgnoreAspectRatio)


class ProbabilityChartDialog(QDialog):
    """独立窗口显示预测概率折线图，支持缩放与拖动."""

    def __init__(self, details: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("预测概率折线图")
        self.resize(1100, 850)

        layout = QVBoxLayout(self)

        group_probs = details.get("group_probabilities")
        if group_probs:
            pixmap = build_group_probability_chart_pixmap(
                group_probs,
                lookback=details.get("lookback", "-"),
                diversity_boost=details.get("diversity_boost", "-"),
                model_name=details.get("model_name", "XGBoost"),
            )
        else:
            pixmap = build_probability_chart_pixmap(
                red_probabilities=details.get("red_probabilities", []),
                blue_probabilities=details.get("blue_probabilities", []),
                lookback=details.get("lookback", "-"),
                diversity_boost=details.get("diversity_boost", "-"),
            )
        self.chart_view = ChartGraphicsView(pixmap, self)
        layout.addWidget(self.chart_view)

        btn_layout = QHBoxLayout()
        fit_btn = QPushButton("适应窗口")
        fit_btn.setToolTip("将图表缩放到适合当前窗口")
        fit_btn.clicked.connect(self.chart_view.fit_to_window)
        btn_layout.addWidget(fit_btn)

        zoom_in_btn = QPushButton("放大")
        zoom_in_btn.setToolTip("放大图表")
        zoom_in_btn.clicked.connect(lambda: self.chart_view.scale(1.2, 1.2))
        btn_layout.addWidget(zoom_in_btn)

        zoom_out_btn = QPushButton("缩小")
        zoom_out_btn.setToolTip("缩小图表")
        zoom_out_btn.clicked.connect(lambda: self.chart_view.scale(1 / 1.2, 1 / 1.2))
        btn_layout.addWidget(zoom_out_btn)

        btn_layout.addStretch()

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def showEvent(self, event: QEvent) -> None:
        """窗口首次显示时铺满图表."""
        super().showEvent(event)
        self.chart_view.fit_to_window()
