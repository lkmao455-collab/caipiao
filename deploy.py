#!/usr/bin/env python3
"""部署脚本.

提供应用部署、打包和分发功能。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


def check_python_version() -> bool:
    """检查 Python 版本."""
    if sys.version_info < (3, 10):
        print(f"错误: 需要 Python 3.10+，当前版本 {sys.version}")
        return False
    return True


def check_dependencies() -> bool:
    """检查依赖是否安装."""
    try:
        import PySide6
        import numpy
        import xgboost
        print("依赖检查通过")
        return True
    except ImportError as e:
        print(f"缺少依赖: {e}")
        print("请运行: pip install -r requirements.txt")
        return False


def install_dependencies() -> bool:
    """安装依赖."""
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
            check=True,
        )
        print("依赖安装成功")
        return True
    except subprocess.CalledProcessError as e:
        print(f"依赖安装失败: {e}")
        return False


def run_tests() -> bool:
    """运行测试."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-q"],
            capture_output=True,
            text=True,
        )
        print(result.stdout)
        if result.returncode != 0:
            print(f"测试失败:\n{result.stderr}")
            return False
        return True
    except subprocess.CalledProcessError as e:
        print(f"测试运行失败: {e}")
        return False


def build_distribution(output_dir: Optional[str] = None) -> bool:
    """构建分发包."""
    if output_dir is None:
        output_dir = "dist"

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # 复制必要文件
    files_to_copy = [
        "main.py",
        "requirements.txt",
        "README.md",
        "CHANGELOG.md",
        "caipiao/",
        "docs/",
    ]

    for item in files_to_copy:
        src = Path(item)
        if src.is_dir():
            dst = output_path / item
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        elif src.is_file():
            shutil.copy2(src, output_path)

    print(f"分发包已构建到 {output_path}")
    return True


def create_portable_package(output_dir: Optional[str] = None) -> bool:
    """创建便携版包."""
    if output_dir is None:
        output_dir = "portable"

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # 创建启动脚本
    if sys.platform == "win32":
        launcher = output_path / "启动彩票生成器.bat"
        launcher.write_text("@echo off\npython main.py\n", encoding="utf-8")
    else:
        launcher = output_path / "启动彩票生成器.sh"
        launcher.write_text("#!/bin/bash\npython main.py\n", encoding="utf-8")
        launcher.chmod(0o755)

    # 复制必要文件
    files_to_copy = [
        "main.py",
        "requirements.txt",
        "README.md",
        "CHANGELOG.md",
        "caipiao/",
    ]

    for item in files_to_copy:
        src = Path(item)
        if src.is_dir():
            dst = output_path / item
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        elif src.is_file():
            shutil.copy2(src, output_path)

    print(f"便携版已创建到 {output_path}")
    return True


def main():
    """主函数."""
    parser = argparse.ArgumentParser(description="彩票号码生成器部署工具")
    parser.add_argument(
        "action",
        choices=["check", "install", "test", "build", "portable", "all"],
        help="执行的操作",
    )
    parser.add_argument("--output", "-o", help="输出目录")

    args = parser.parse_args()

    # 设置日志
    logging.basicConfig(level=logging.INFO)

    if args.action == "check":
        if check_python_version() and check_dependencies():
            print("部署检查通过")
        else:
            sys.exit(1)

    elif args.action == "install":
        if not check_python_version():
            sys.exit(1)
        if not install_dependencies():
            sys.exit(1)

    elif args.action == "test":
        if not run_tests():
            sys.exit(1)

    elif args.action == "build":
        if not build_distribution(args.output):
            sys.exit(1)

    elif args.action == "portable":
        if not create_portable_package(args.output):
            sys.exit(1)

    elif args.action == "all":
        if not check_python_version():
            sys.exit(1)
        if not check_dependencies():
            if not install_dependencies():
                sys.exit(1)
        if not run_tests():
            sys.exit(1)
        if not build_distribution(args.output):
            sys.exit(1)
        print("部署完成")


if __name__ == "__main__":
    main()
