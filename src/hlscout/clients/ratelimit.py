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


class SharedRateLimiter:
    """Same interface as RateLimiter, but the bucket lives in SQLite so every process
    (tape, worker, monitor, one-off jobs) draws from ONE budget. A 429 in any process
    pauses all of them. State is a single row; every update is an atomic IMMEDIATE transaction."""

    def __init__(
        self,
        path: str,
        weight_per_min: int = 1200,
        headroom: float = 0.90,
        lanes: dict[str, float] | None = None,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        import sqlite3

        self.capacity = weight_per_min * headroom
        self.rate = self.capacity / 60.0
        self._clock, self._sleep = clock, sleep
        self._con = sqlite3.connect(path, isolation_level=None, timeout=10)
        self._con.execute("PRAGMA journal_mode=WAL")
        self._con.execute("CREATE TABLE IF NOT EXISTS bucket (id INTEGER PRIMARY KEY CHECK (id=1), "
                          "level REAL, last REAL, pause_until REAL, backoff REAL)")
        self._con.execute("INSERT OR IGNORE INTO bucket VALUES (1, ?, ?, 0, 1)", (self.capacity, clock()))
        shares = lanes or {"monitor": 0.25, "deep_vet": 0.50, "light_hydrate": 0.15, "backfill": 0.10}
        self._floor: dict[str, float] = {}
        higher = 0.0
        for lane in LANE_ORDER:
            self._floor[lane] = self.capacity * higher
            higher += shares.get(lane, 0.0)
        self.pauses: list[float] = []

    def _txn(self, fn):
        self._con.execute("BEGIN IMMEDIATE")
        try:
            out = fn()
            self._con.execute("COMMIT")
            return out
        except BaseException:
            self._con.execute("ROLLBACK")
            raise

    def _read(self) -> tuple[float, float, float, float]:
        level, last, pause, backoff = self._con.execute(
            "SELECT level, last, pause_until, backoff FROM bucket WHERE id=1").fetchone()
        now = self._clock()
        return min(self.capacity, level + max(0.0, now - last) * self.rate), now, pause, backoff

    async def acquire(self, weight: float, lane: str = "deep_vet") -> None:
        floor = self._floor[lane]
        weight = min(weight, self.capacity - floor)
        while True:
            def attempt() -> float:
                level, now, pause, _ = self._read()
                if now >= pause and level - weight >= floor:
                    self._con.execute("UPDATE bucket SET level=?, last=? WHERE id=1", (level - weight, now))
                    return 0.0
                self._con.execute("UPDATE bucket SET level=?, last=? WHERE id=1", (level, now))
                return max(pause - now, (floor + weight - level) / self.rate, 0.01)

            wait = self._txn(attempt)
            if wait == 0.0:
                return
            await self._sleep(wait)

    def debit(self, extra_weight: float) -> None:
        def f() -> None:
            level, now, _, _ = self._read()
            self._con.execute("UPDATE bucket SET level=?, last=? WHERE id=1", (level - extra_weight, now))

        self._txn(f)

    def on_429(self) -> float:
        def f() -> float:
            _, now, pause, backoff = self._read()
            p = min(60.0, backoff) * (1 + random.random() * 0.25)
            self._con.execute("UPDATE bucket SET pause_until=?, backoff=? WHERE id=1",
                              (max(pause, now + p), min(60.0, backoff * 2)))
            return p

        p = self._txn(f)
        self.pauses.append(p)
        return p

    def on_success(self) -> None:
        self._txn(lambda: self._con.execute("UPDATE bucket SET backoff=1 WHERE id=1"))


def make_limiter(cfg, root) -> SharedRateLimiter:
    """The one limiter every command uses: shared across processes via data/ratelimit.sqlite."""
    from pathlib import Path

    return SharedRateLimiter(str(Path(root) / "ratelimit.sqlite"), cfg.api.weight_per_min,
                             cfg.api.headroom, cfg.api.lanes)
