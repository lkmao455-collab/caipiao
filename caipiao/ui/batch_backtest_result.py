"""批量历史回测汇总结果数据类.

本模块现在从 ``caipiao.core.backtest_data`` 重新导出 ``BatchBacktestResult``，
保持与既有导入路径的向后兼容。
"""

from __future__ import annotations

from ..core.backtest_data import BatchBacktestResult

__all__ = ["BatchBacktestResult"]
