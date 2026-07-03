"""核心模块单元测试."""

import pytest

from caipiao.core.ball import Ball, BallColor
from caipiao.core.engine import GenerationEngine
from caipiao.core.prize import calculate_prize, fc3d_bet_type
from caipiao.core.strategies import (
    ExcludeIncludeStrategy,
    HotColdStrategy,
    OddEvenStrategy,
    RandomStrategy,
)
from caipiao.core.ticket import Ticket


def test_ball_validation():
    Ball.red(1)
    Ball.red(33)
    Ball.blue(1)
    Ball.blue(16)

    with pytest.raises(ValueError):
        Ball.red(0)
    with pytest.raises(ValueError):
        Ball.red(34)
    with pytest.raises(ValueError):
        Ball.blue(17)


def test_ticket_validation():
    Ticket([1, 2, 3, 4, 5, 6], 7)

    with pytest.raises(ValueError):
        Ticket([1, 2, 3, 4, 5], 7)
    with pytest.raises(ValueError):
        Ticket([1, 2, 3, 4, 5, 5], 7)
    with pytest.raises(ValueError):
        Ticket([1, 2, 3, 4, 5, 6], 17)


def test_random_strategy():
    strategy = RandomStrategy()
    tickets = strategy.generate(count=10)
    assert len(tickets) == 10
    for t in tickets:
        assert len(t.red_balls) == 6
        assert 1 <= t.blue_ball.number <= 16


def test_odd_even_strategy():
    strategy = OddEvenStrategy()
    tickets = strategy.generate(count=5, options={"odd_count": 4})
    for t in tickets:
        odd_count = sum(1 for b in t.red_balls if b.number % 2 == 1)
        assert odd_count == 4


def test_exclude_include_strategy():
    strategy = ExcludeIncludeStrategy()
    tickets = strategy.generate(
        count=3,
        options={"include_red": [1, 2], "exclude_red": [33], "exclude_blue": [16]},
    )
    for t in tickets:
        reds = {b.number for b in t.red_balls}
        assert 1 in reds
        assert 2 in reds
        assert 33 not in reds
        assert t.blue_ball.number != 16


def test_engine():
    engine = GenerationEngine()
    engine.register(RandomStrategy())
    tickets = engine.generate("random", count=2)
    assert len(tickets) == 2


def test_hot_cold_strategy_with_history():
    strategy = HotColdStrategy()
    history = [Ticket([1, 2, 3, 4, 5, 6], 1) for _ in range(5)]
    tickets = strategy.generate(count=2, options={"mode": "hot", "history": history})
    assert len(tickets) == 2


def test_hot_cold_strategy_with_draw_records():
    """应用实际传入的是官方开奖记录 DrawRecord（红球为 int），需正确统计。"""
    from datetime import datetime

    from caipiao.data.models import DrawRecord

    strategy = HotColdStrategy()
    history = [
        DrawRecord(
            issue=f"2024{i:03d}",
            draw_date=datetime(2024, 1, 1),
            red_balls=[1, 2, 3, 4, 5, 6],
            blue_ball=1,
        )
        for i in range(1, 6)
    ]
    tickets = strategy.generate(count=2, options={"mode": "hot", "history": history})
    assert len(tickets) == 2
    for t in tickets:
        assert len(t.red_balls) == 6
        assert 1 <= t.blue_ball.number <= 16


# --------------------------------------------------------------------------- #
# 福彩 3D 奖金判定回归测试
# --------------------------------------------------------------------------- #
def test_fc3d_prize_straight():
    actual = {"pos": [1, 2, 3]}
    # 完全相同：直选
    assert calculate_prize("3d", {"pos": 3}, {"pos": [1, 2, 3]}, actual) == ("直选", 1040)


def test_fc3d_prize_group6():
    actual = {"pos": [3, 7, 5]}
    # 排列不同：组选6
    assert calculate_prize("3d", {"pos": 0}, {"pos": [7, 5, 3]}, actual) == ("组选6", 173)


def test_fc3d_prize_group3():
    actual = {"pos": [1, 6, 1]}
    # 排列不同：组选3
    assert calculate_prize("3d", {"pos": 1}, {"pos": [6, 1, 1]}, actual) == ("组选3", 346)


def test_fc3d_prize_no_win():
    actual = {"pos": [1, 2, 3]}
    # 号码不完全相同：未中奖
    assert calculate_prize("3d", {"pos": 2}, {"pos": [1, 2, 4]}, actual) == ("未中奖", 0)
    assert calculate_prize("3d", {"pos": 2}, {"pos": [3, 4, 5]}, actual) == ("未中奖", 0)


def test_fc3d_prize_requires_actual():
    # 不传入真实开奖时，必须视为未中奖，避免 100% 误中奖
    assert calculate_prize("3d", {"pos": 3}, {"pos": [1, 2, 3]}) == ("未中奖", 0)


# --------------------------------------------------------------------------- #
# 体育彩票奖金计算测试
# --------------------------------------------------------------------------- #
def test_dlt_prize():
    assert calculate_prize("dlt", {"front": 5, "back": 2}, {}) == ("一等奖", None)
    assert calculate_prize("dlt", {"front": 5, "back": 1}, {}) == ("二等奖", None)
    assert calculate_prize("dlt", {"front": 5, "back": 0}, {}) == ("三等奖", 10000)
    assert calculate_prize("dlt", {"front": 3, "back": 1}, {}) == ("八等奖", 15)
    assert calculate_prize("dlt", {"front": 0, "back": 2}, {}) == ("九等奖", 5)
    assert calculate_prize("dlt", {"front": 1, "back": 0}, {}) == ("未中奖", 0)


def test_pl3_prize():
    actual = {"pos": [1, 2, 3]}
    assert calculate_prize("pl3", {"pos": 3}, {"pos": [1, 2, 3]}, actual) == ("直选", 1040)
    assert calculate_prize("pl3", {"pos": 0}, {"pos": [3, 2, 1]}, actual) == ("组选6", 173)
    actual_group3 = {"pos": [1, 1, 2]}
    assert calculate_prize("pl3", {"pos": 0}, {"pos": [2, 1, 1]}, actual_group3) == ("组选3", 346)
    assert calculate_prize("pl3", {"pos": 2}, {"pos": [1, 2, 4]}, actual) == ("未中奖", 0)


def test_pl5_prize():
    assert calculate_prize("pl5", {"pos": 5}, {"pos": [1, 2, 3, 4, 5]}) == ("直选", 100000)
    assert calculate_prize("pl5", {"pos": 4}, {"pos": [1, 2, 3, 4, 5]}) == ("未中奖", 0)


def test_qxc_prize():
    actual = {"pos": [1, 2, 3, 4, 5, 6, 7]}
    assert calculate_prize("qxc", {"pos": 7}, {"pos": [1, 2, 3, 4, 5, 6, 7]}, actual) == ("一等奖", None)
    assert calculate_prize("qxc", {"pos": 5}, {"pos": [9, 9, 3, 4, 5, 6, 7]}, actual) == ("三等奖", 3000)
    assert calculate_prize("qxc", {"pos": 2}, {"pos": [9, 9, 9, 9, 9, 6, 7]}, actual) == ("六等奖", 5)
    assert calculate_prize("qxc", {"pos": 1}, {"pos": [9, 9, 9, 9, 9, 9, 7]}, actual) == ("未中奖", 0)


def test_gd36x7_prize():
    # 广东36选7 已临时从注册表中移除，但奖金函数保留；
    # 这里仅验证函数本身逻辑，不验证彩种是否注册。
    assert calculate_prize("gd36x7", {"basic": 7, "special": 0}, {}) == ("一等奖", None)
    assert calculate_prize("gd36x7", {"basic": 6, "special": 1}, {}) == ("二等奖", None)
    assert calculate_prize("gd36x7", {"basic": 5, "special": 1}, {}) == ("四等奖", 200)
    assert calculate_prize("gd36x7", {"basic": 4, "special": 0}, {}) == ("七等奖", 5)
    assert calculate_prize("gd36x7", {"basic": 3, "special": 1}, {}) == ("未中奖", 0)


# --------------------------------------------------------------------------- #
# 福彩 3D 投注方式识别测试
# --------------------------------------------------------------------------- #
def test_fc3d_bet_type():
    assert fc3d_bet_type([3, 7, 5]) == "组选6"
    assert fc3d_bet_type([1, 6, 1]) == "组选3"
    assert fc3d_bet_type([7, 7, 7]) == "豹子号（直选）"
    assert fc3d_bet_type([1, 2]) == "未知"


# --------------------------------------------------------------------------- #
# 概率折线图 HTML 生成测试
# --------------------------------------------------------------------------- #
def test_group_probability_charts_html_layout():
    """PDF/打印用概率图应使用横向网格布局，且图片独占一行。"""
    from caipiao.ui.chart_utils import build_group_probability_charts_html

    group_probs = [
        ("第1位概率", [0.1] * 10, "#F57C00", 1, "数字 (0-9)"),
        ("第2位概率", [0.1] * 10, "#F57C00", 1, "数字 (0-9)"),
        ("第3位概率", [0.1] * 10, "#F57C00", 1, "数字 (0-9)"),
    ]
    html = build_group_probability_charts_html(group_probs, lookback=100, diversity_boost=3, model_name="LightGBM")
    assert "data:image/png;base64," in html
    assert 'style="width:100%; height:auto; display:block;' in html
    assert "LightGBM 预测概率折线图" in html
