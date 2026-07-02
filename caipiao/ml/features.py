"""特征工程."""

from __future__ import annotations

from typing import List, Tuple

import numpy as np

from ..data.models import DrawRecord

RED_COUNT = 33
BLUE_COUNT = 16


def build_features(
    records: List[DrawRecord], lookback: int = 50
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """构建训练特征和标签（仅支持双色球）.

    Args:
        records: 按时间排序的开奖记录（必须为双色球）。
        lookback: 回看期数。

    Returns:
        X: 特征矩阵，形状 (samples, features)
        y_red: 红球标签，形状 (samples, 33)，每列为是否出现
        y_blue: 蓝球标签，形状 (samples, 16)，每列为是否出现
    """
    if any(r.profile.key != "ssq" for r in records):
        raise ValueError("features.build_features 仅支持双色球记录")
    if len(records) <= lookback:
        return np.array([]), np.array([]), np.array([])

    samples = len(records) - lookback
    X = []
    y_red = []
    y_blue = []

    for i in range(lookback, len(records)):
        window = records[i - lookback : i]
        next_record = records[i]

        features = _extract_window_features(window)
        X.append(features)

        red_label = np.zeros(RED_COUNT, dtype=np.int32)
        for n in next_record.red_balls:
            red_label[n - 1] = 1
        y_red.append(red_label)

        blue_label = np.zeros(BLUE_COUNT, dtype=np.int32)
        blue = next_record.blue_ball
        if blue is not None:
            blue_label[blue - 1] = 1
        y_blue.append(blue_label)

    return np.array(X), np.array(y_red), np.array(y_blue)


def build_prediction_features(
    records: List[DrawRecord], lookback: int = 50
) -> np.ndarray:
    """为最新一期构建预测特征（仅支持双色球）。"""
    if any(r.profile.key != "ssq" for r in records):
        raise ValueError("features.build_prediction_features 仅支持双色球记录")
    if len(records) < lookback:
        return np.array([])
    window = records[-lookback:]
    features = _extract_window_features(window)
    return features.reshape(1, -1)


def _extract_window_features(window: List[DrawRecord]) -> np.ndarray:
    """从窗口中提取特征向量."""
    features = []

    # 1. 每个红球的统计特征
    for n in range(1, RED_COUNT + 1):
        features.extend(_number_features(window, n, is_red=True))

    # 2. 每个蓝球的统计特征
    for n in range(1, BLUE_COUNT + 1):
        features.extend(_number_features(window, n, is_red=False))

    # 3. 窗口整体统计特征
    features.extend(_window_stats(window))

    # 4. 时间特征（使用最后一期）
    last = window[-1]
    features.extend(
        [
            last.draw_date.month / 12.0,
            last.draw_date.day / 31.0,
            last.draw_date.weekday() / 7.0,
        ]
    )

    return np.array(features, dtype=np.float32)


def _number_features(
    window: List[DrawRecord], number: int, is_red: bool
) -> List[float]:
    """单个号码的特征：出现次数、最近一次出现距离、出现频率."""
    appears = []
    for idx, record in enumerate(window):
        nums = record.red_balls if is_red else ([record.blue_ball] if record.blue_ball is not None else [])
        if number in nums:
            appears.append(idx)

    count = len(appears)
    last_distance = (len(window) - 1 - appears[-1]) if appears else len(window)
    freq = count / len(window)

    return [count / 10.0, last_distance / len(window), freq]


def _window_stats(window: List[DrawRecord]) -> List[float]:
    """窗口期数的聚合统计."""
    sums = [sum(r.red_balls) for r in window]
    odd_counts = [sum(1 for b in r.red_balls if b % 2 == 1) for r in window]
    high_counts = [sum(1 for b in r.red_balls if b >= 17) for r in window]

    blue_balls = [r.blue_ball for r in window if r.blue_ball is not None]

    return [
        np.mean(sums) / 200.0,
        np.std(sums) / 50.0 if len(sums) > 1 else 0.0,
        np.mean(odd_counts) / 6.0,
        np.mean(high_counts) / 6.0,
        np.mean(blue_balls) / 16.0 if blue_balls else 0.0,
    ]
