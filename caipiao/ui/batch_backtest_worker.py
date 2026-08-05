"""批量历史回测 worker 环境初始化.

本模块保留与多进程池启动相关的 UI/环境设置，worker 的核心数据处
理函数已迁移至 ``caipiao.core.backtest_worker``。为保持向后兼容，
原导出的符号仍在本模块重新导出。
"""

from __future__ import annotations

import atexit
import os
import random

import numpy as np

from caipiao.core.backtest_worker import (
    _cleanup_worker_temp_dir,
    _configure_worker_threads,
    _get_worker_temp_dir,
)


def init_worker_process(seed: int):
    """每个子进程启动时调用。"""
    _configure_worker_threads()
    worker_tmp = _get_worker_temp_dir()
    # 将模型缓存目录重定向到 worker 私有临时目录，避免多进程并发写入冲突。
    os.environ["CAIPIAO_MODEL_DIR"] = worker_tmp
    atexit.register(_cleanup_worker_temp_dir)
    random.seed(seed)
    np.random.seed(seed)
