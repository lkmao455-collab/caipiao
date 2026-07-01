"""帮助文档 Markdown 渲染测试."""

import pytest


def test_latex_protect_restore_roundtrip():
    from caipiao.utils.latex_utils import protect_latex, restore_latex

    text = "inline $a+b$ and display $$x^2$$ done"
    protected, placeholders = protect_latex(text)
    # 公式已被占位符替换，解析阶段不会再看到 $
    assert "$" not in protected
    assert restore_latex(protected, placeholders) == text


def test_render_markdown_html_markers():
    mv = pytest.importorskip("caipiao.ui.markdown_view")
    md = "# 标题\n\n**粗体**\n\n```python\nx = 1\n```\n\n| a | b |\n|---|---|\n| 1 | 2 |\n"
    html = mv.render_markdown_html(md, dark=False)
    assert "<strong>" in html          # markdown 转换生效
    assert "codehilite" in html         # 代码块高亮
    assert "<table>" in html            # 表格扩展
    assert "font-family" in html        # 主题 CSS 已注入
    assert "MathJax" in html            # LaTeX 支持脚本


def test_render_markdown_html_dark_theme_differs():
    mv = pytest.importorskip("caipiao.ui.markdown_view")
    light = mv.render_markdown_html("# t", dark=False)
    dark = mv.render_markdown_html("# t", dark=True)
    assert light != dark
