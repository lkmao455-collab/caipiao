"""项目统一的日志工厂。

新一批 Web 模块通过 ``from caipiao.log import get_logger`` 获取 logger，
此处提供与项目既有约定（标准库 ``logging.getLogger``）一致的封装，
并将名称归一到 ``caipiao`` 命名空间下，便于统一过滤与配置。
"""

from __future__ import annotations

import logging

_BASE = "caipiao"


def get_logger(name: str | None = None) -> logging.Logger:
    """返回位于 ``caipiao`` 命名空间下的 logger。

    - ``get_logger(__name__)``：``caipiao.web.ai_engine`` 这类已带前缀的名称原样保留。
    - ``get_logger("foo")``：归并为 ``caipiao.foo``。
    - ``get_logger()`` / ``get_logger("__main__")``：归并为 ``caipiao``。
    """
    if name is None or name == "__main__":
        name = _BASE
    elif name != _BASE and not name.startswith(_BASE + "."):
        name = f"{_BASE}.{name}"
    return logging.getLogger(name)
