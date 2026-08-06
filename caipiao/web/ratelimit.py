"""速率限制：基于 slowapi，按调用方（Token / API Key / IP）限流。

- 默认限制对所有被 ``@limiter.limit()`` 装饰的路由生效（default_limits 在请求时读取，便于测试覆盖）。
- 重接口（/generate、/backtest）使用更严格的显式限制。
"""

from __future__ import annotations

import os

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

DEFAULT_RATE_LIMIT = os.getenv("CAIPIAO_WEB_RATE_LIMIT", "600/minute")


def default_limit(*_args) -> str:
    """默认限流值（请求时读取环境变量，便于测试覆盖与运行时调整）。"""
    return os.getenv("CAIPIAO_WEB_RATE_LIMIT", "600/minute")


def _rate_key(request: Request) -> str:
    """以 Token / API Key / 远程地址作为限流桶标识，实现按用户/Key 限流。"""
    auth = request.headers.get("authorization")
    if auth:
        return f"tok:{auth}"
    api_key = request.headers.get("x-api-key")
    if api_key:
        return f"key:{api_key}"
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(key_func=_rate_key, default_limits=[DEFAULT_RATE_LIMIT])
