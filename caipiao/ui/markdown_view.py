"""Markdown 文档查看器.

渲染管线移植自 md_reader（PyQt5 -> PySide6）：

    protect_latex(text) -> markdown.markdown(..., extensions=[...]) -> restore_latex
    -> 套用主题 CSS 与 MathJax 脚本 -> QWebEngineView.setHtml(html, base_url)

若运行环境缺少 QtWebEngine 或 markdown 库，会自动降级为 QTextBrowser 显示，
保证帮助文档始终可读，不会导致主程序无法启动。
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..utils.encoding_utils import read_text_file
from ..utils.latex_utils import get_mathjax_script, protect_latex, restore_latex

# markdown 为可选依赖：缺失时降级为纯文本显示，而不是让整个应用导入失败。
try:
    import markdown as _markdown
except Exception:  # noqa: BLE001
    _markdown = None

# QtWebEngine 为可选组件：缺失时降级为 QTextBrowser。
try:
    from PySide6.QtWebEngineWidgets import QWebEngineView

    _WEBENGINE_AVAILABLE = True
except Exception:  # noqa: BLE001
    QWebEngineView = None  # type: ignore[assignment]
    _WEBENGINE_AVAILABLE = False

# 用于在系统浏览器中打开外部链接（可选，失败则链接在内嵌视图中打开）。
try:
    from PySide6.QtWebEngineCore import QWebEnginePage
except Exception:  # noqa: BLE001
    QWebEnginePage = None  # type: ignore[assignment]

_THEME_DIR = Path(__file__).resolve().parent / "md_themes"

# 与 md_reader 保持一致的 Markdown 扩展组合。
_MD_EXTENSIONS = ["extra", "codehilite", "toc", "tables", "fenced_code"]


def _load_theme_css(dark: bool) -> str:
    """读取主题 CSS（含 GitHub 风格排版与 Pygments 代码高亮调色板）."""
    path = _THEME_DIR / ("dark.css" if dark else "light.css")
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def render_markdown_html(text: str, dark: bool = False) -> str:
    """将 Markdown 文本渲染为完整的 HTML 文档字符串.

    markdown 库不可用时，退化为在 <pre> 中原样展示文本。
    """
    css = _load_theme_css(dark)
    if _markdown is None:
        import html as _html

        html_body = f"<pre>{_html.escape(text)}</pre>"
        mathjax = ""
    else:
        protected, placeholders = protect_latex(text)
        html_body = _markdown.markdown(protected, extensions=_MD_EXTENSIONS)
        html_body = restore_latex(html_body, placeholders)
        mathjax = get_mathjax_script()

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
{css}
</style>
{mathjax}
</head>
<body>
{html_body}
</body>
</html>"""


if _WEBENGINE_AVAILABLE and QWebEnginePage is not None:

    class _HelpWebPage(QWebEnginePage):
        """把外部链接交给系统浏览器，内部锚点/本地资源仍在视图内跳转."""

        def acceptNavigationRequest(self, url, nav_type, is_main_frame):  # noqa: N802
            if nav_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
                if url.scheme() in ("http", "https", "mailto"):
                    QDesktopServices.openUrl(url)
                    return False
            return super().acceptNavigationRequest(url, nav_type, is_main_frame)


class MarkdownView(QWidget):
    """内嵌的 Markdown 渲染视图（优先 QWebEngine，缺失时用 QTextBrowser）."""

    def __init__(self, dark: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._dark = dark
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if _WEBENGINE_AVAILABLE:
            self._web = QWebEngineView(self)
            if QWebEnginePage is not None:
                self._web.setPage(_HelpWebPage(self._web))
            self._browser = None
            layout.addWidget(self._web)
        else:
            self._web = None
            self._browser = QTextBrowser(self)
            self._browser.setOpenExternalLinks(True)
            layout.addWidget(self._browser)

    def show_markdown_text(self, text: str, base_dir: str | os.PathLike | None = None) -> None:
        """渲染并显示一段 Markdown 文本."""
        html = render_markdown_html(text, dark=self._dark)
        if self._web is not None:
            base_url = QUrl("file:///")
            if base_dir and os.path.isdir(base_dir):
                # 结尾必须带分隔符，QWebEngine 才能正确解析相对路径（如图片）。
                base_url = QUrl.fromLocalFile(str(base_dir) + os.sep)
            self._web.setHtml(html, base_url)
        else:
            if base_dir and os.path.isdir(base_dir):
                self._browser.setSearchPaths([str(base_dir)])
            self._browser.setHtml(html)

    def show_markdown_file(self, path: str | os.PathLike) -> None:
        """读取并显示一个 Markdown 文件（自动检测编码）."""
        path = Path(path)
        try:
            text = read_text_file(str(path))
        except OSError as exc:
            text = f"# 无法打开文档\n\n未能读取 `{path}`：{exc}"
        self.show_markdown_text(text, base_dir=path.parent)


class MarkdownDialog(QDialog):
    """用于帮助文档展示的 Markdown 对话框."""

    def __init__(
        self,
        title: str,
        md_path: str | os.PathLike,
        dark: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(900, 700)

        layout = QVBoxLayout(self)
        self.view = MarkdownView(dark=dark, parent=self)
        layout.addWidget(self.view, 1)

        close_btn = QPushButton("关闭", self)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

        self.view.show_markdown_file(md_path)
