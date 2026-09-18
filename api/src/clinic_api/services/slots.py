"""Pure slot arithmetic shared by availability listing and booking validation."""

from collections.abc import Iterable, Iterator
from datetime import date, datetime, time, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo


class ScheduleBlock(Protocol):
    @property
    def weekday(self) -> int: ...
    @property
    def start_time(self) -> time: ...
    @property
    def end_time(self) -> time: ...
    @property
    def slot_minutes(self) -> int: ...


def iter_dates(date_from: date, date_to: date) -> Iterator[date]:
    current = date_from
    while current <= date_to:
        yield current
        current += timedelta(days=1)


def generate_slots(blocks: Iterable[ScheduleBlock], day: date, tz: ZoneInfo) -> list[datetime]:
    """Start times (aware, clinic local) of every slot that fully fits a block on `day`."""
    starts: list[datetime] = []
    for block in blocks:
        if block.weekday != day.weekday():
            continue
        step = timedelta(minutes=block.slot_minutes)
        current = datetime.combine(day, block.start_time, tzinfo=tz)
        block_end = datetime.combine(day, block.end_time, tzinfo=tz)
        while current + step <= block_end:
            starts.append(current)
            current += step
    return sorted(starts)


def find_slot(
    blocks: Iterable[ScheduleBlock], starts_at: datetime, tz: ZoneInfo
) -> tuple[datetime, datetime] | None:
    """Return `(start, end)` in clinic local time if `starts_at` is exactly a slot start."""
    local_start = starts_at.astimezone(tz)
    for block in blocks:
        if local_start in generate_slots([block], local_start.date(), tz):
            return local_start, local_start + timedelta(minutes=block.slot_minutes)
    return None
