from collections.abc import Callable

import pytest

from clinic_api.cache import TTLCache


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def counting(prefix: str = "v") -> tuple[Callable[[], str], list[str]]:
    """A compute function returning `v1`, `v2`, ... so tests can tell fresh values from cached."""
    produced: list[str] = []

    def compute() -> str:
        produced.append(f"{prefix}{len(produced) + 1}")
        return produced[-1]

    return compute, produced


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def cache(clock: FakeClock) -> TTLCache[str, str]:
    return TTLCache(ttl_seconds=60, clock=clock)


def test_serves_cached_value_until_the_ttl_expires(
    cache: TTLCache[str, str], clock: FakeClock
) -> None:
    compute, produced = counting()

    assert cache.get_or_compute("k", compute) == "v1"
    clock.now = 59.9
    assert cache.get_or_compute("k", compute) == "v1"
    clock.now = 60.0
    assert cache.get_or_compute("k", compute) == "v2"
    assert produced == ["v1", "v2"]


def test_keys_are_cached_independently(cache: TTLCache[str, str]) -> None:
    compute_a, _ = counting("a")
    compute_b, _ = counting("b")

    assert cache.get_or_compute("a", compute_a) == "a1"
    assert cache.get_or_compute("b", compute_b) == "b1"
    assert cache.get_or_compute("a", compute_a) == "a1"
    assert len(cache) == 2


def test_clear_drops_every_entry(cache: TTLCache[str, str]) -> None:
    compute, _ = counting()
    cache.get_or_compute("k", compute)

    cache.clear()

    assert len(cache) == 0
    assert cache.get_or_compute("k", compute) == "v2"


def test_value_computed_across_a_clear_is_returned_but_not_cached(
    cache: TTLCache[str, str],
) -> None:
    def compute_racing_a_write() -> str:
        # A booking commits and invalidates while this request is still reading the database.
        cache.clear()
        return "stale"

    assert cache.get_or_compute("k", compute_racing_a_write) == "stale"
    assert len(cache) == 0
    compute, _ = counting()
    assert cache.get_or_compute("k", compute) == "v1"


def test_errors_are_not_cached(cache: TTLCache[str, str]) -> None:
    def failing() -> str:
        raise LookupError("doctor not found")

    with pytest.raises(LookupError):
        cache.get_or_compute("k", failing)

    assert len(cache) == 0


def test_evicts_the_least_recently_used_entry(clock: FakeClock) -> None:
    cache: TTLCache[str, str] = TTLCache(ttl_seconds=60, max_entries=2, clock=clock)
    compute, _ = counting()
    cache.get_or_compute("a", compute)
    cache.get_or_compute("b", compute)
    cache.get_or_compute("a", compute)  # hit: "a" becomes the most recently used

    cache.get_or_compute("c", compute)

    assert len(cache) == 2
    assert cache.get_or_compute("a", compute) == "v1"
    assert cache.get_or_compute("b", compute) == "v4"


def test_zero_ttl_disables_caching(clock: FakeClock) -> None:
    cache: TTLCache[str, str] = TTLCache(ttl_seconds=0, clock=clock)
    compute, produced = counting()

    cache.get_or_compute("k", compute)
    cache.get_or_compute("k", compute)

    assert produced == ["v1", "v2"]
    assert len(cache) == 0


def test_rejects_an_empty_capacity() -> None:
    with pytest.raises(ValueError, match="max_entries"):
        TTLCache[str, str](ttl_seconds=60, max_entries=0)
