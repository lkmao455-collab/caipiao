"""通用机器学习特征工程（按彩种档案驱动）.

为每个号码组（组内每个候选号码）提取出现次数、最近距离、出现频率，
并加入窗口聚合统计与时间特征。
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np

from ..core.profile import LotteryProfile, NumberGroup
from ..data.models import DrawRecord


def build_features(
    records: List[DrawRecord],
    profile: LotteryProfile,
    lookback: int = 50,
) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
    """构建训练特征与标签.

    Returns:
        X: 特征矩阵 (samples, features)
        y_dict: 每个号码组的标签矩阵；组合组为 (samples, group.size)，
                按位组(3D)为 (samples, group.count) 的整数类别标签。
    """
    if lookback <= 0:
        raise ValueError("lookback 必须大于 0")
    if len(records) <= lookback:
        return np.array([]), {}

    X = []
    y_dict: Dict[str, List[np.ndarray]] = {g.key: [] for g in profile.groups}
    for i in range(lookback, len(records)):
        window = records[i - lookback : i]
        rec = records[i]
        X.append(_extract_window_features(window, profile))
        for g in profile.groups:
            nums = rec.groups.get(g.key, [])
            if g.positional:
                # 按位组：每个位置一个类别标签
                label = np.array(nums, dtype=np.int32)
            else:
                label = np.zeros(g.size, dtype=np.int32)
                for n in nums:
                    if g.lo <= n <= g.hi:
                        label[n - g.lo] = 1
            y_dict[g.key].append(label)

    return np.array(X, dtype=np.float32), {
        k: np.array(v) for k, v in y_dict.items()
    }


def build_prediction_features(
    records: List[DrawRecord],
    profile: LotteryProfile,
    lookback: int = 50,
) -> np.ndarray:
    """为最新一期构建预测特征."""
    if lookback <= 0:
        raise ValueError("lookback 必须大于 0")
    if len(records) < lookback:
        return np.array([])
    window = records[-lookback:]
    features = _extract_window_features(window, profile)
    return features.reshape(1, -1)


def _extract_window_features(window: List[DrawRecord], profile: LotteryProfile) -> np.ndarray:
    features: List[float] = []
    for g in profile.groups:
        for n in g.values:
            features.extend(_number_features(window, g, n))
    features.extend(_window_stats(window, profile))
    last = window[-1]
    features.extend(
        [
            last.draw_date.month / 12.0,
            last.draw_date.day / 31.0,
            last.draw_date.weekday() / 7.0,
        ]
    )
    return np.array(features, dtype=np.float32)


def _number_features(window: List[DrawRecord], group: NumberGroup, number: int) -> List[float]:
    appears = []
    for idx, record in enumerate(window):
        nums = record.groups.get(group.key, [])
        if number in nums:
            appears.append(idx)
    count = len(appears)
    last_distance = (len(window) - 1 - appears[-1]) if appears else len(window)
    freq = count / len(window)
    return [count / 10.0, last_distance / len(window), freq]


def _window_stats(window: List[DrawRecord], profile: LotteryProfile) -> List[float]:
    primary = profile.primary_group
    if primary is None:
        raise ValueError("profile 缺少 primary_group")
    sums = []
    odd_counts = []
    high_counts = []
    for record in window:
        nums = record.groups.get(primary.key, [])
        sums.append(sum(nums))
        odd_counts.append(sum(1 for b in nums if b % 2 == 1))
        high_counts.append(sum(1 for b in nums if b >= primary.high_low_border))

    denom = max(primary.count, 1)
    return [
        np.mean(sums) / 200.0,
        np.std(sums) / 50.0 if len(sums) > 1 else 0.0,
        np.mean(odd_counts) / denom,
        np.mean(high_counts) / denom,
    ]
