#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LaTeX 公式保护工具 - 防止 Markdown 解析器破坏数学公式。
"""

import re

_INLINE_PLACEHOLDER = "<!--MDMATHINLINE{:d}-->"
_DISPLAY_PLACEHOLDER = "<!--MDMATHDISPLAY{:d}-->"


def protect_latex(text):
    """
    在 Markdown 解析前保护 LaTeX 公式。

    支持：
    - 行内公式：$...$
    - 块级公式：$$...$$

    Args:
        text: 原始 Markdown 文本

    Returns:
        tuple: (处理后的文本, placeholders 字典)
    """
    placeholders = {}
    counter = [0]

    def replace_display(match):
        key = _DISPLAY_PLACEHOLDER.format(counter[0])
        placeholders[key] = match.group(0)
        counter[0] += 1
        return key

    def replace_inline(match):
        key = _INLINE_PLACEHOLDER.format(counter[0])
        placeholders[key] = match.group(0)
        counter[0] += 1
        return key

    # 先匹配 $$...$$（块级），允许换行
    text = re.sub(r"(?<!\\)\$\$(.+?)(?<!\\)\$\$", replace_display, text, flags=re.DOTALL)

    # 再匹配 $...$（行内），不包含换行，避免已匹配的 $$
    text = re.sub(r"(?<!\\)\$([^$\n]+?)(?<!\\)\$", replace_inline, text)

    return text, placeholders


def restore_latex(html, placeholders):
    """
    在 Markdown 解析后恢复 LaTeX 公式。

    Args:
        html: Markdown 解析后的 HTML
        placeholders: protect_latex 返回的字典

    Returns:
        str: 恢复公式后的 HTML
    """
    for key, val in placeholders.items():
        html = html.replace(key, val)
    return html


def get_mathjax_script():
    """
    返回 MathJax 3 的 HTML script 配置片段。

    Returns:
        str: HTML script 标签字符串
    """
    return """<script>
window.MathJax = {
  tex: {
    inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
    displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']],
    processEscapes: true
  },
  options: {
    skipHtmlTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code']
  }
};
</script>
<script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>"""
