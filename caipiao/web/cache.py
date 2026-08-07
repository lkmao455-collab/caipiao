"""缓存模块：提供内存缓存和Redis缓存两种实现。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from collections.abc import Callable
from functools import wraps
from typing import Any

logger = logging.getLogger(__name__)

# 内存缓存实现
_memory_cache: dict[str, tuple[Any, float]] = {}
_memory_cache_lock = asyncio.Lock()


def _get_cache_key(*args: Any, **kwargs: Any) -> str:
    """生成缓存键。"""
    key_parts = [str(arg) for arg in args]
    key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
    raw_key = ":".join(key_parts)
    return hashlib.md5(raw_key.encode()).hexdigest()


async def get_from_cache(key: str, ttl: int = 300) -> Any | None:
    """从内存缓存获取数据。"""
    async with _memory_cache_lock:
        if key in _memory_cache:
            value, timestamp = _memory_cache[key]
            if time.time() - timestamp < ttl:
                return value
            else:
                del _memory_cache[key]
    return None


async def set_to_cache(key: str, value: Any, ttl: int = 300) -> None:
    """设置内存缓存。"""
    async with _memory_cache_lock:
        _memory_cache[key] = (value, time.time())
        # 清理过期缓存
        current_time = time.time()
        expired_keys = [
            k for k, (_, timestamp) in _memory_cache.items()
            if current_time - timestamp >= ttl
        ]
        for k in expired_keys:
            del _memory_cache[k]


async def invalidate_cache(pattern: str) -> int:
    """根据模式清除缓存。"""
    async with _memory_cache_lock:
        keys_to_delete = [
            k for k in _memory_cache
            if pattern in k
        ]
        for k in keys_to_delete:
            del _memory_cache[k]
        return len(keys_to_delete)


def cached(ttl: int = 300, key_prefix: str = "") -> Callable:
    """缓存装饰器：自动缓存函数结果。"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # 生成缓存键
            cache_key = f"{key_prefix}:{_get_cache_key(*args, **kwargs)}"
            
            # 尝试从缓存获取
            cached_value = await get_from_cache(cache_key, ttl)
            if cached_value is not None:
                return cached_value
            
            # 执行函数并缓存结果
            result = await func(*args, **kwargs)
            await set_to_cache(cache_key, result, ttl)
            return result
        return wrapper
    return decorator


def clear_all_cache() -> int:
    """清除所有内存缓存。"""
    count = len(_memory_cache)
    _memory_cache.clear()
    return count


# Redis缓存实现（可选）
class RedisCache:
    """基于Redis的缓存实现。"""
    
    def __init__(self, redis_url: str) -> None:
        import redis
        self._redis = redis.from_url(redis_url)
    
    async def get(self, key: str) -> Any | None:
        """从Redis获取缓存。"""
        try:
            data = self._redis.get(key)
            if data:
                return json.loads(data)
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug("Redis get failed: %s", exc)
        return None

    async def set(self, key: str, value: Any, ttl: int = 300) -> None:
        """设置Redis缓存。"""
        try:
            self._redis.setex(key, ttl, json.dumps(value, default=str))
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug("Redis set failed: %s", exc)

    async def delete(self, key: str) -> bool:
        """删除Redis缓存。"""
        try:
            return bool(self._redis.delete(key))
        except OSError as exc:
            logger.debug("Redis delete failed: %s", exc)
            return False

    async def clear_pattern(self, pattern: str) -> int:
        """根据模式清除缓存。"""
        try:
            keys = self._redis.keys(f"*{pattern}*")
            if keys:
                return self._redis.delete(*keys)
        except OSError as exc:
            logger.debug("Redis clear_pattern failed: %s", exc)
        return 0


# 全局缓存实例
def create_cache() -> RedisCache | None:
    """根据环境变量创建缓存实例。"""
    redis_url = os.getenv("CAIPIAO_WEB_REDIS_URL")
    if redis_url:
        try:
            return RedisCache(redis_url)
        except (ImportError, OSError) as exc:
            logger.debug("Redis cache init failed, falling back to memory cache: %s", exc)
    return None


# 全局缓存实例（Redis可用时使用Redis，否则使用内存缓存）
redis_cache = create_cache()