"""特征工程（增强版）."""

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
    if lookback <= 0:
        raise ValueError("lookback 必须大于 0")
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
            if 1 <= n <= RED_COUNT:
                red_label[n - 1] = 1
        y_red.append(red_label)

        blue_label = np.zeros(BLUE_COUNT, dtype=np.int32)
        blue = next_record.blue_ball
        if blue is not None and 1 <= blue <= BLUE_COUNT:
            blue_label[blue - 1] = 1
        y_blue.append(blue_label)

    return np.array(X), np.array(y_red), np.array(y_blue)


def build_prediction_features(
    records: List[DrawRecord], lookback: int = 50
) -> np.ndarray:
    """为最新一期构建预测特征（仅支持双色球）。"""
    if any(r.profile.key != "ssq" for r in records):
        raise ValueError("features.build_prediction_features 仅支持双色球记录")
    if lookback <= 0:
        raise ValueError("lookback 必须大于 0")
    if len(records) < lookback:
        return np.array([])
    window = records[-lookback:]
    features = _extract_window_features(window)
    return features.reshape(1, -1)


def _extract_window_features(window: List[DrawRecord]) -> np.ndarray:
    """从窗口中提取特征向量."""
    features = []

    # 1. 每个红球的统计特征（含间隔分析、连续性）
    for n in range(1, RED_COUNT + 1):
        features.extend(_number_features(window, n, is_red=True))

    # 2. 每个蓝球的统计特征
    for n in range(1, BLUE_COUNT + 1):
        features.extend(_number_features(window, n, is_red=False))

    # 3. 窗口整体统计特征
    features.extend(_window_stats(window))

    # 4. 关联性特征
    features.extend(_correlation_features(window))

    # 5. 区间分布特征
    features.extend(_zone_distribution(window))

    # 6. AC值特征
    features.extend(_ac_value_features(window))

    # 7. 和值区间分布特征
    features.extend(_sum_distribution(window))

    # 8. 时间特征（使用最后一期）
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
    """单个号码的特征：出现次数、最近距离、频率 + 间隔统计 + 连续性."""
    appears = []
    for idx, record in enumerate(window):
        nums = record.red_balls if is_red else ([record.blue_ball] if record.blue_ball is not None else [])
        if number in nums:
            appears.append(idx)

    count = len(appears)
    last_distance = (len(window) - 1 - appears[-1]) if appears else len(window)
    freq = count / len(window)

    # 间隔统计：相邻出现位置的差值
    if len(appears) >= 2:
        gaps = [appears[i + 1] - appears[i] for i in range(len(appears) - 1)]
        gap_mean = np.mean(gaps) / len(window)
        gap_std = np.std(gaps) / len(window) if len(gaps) > 1 else 0.0
        gap_max = max(gaps) / len(window)
        gap_min = min(gaps) / len(window)
    else:
        gap_mean = gap_std = gap_max = gap_min = 0.0

    # 连续性：当前连续未出期数、历史最长连续出号期数
    current_streak = 0
    for idx in range(len(window) - 1, -1, -1):
        nums = window[idx].red_balls if is_red else ([window[idx].blue_ball] if window[idx].blue_ball is not None else [])
        if number not in nums:
            current_streak += 1
        else:
            break

    max_hit_streak = 0
    current_hit = 0
    for idx in range(len(window)):
        nums = window[idx].red_balls if is_red else ([window[idx].blue_ball] if window[idx].blue_ball is not None else [])
        if number in nums:
            current_hit += 1
            max_hit_streak = max(max_hit_streak, current_hit)
        else:
            current_hit = 0

    return [
        count / 10.0,
        last_distance / len(window),
        freq,
        gap_mean,
        gap_std,
        gap_max,
        gap_min,
        current_streak / len(window),
        max_hit_streak / len(window),
    ]


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


def _correlation_features(window: List[DrawRecord]) -> List[float]:
    """关联性特征：相邻号码(±1)共现频率、配对共现统计."""
    # 收集所有红球出现的位置
    number_positions: dict[int, list[int]] = {n: [] for n in range(1, RED_COUNT + 1)}
    for idx, record in enumerate(window):
        for n in record.red_balls:
            if 1 <= n <= RED_COUNT:
                number_positions[n].append(idx)

    # 相邻号码(±1)共现频率：号码n和n+1在同一期出现的次数
    adjacent_cooccur = 0
    adjacent_possible = 0
    for n in range(1, RED_COUNT):
        if number_positions[n] and number_positions[n + 1]:
            set_a = set(number_positions[n])
            set_b = set(number_positions[n + 1])
            adjacent_cooccur += len(set_a & set_b)
        if number_positions[n] or number_positions[n + 1]:
            adjacent_possible += 1

    adj_freq = adjacent_cooccur / max(len(window), 1)

    # 配对共现：任意两个号码在同一期出现的平均次数
    total_pairs = 0
    cooccur_count = 0
    for i in range(1, RED_COUNT + 1):
        for j in range(i + 1, RED_COUNT + 1):
            if number_positions[i] and number_positions[j]:
                set_a = set(number_positions[i])
                set_b = set(number_positions[j])
                pairs = len(set_a & set_b)
                if pairs > 0:
                    cooccur_count += pairs
                    total_pairs += 1

    avg_cooccur = cooccur_count / max(total_pairs, 1)

    return [
        adj_freq,
        adjacent_possible / max(RED_COUNT - 1, 1),
        avg_cooccur / max(len(window), 1),
    ]


def _zone_distribution(window: List[DrawRecord]) -> List[float]:
    """区间分布特征：1-11/12-22/23-33三区出号比例."""
    zone_counts = [0, 0, 0]
    for record in window:
        for n in record.red_balls:
            if 1 <= n <= 11:
                zone_counts[0] += 1
            elif 12 <= n <= 22:
                zone_counts[1] += 1
            elif 23 <= n <= 33:
                zone_counts[2] += 1

    total = sum(zone_counts)
    if total == 0:
        return [0.0, 0.0, 0.0, 0.0, 0.0]

    # 三区比例
    ratios = [c / total for c in zone_counts]

    # 区间分布均匀度（标准差越小越均匀）
    zone_std = np.std(ratios)

    return ratios + [zone_std]


def _ac_value_features(window: List[DrawRecord]) -> List[float]:
    """AC值特征：号码组合差值种类数（彩票界常用指标）.

    AC值 = 不同差值的个数 - (n-1)，其中n=6（红球个数）。
    历史AC值的均值和标准差可反映号码组合的离散程度。
    """
    ac_values = []
    for record in window:
        reds = sorted(record.red_balls)
        if len(reds) < 2:
            continue
        diffs = set()
        for i in range(len(reds)):
            for j in range(i + 1, len(reds)):
                diffs.add(abs(reds[i] - reds[j]))
        ac = len(diffs) - (len(reds) - 1)
        ac_values.append(ac)

    if not ac_values:
        return [0.0, 0.0, 0.0]

    return [
        np.mean(ac_values) / 10.0,
        np.std(ac_values) / 5.0 if len(ac_values) > 1 else 0.0,
        min(ac_values) / 10.0,
    ]


def _sum_distribution(window: List[DrawRecord]) -> List[float]:
    """和值区间分布特征：历史和值落入各区间的频率."""
    # 和值区间：0-60, 61-120, 121-180, 181-240
    zone_bounds = [0, 61, 121, 181, 241]
    zone_counts = [0] * 4

    for record in window:
        s = sum(record.red_balls)
        for z in range(4):
            if zone_bounds[z] <= s < zone_bounds[z + 1]:
                zone_counts[z] += 1
                break
        else:
            # 超出范围的归入最近区间
            if s < zone_bounds[0]:
                zone_counts[0] += 1
            else:
                zone_counts[3] += 1

    total = sum(zone_counts)
    if total == 0:
        return [0.0, 0.0, 0.0, 0.0]

    return [c / total for c in zone_counts]
