"""回测胜率统计测试."""

from datetime import datetime

import pytest

from caipiao.core.backtest_stats import (
    BacktestResult,
    BacktestStats,
    analyze_ticket_numbers,
    find_hot_cold_numbers,
    format_backtest_report,
    run_backtest,
)
from caipiao.core.ticket import Ticket
from caipiao.data.models import DrawRecord


class TestBacktestStats:
    """BacktestStats 数据类测试."""

    def test_initial_state(self):
        stats = BacktestStats()
        assert stats.total_periods == 0
        assert stats.total_tickets == 0
        assert stats.total_investment == 0
        assert stats.total_return == 0

    def test_win_rate(self):
        stats = BacktestStats()
        stats.total_tickets = 10
        stats.results = [
            BacktestResult(
                issue="2024001",
                draw_date=datetime(2024, 1, 1),
                ticket=Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7),
                prize_level="六等奖",
                prize_amount=5,
            )
            for _ in range(3)
        ]
        stats.results.extend(
            [
                BacktestResult(
                    issue="2024001",
                    draw_date=datetime(2024, 1, 1),
                    ticket=Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7),
                    prize_level="未中奖",
                    prize_amount=0,
                )
                for _ in range(7)
            ]
        )
        assert stats.win_rate == 0.3

    def test_roi(self):
        stats = BacktestStats()
        stats.total_investment = 100
        stats.total_return = 150
        assert stats.roi == 0.5

    def test_summary(self):
        stats = BacktestStats()
        stats.total_periods = 5
        stats.total_tickets = 10
        stats.total_investment = 20
        stats.total_return = 25
        stats.prize_counts = {"六等奖": 2, "未中奖": 8}
        stats.prize_amounts = {"六等奖": 10}

        summary = stats.summary()
        assert summary["总期数"] == 5
        assert summary["总注数"] == 10
        assert summary["总投入"] == 20
        assert summary["总回报"] == 25
        assert "收益率" in summary
        assert "中奖率" in summary


class TestAnalyzeTicketNumbers:
    """号码分析测试."""

    def test_empty_tickets(self):
        result = analyze_ticket_numbers([])
        assert result == {}

    def test_single_ticket(self):
        ticket = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        result = analyze_ticket_numbers([ticket])
        assert result[1] == 1
        assert result[7] == 1

    def test_multiple_tickets(self):
        tickets = [
            Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7),
            Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=8),
            Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=9),
        ]
        result = analyze_ticket_numbers(tickets)
        assert result[1] == 3
        assert result[7] == 1


class TestFindHotColdNumbers:
    """热冷号分析测试."""

    def test_empty_tickets(self):
        hot, cold = find_hot_cold_numbers([])
        assert hot == []
        assert cold == []

    def test_hot_cold(self):
        tickets = [
            Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7),
            Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7),
            Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7),
            Ticket(red_balls=[7, 8, 9, 10, 11, 12], blue_ball=1),
        ]
        hot, cold = find_hot_cold_numbers(tickets, recent_count=4)
        assert 1 in hot
        assert len(hot) > 0


class TestRunBacktest:
    """回测运行测试."""

    def test_empty_backtest(self):
        stats = run_backtest({}, {}, "ssq")
        assert stats.total_periods == 0
        assert stats.total_tickets == 0

    def test_backtest_with_data(self):
        tickets = [
            Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7),
        ]
        draw_record = DrawRecord(
            issue="2024001",
            draw_date=datetime(2024, 1, 1),
            red_balls=[1, 2, 3, 4, 5, 6],
            blue_ball=7,
        )
        tickets_by_period = {"2024001": tickets}
        draw_records = {"2024001": draw_record}

        stats = run_backtest(tickets_by_period, draw_records, "ssq")
        assert stats.total_periods == 1
        assert stats.total_tickets == 1
        assert stats.total_investment == 2
        # 一等奖是浮动奖金，prize_amount 为 None
        assert "一等奖" in stats.prize_counts


class TestFormatBacktestReport:
    """报告格式化测试."""

    def test_empty_report(self):
        stats = BacktestStats()
        report = format_backtest_report(stats)
        assert "回测统计报告" in report
        assert "总期数: 0" in report

    def test_report_with_data(self):
        stats = BacktestStats()
        stats.total_periods = 5
        stats.total_tickets = 10
        stats.total_investment = 20
        stats.total_return = 25
        stats.prize_counts = {"六等奖": 2, "未中奖": 8}
        stats.prize_amounts = {"六等奖": 10}
        stats.hot_numbers = [1, 2, 3]
        stats.cold_numbers = [30, 31, 32]

        report = format_backtest_report(stats)
        assert "总期数: 5" in report
        assert "总注数: 10" in report
        assert "六等奖" in report
        assert "热号" in report
        assert "冷号" in report
