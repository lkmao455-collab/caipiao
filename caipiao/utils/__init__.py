"""工具模块."""

from __future__ import annotations

import sys
from pathlib import Path


def app_data_dir() -> Path:
    """返回应用数据目录，位于应用入口文件（main.py）所在目录的 .caipiao 子目录下。

    该目录用于替代原先写入用户主目录 ``~/.caipiao`` 的方案，使应用在便携
    部署或打包运行时，数据直接保存在应用目录下，便于迁移与管理。
    """
    if getattr(sys, "frozen", False):
        # PyInstaller 等打包环境：入口目录为 sys._MEIPASS 或 executable 所在目录
        try:
            base = Path(sys._MEIPASS)
        except AttributeError:
            base = Path(sys.executable).resolve().parent
    else:
        # 源码运行：以 main.py 所在目录作为应用根目录
        base = Path(sys.argv[0]).resolve().parent
    d = base / ".caipiao"
    d.mkdir(parents=True, exist_ok=True)
    return d

