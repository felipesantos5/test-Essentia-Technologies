from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from clinic_api.services.slots import find_slot, generate_slots, iter_dates

SAO_PAULO = ZoneInfo("America/Sao_Paulo")
WEDNESDAY = date(2026, 9, 16)


@dataclass(frozen=True)
class Block:
    weekday: int
    start_time: time
    end_time: time
    slot_minutes: int


MORNING = Block(weekday=2, start_time=time(8), end_time=time(10), slot_minutes=30)
AFTERNOON = Block(weekday=2, start_time=time(13), end_time=time(14, 10), slot_minutes=30)


def test_generate_slots_only_returns_slots_that_fit_the_block() -> None:
    slots = generate_slots([AFTERNOON, MORNING], WEDNESDAY, SAO_PAULO)

    assert [slot.strftime("%H:%M") for slot in slots] == [
        "08:00",
        "08:30",
        "09:00",
        "09:30",
        "13:00",
        "13:30",
    ]
    assert all(slot.tzinfo == SAO_PAULO for slot in slots)


def test_generate_slots_ignores_blocks_from_other_weekdays() -> None:
    thursday = date(2026, 9, 17)

    assert generate_slots([MORNING], thursday, SAO_PAULO) == []


def test_find_slot_accepts_exact_start_in_any_timezone() -> None:
    utc_start = datetime(2026, 9, 16, 11, 30, tzinfo=UTC)  # 08:30 in São Paulo

    found = find_slot([MORNING], utc_start, SAO_PAULO)

    assert found is not None
    start, end = found
    assert (start.strftime("%H:%M"), end.strftime("%H:%M")) == ("08:30", "09:00")


@pytest.mark.parametrize(
    "local_start",
    [
        datetime(2026, 9, 16, 8, 15, tzinfo=SAO_PAULO),  # misaligned with the grid
        datetime(2026, 9, 16, 10, 0, tzinfo=SAO_PAULO),  # block end, slot would overflow
        datetime(2026, 9, 17, 8, 0, tzinfo=SAO_PAULO),  # weekday without schedule
    ],
)
def test_find_slot_rejects_times_outside_the_grid(local_start: datetime) -> None:
    assert find_slot([MORNING], local_start, SAO_PAULO) is None


def test_iter_dates_is_inclusive() -> None:
    assert list(iter_dates(WEDNESDAY, date(2026, 9, 18))) == [
        date(2026, 9, 16),
        date(2026, 9, 17),
        date(2026, 9, 18),
    ]
