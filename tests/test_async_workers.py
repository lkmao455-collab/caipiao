"""异步工作模块测试."""

import asyncio
import pytest

from caipiao.ui.async_workers import AsyncFetcher, AsyncWorker, run_async_in_thread


class TestAsyncWorker:
    """AsyncWorker 测试."""

    def test_initialization(self):
        worker = AsyncWorker()
        assert worker is not None


class TestAsyncFetcher:
    """AsyncFetcher 测试."""

    def test_initialization(self):
        fetcher = AsyncFetcher()
        assert fetcher is not None

    def test_shutdown(self):
        fetcher = AsyncFetcher()
        fetcher.shutdown()


class TestRunAsyncInThread:
    """run_async_in_thread 测试."""

    def test_run_async(self):
        async def simple_coro():
            return 42

        result = None
        error = None

        def callback(r, e):
            nonlocal result, error
            result = r
            error = e

        thread = run_async_in_thread(simple_coro(), callback)
        thread.wait(5000)

        assert result == 42
        assert error is None

    def test_run_async_with_error(self):
        async def error_coro():
            raise ValueError("test error")

        result = None
        error = None

        def callback(r, e):
            nonlocal result, error
            result = r
            error = e

        thread = run_async_in_thread(error_coro(), callback)
        thread.wait(5000)

        assert result is None
        assert error is not None
        assert "test error" in str(error)


class TestAsyncWorkerIntegration:
    """AsyncWorker 集成测试."""

    def test_worker_initialization(self):
        worker = AsyncWorker()
        assert worker._executor is not None
