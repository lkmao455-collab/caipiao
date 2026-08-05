"""持久化历史记录测试."""

from datetime import datetime, timedelta, timezone

import pytest

from caipiao.core.ticket import Ticket
from caipiao.persistence.history import HistoryManager


class TestHistoryManager:
    """HistoryManager 测试."""

    def test_initialization(self, tmp_path):
        hm = HistoryManager(tmp_path / "history.json")
        assert hm is not None
        assert len(hm.get_all()) == 0

    def test_add_ticket(self, tmp_path):
        hm = HistoryManager(tmp_path / "history.json")
        ticket = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        result = hm.add(ticket)
        assert result is True
        assert len(hm.get_all()) == 1

    def test_add_duplicate(self, tmp_path):
        hm = HistoryManager(tmp_path / "history.json")
        ticket = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        hm.add(ticket)
        result = hm.add(ticket, skip_duplicates=True)
        assert result is False
        assert len(hm.get_all()) == 1

    def test_add_many(self, tmp_path):
        hm = HistoryManager(tmp_path / "history.json")
        tickets = [
            Ticket(red_balls=[i + 1, i + 2, i + 3, i + 4, i + 5, i + 6], blue_ball=(i % 16) + 1)
            for i in range(5)
        ]
        added = hm.add_many(tickets)
        assert added == 5
        assert len(hm.get_all()) == 5

    def test_get_all(self, tmp_path):
        hm = HistoryManager(tmp_path / "history.json")
        ticket = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        hm.add(ticket)
        all_tickets = hm.get_all()
        assert len(all_tickets) == 1

    def test_get_recent(self, tmp_path):
        hm = HistoryManager(tmp_path / "history.json")
        # 使用带时区的 datetime
        now = datetime.now(timezone.utc).astimezone()
        tickets = [
            Ticket(
                red_balls=[i + 1, i + 2, i + 3, i + 4, i + 5, i + 6],
                blue_ball=(i % 16) + 1,
                generated_at=now - timedelta(days=9 - i),
            )
            for i in range(10)
        ]
        hm.add_many(tickets)
        recent = hm.get_recent(days=5)
        assert len(recent) == 5

    def test_clear(self, tmp_path):
        hm = HistoryManager(tmp_path / "history.json")
        ticket = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        hm.add(ticket)
        hm.clear()
        assert len(hm.get_all()) == 0

    def test_delete(self, tmp_path):
        hm = HistoryManager(tmp_path / "history.json")
        ticket = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        hm.add(ticket)
        result = hm.delete(ticket)
        assert result is True
        assert len(hm.get_all()) == 0

    def test_export_csv(self, tmp_path):
        hm = HistoryManager(tmp_path / "history.json")
        ticket = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        hm.add(ticket)
        csv_path = tmp_path / "export.csv"
        hm.export_csv(csv_path)
        assert csv_path.exists()

    def test_export_txt(self, tmp_path):
        hm = HistoryManager(tmp_path / "history.json")
        ticket = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        hm.add(ticket)
        txt_path = tmp_path / "export.txt"
        hm.export_txt(txt_path)
        assert txt_path.exists()

    def test_export_excel(self, tmp_path):
        pytest.importorskip("openpyxl")
        hm = HistoryManager(tmp_path / "history.json")
        ticket = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        hm.add(ticket)
        xlsx_path = tmp_path / "export.xlsx"
        hm.export_excel(xlsx_path)
        assert xlsx_path.exists()

    def test_save_and_reload(self, tmp_path):
        path = tmp_path / "history.json"
        hm1 = HistoryManager(path)
        ticket = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        hm1.add(ticket)

        hm2 = HistoryManager(path)
        assert len(hm2.get_all()) == 1
