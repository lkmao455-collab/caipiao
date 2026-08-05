"""异步工作模块.

提供基于 asyncio 的异步网络请求和后台任务执行，
作为 QThread 的替代方案，提供更好的资源利用和错误处理。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

from PySide6.QtCore import QObject, QThread, Signal

logger = logging.getLogger(__name__)

T = TypeVar("T")


class AsyncWorker(QObject):
    """异步工作器基类.

    提供在后台线程中运行 asyncio 事件循环的能力。
    """

    finished = Signal(object, object)  # (result, error)
    progress = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._executor = ThreadPoolExecutor(max_workers=4)

    def start_async(self, coro: Coroutine) -> None:
        """启动异步任务."""
        self._thread = QThread()
        self._thread.run = lambda: self._run_loop(coro)
        self._thread.finished.connect(self._cleanup)
        self._thread.start()

    def _run_loop(self, coro: Coroutine) -> None:
        """在子线程中运行事件循环."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            result = self._loop.run_until_complete(coro)
            self.finished.emit(result, None)
        except Exception as exc:  # noqa: BLE001
            self.finished.emit(None, exc)
        finally:
            self._loop.close()

    def _cleanup(self) -> None:
        """清理资源."""
        self._executor.shutdown(wait=False)

    def stop(self) -> None:
        """停止工作器."""
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(3000)


class AsyncFetcher:
    """异步数据获取器.

    使用线程池执行阻塞的网络请求，避免阻塞 UI 线程。
    """

    def __init__(self, max_workers: int = 4) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._running_tasks: dict[str, asyncio.Task] = {}

    async def fetch_all_async(
        self,
        profile: Any,
        timeout: int = 60,
        callback: Callable[[str], None] | None = None,
    ) -> Any:
        """异步获取全部历史数据."""
        from ..data.fetcher import LotteryDataFetcher

        def _fetch():
            if callback:
                callback("正在获取数据...")
            fetcher = LotteryDataFetcher(profile=profile, timeout=timeout)
            return fetcher.fetch_all()

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, _fetch)

    async def fetch_latest_async(
        self,
        profile: Any,
        timeout: int = 15,
        callback: Callable[[str], None] | None = None,
    ) -> Any:
        """异步获取最新一期数据."""
        from ..data.fetcher import LotteryDataFetcher

        def _fetch():
            if callback:
                callback("正在获取最新数据...")
            fetcher = LotteryDataFetcher(profile=profile, timeout=timeout)
            return fetcher.fetch_latest()

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, _fetch)

    async def fetch_multiple_async(
        self,
        tasks: list[Callable[[], Any]],
        callback: Callable[[str], None] | None = None,
    ) -> list[Any]:
        """异步执行多个任务."""
        results = []
        for i, task in enumerate(tasks):
            if callback:
                callback(f"执行任务 {i + 1}/{len(tasks)}...")
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(self._executor, task)
            results.append(result)
        return results

    def shutdown(self) -> None:
        """关闭执行器."""
        self._executor.shutdown(wait=True)


class AsyncTrainWorker(AsyncWorker):
    """异步训练工作器."""

    def start_training(
        self,
        records: list[Any],
        lookback: int,
        model_path: Any,
        model_class: Any,
        prefix: str,
        incremental: bool = False,
        new_count: int = 0,
    ) -> None:
        """启动异步训练."""
        coro = self._train_coroutine(
            records, lookback, model_path, model_class, prefix, incremental, new_count
        )
        self.start_async(coro)

    async def _train_coroutine(
        self,
        records: list[Any],
        lookback: int,
        model_path: Any,
        model_class: Any,
        prefix: str,
        incremental: bool,
        new_count: int,
    ) -> Any:
        """训练协程."""
        from ..ml.predictor import MLPredictor

        def _train():
            self.progress.emit("正在训练模型...")

            if model_class is not None:
                predictor = MLPredictor(
                    records,
                    lookback=lookback,
                    model_path=model_path,
                    model_class=model_class,
                )
            else:
                predictor = MLPredictor(
                    records,
                    lookback=lookback,
                    model_path=model_path,
                )

            if incremental and new_count > 0:
                success = predictor.train_incremental(
                    new_count=new_count,
                    progress_callback=lambda c, t: self.progress.emit(f"训练进度: {c}/{t}"),
                )
                if not success:
                    predictor.train(
                        progress_callback=lambda c, t: self.progress.emit(f"训练进度: {c}/{t}"),
                    )
            else:
                predictor.train(
                    progress_callback=lambda c, t: self.progress.emit(f"训练进度: {c}/{t}"),
                )

            return True

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, _train)


class AsyncGenerateWorker(AsyncWorker):
    """异步号码生成工作器。"""

    def start_generation(
        self,
        engine: Any,
        strategy_id: str,
        count: int,
        options: dict,
    ) -> None:
        """启动异步生成."""
        coro = self._generate_coroutine(engine, strategy_id, count, options)
        self.start_async(coro)

    async def _generate_coroutine(
        self,
        engine: Any,
        strategy_id: str,
        count: int,
        options: dict,
    ) -> Any:
        """生成协程."""
        def _generate():
            self.progress.emit("正在生成号码...")
            return engine.generate(strategy_id, count=count, options=options)

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, _generate)


class AsyncBatchWorker(AsyncWorker):
    """异步批量处理工作器。"""

    def start_batch(
        self,
        tasks: list[Callable[[], Any]],
        description: str = "批量处理",
    ) -> None:
        """启动批量任务."""
        coro = self._batch_coroutine(tasks, description)
        self.start_async(coro)

    async def _batch_coroutine(
        self,
        tasks: list[Callable[[], Any]],
        description: str,
    ) -> list[Any]:
        """批量处理协程."""
        results = []
        for i, task in enumerate(tasks):
            self.progress.emit(f"{description}: {i + 1}/{len(tasks)}")
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(self._executor, task)
            results.append(result)
        return results


def run_async_in_thread(
    coro: Coroutine,
    callback: Callable[[Any, Exception | None], None] | None = None,
) -> QThread:
    """在后台线程中运行协程.

    Args:
        coro: 要运行的协程
        callback: 完成回调 (result, error)

    Returns:
        运行的线程
    """
    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(coro)
            if callback:
                callback(result, None)
        except Exception as exc:  # noqa: BLE001
            if callback:
                callback(None, exc)
        finally:
            loop.close()

    thread = QThread()
    thread.run = _run
    thread.start()
    return thread
