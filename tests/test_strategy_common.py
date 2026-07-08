from datetime import datetime, timedelta

import pytest

from caipiao.core.profile import FC3D, SSQ
from caipiao.core.strategies.common.records import records_from_options
from caipiao.core.strategies.common.rng import make_rng
from caipiao.core.strategies.common.validators import validate_odd_count
from caipiao.core.ticket import Ticket
from caipiao.data.models import DrawRecord


def make_ticket_3d(numbers):
    return Ticket(profile=FC3D, groups={"pos": numbers})


def test_records_from_options_accepts_draw_records():
    records = [
        DrawRecord("2024001", datetime(2024, 1, 1), profile="3d", groups={"pos": [1, 2, 3]}),
    ]
    assert records_from_options({"history": records}) == records


def test_records_from_options_accepts_tickets():
    tickets = [make_ticket_3d([1, 2, 3])]
    result = records_from_options({"history": tickets})
    assert len(result) == 1
    assert result[0].profile.key == "3d"
    assert result[0].groups["pos"] == [1, 2, 3]


def test_records_from_options_empty():
    assert records_from_options({}) == []
    assert records_from_options({"history": None}) == []


def test_make_rng_with_seed():
    rng1 = make_rng({"seed": 42})
    rng2 = make_rng({"seed": 42})
    assert rng1.randint(0, 100) == rng2.randint(0, 100)


def test_make_rng_without_seed():
    rng = make_rng({})
    assert isinstance(rng.randint(0, 100), int)


def test_validate_odd_count_valid():
    validate_odd_count({"odd_count": 3}, 6)


def test_validate_odd_count_invalid():
    with pytest.raises(ValueError):
        validate_odd_count({"odd_count": 7}, 6)
