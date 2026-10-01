"""Weight-aware token bucket for the Hyperliquid REST budget (1,200 weight/min/IP).

Priority lanes are enforced with floors: a lane may only spend tokens while the bucket
stays above the share reserved for higher-priority lanes, so `monitor` can always draw.
Surcharges (+1 weight per 20 rows) are debited after the response and may drive the
balance negative; later requests then wait for it to refill.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable

LANE_ORDER = ["monitor", "deep_vet", "light_hydrate", "backfill"]


class RateLimiter:
    def __init__(
        self,
        weight_per_min: int = 1200,
        headroom: float = 0.90,
        lanes: dict[str, float] | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.capacity = weight_per_min * headroom
        self.rate = self.capacity / 60.0  # tokens per second
        self.level = self.capacity
        self._clock = clock
        self._sleep = sleep
        self._last = clock()
        self._pause_until = 0.0
        self._backoff = 1.0
        self._lock = asyncio.Lock()
        shares = lanes or {"monitor": 0.25, "deep_vet": 0.50, "light_hydrate": 0.15, "backfill": 0.10}
        self._floor: dict[str, float] = {}
        higher = 0.0
        for lane in LANE_ORDER:
            self._floor[lane] = self.capacity * higher
            higher += shares.get(lane, 0.0)
        self.pauses: list[float] = []  # logged 429 pauses (seconds)

    def _refill(self) -> None:
        now = self._clock()
        self.level = min(self.capacity, self.level + (now - self._last) * self.rate)
        self._last = now

    async def acquire(self, weight: float, lane: str = "deep_vet") -> None:
        floor = self._floor[lane]
        weight = min(weight, self.capacity - floor)  # a request must always be satisfiable
        while True:
            async with self._lock:
                self._refill()
                now = self._clock()
                if now >= self._pause_until and self.level - weight >= floor:
                    self.level -= weight
                    return
                wait = max(self._pause_until - now, (floor + weight - self.level) / self.rate, 0.01)
            await self._sleep(wait)

    def debit(self, extra_weight: float) -> None:
        """Charge the row surcharge after the response arrives."""
        self._refill()
        self.level -= extra_weight

    def on_429(self) -> float:
        """Global pause with exponential backoff and jitter; returns the pause length."""
        pause = min(60.0, self._backoff) * (1 + random.random() * 0.25)
        self._backoff = min(60.0, self._backoff * 2)
        self._pause_until = self._clock() + pause
        self.pauses.append(pause)
        return pause

    def on_success(self) -> None:
        self._backoff = 1.0
