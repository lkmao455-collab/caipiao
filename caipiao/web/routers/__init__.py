"""Web 路由包。"""

from __future__ import annotations

from . import api_keys, auth, backtest, generate, profiles, user

__all__ = ["auth", "profiles", "generate", "backtest", "user", "api_keys"]
