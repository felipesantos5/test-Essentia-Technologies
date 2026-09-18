import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Hashable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class _Entry[V]:
    value: V
    expires_at: float


class TTLCache[K: Hashable, V]:
    """Thread-safe in-process cache with per-entry TTL, LRU eviction and invalidation.

    Values are shared by concurrent requests, so they must be immutable. A TTL of zero or less
    disables caching.
    """

    def __init__(
        self,
        *,
        ttl_seconds: float,
        max_entries: int = 256,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._entries: OrderedDict[K, _Entry[V]] = OrderedDict()
        self._generation = 0
        self._lock = threading.Lock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def get_or_compute(self, key: K, compute: Callable[[], V]) -> V:
        """Return the fresh value cached for `key`, or run `compute` (unlocked) and cache it."""
        if self._ttl <= 0:
            return compute()

        with self._lock:
            entry = self._entries.get(key)
            if entry is not None:
                if entry.expires_at > self._clock():
                    self._entries.move_to_end(key)
                    return entry.value
                del self._entries[key]
            generation = self._generation

        value = compute()

        with self._lock:
            # `clear()` ran while computing, so `value` may predate that write: serve, don't keep.
            if generation == self._generation:
                self._entries[key] = _Entry(value, self._clock() + self._ttl)
                self._entries.move_to_end(key)
                if len(self._entries) > self._max_entries:
                    self._entries.popitem(last=False)
        return value

    def clear(self) -> None:
        """Drop every entry, including values still being computed by in-flight requests."""
        with self._lock:
            self._entries.clear()
            self._generation += 1
