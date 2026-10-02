"""Hourly mark store from candleSnapshot closes (5,000-candle cap ~ 208 days per call)."""

from __future__ import annotations

import bisect
from collections.abc import Callable
from pathlib import Path
from typing import Any

import polars as pl

HOUR_MS = 3_600_000
MAX_CANDLES = 5000


def marks_path(root: Path, coin: str) -> Path:
    return Path(root) / "marks" / f"{coin.replace(':', '_').replace('/', '_')}.parquet"


async def fetch_marks(info: Any, root: Path, coin: str, start_ms: int, end_ms: int,
                      lane: str = "deep_vet") -> pl.DataFrame:
    """Fetch 1h closes covering [start, end], merging into the on-disk store."""
    p = marks_path(root, coin)
    have = pl.read_parquet(p) if p.exists() else pl.DataFrame(schema={"time": pl.Int64, "close": pl.Float64})
    start_ms = max(start_ms, end_ms - MAX_CANDLES * HOUR_MS)
    if not have.is_empty() and have["time"].min() <= start_ms + HOUR_MS and have["time"].max() >= end_ms - 2 * HOUR_MS:
        return have
    rows = await info.post({"type": "candleSnapshot", "req": {
        "coin": coin, "interval": "1h", "startTime": start_ms, "endTime": end_ms}}, lane=lane)
    new = pl.DataFrame({"time": [int(r["t"]) for r in rows], "close": [float(r["c"]) for r in rows]},
                       schema={"time": pl.Int64, "close": pl.Float64})
    out = pl.concat([have, new]).unique("time").sort("time")
    p.parent.mkdir(parents=True, exist_ok=True)
    out.write_parquet(p)
    return out


def mark_provider(root: Path) -> Callable[[str, int], float | None]:
    cache: dict[str, tuple[list[int], list[float]]] = {}

    def mark(coin: str, t: int) -> float | None:
        if coin not in cache:
            p = marks_path(root, coin)
            if not p.exists():
                cache[coin] = ([], [])
            else:
                df = pl.read_parquet(p)
                cache[coin] = (df["time"].to_list(), df["close"].to_list())
        ts, cl = cache[coin]
        if not ts:
            return None
        i = bisect.bisect_right(ts, t) - 1
        return cl[i] if i >= 0 and t - ts[i] <= 2 * HOUR_MS else None

    return mark


# ---- daily marks: one candleSnapshot call per coin covers the whole history (5,000 daily candles) ----
DAY_MS = 86_400_000


def daily_path(root: Path, coin: str) -> Path:
    return Path(root) / "marks_daily" / f"{coin.replace(':', '_').replace('/', '_')}.parquet"


async def fetch_daily_marks(info: Any, root: Path, coin: str, now_ms: int, lane: str = "backfill",
                            max_age_ms: int = 2 * DAY_MS) -> int:
    """Store 1d closes for `coin` (full history). Skips if the store already reaches within max_age of now.
    Returns the number of candles stored (0 for delisted/unknown coins: callers fall back to fill prices)."""
    p = daily_path(root, coin)
    if p.exists():
        have = pl.read_parquet(p)
        if not have.is_empty() and int(have["time"].max()) >= now_ms - max_age_ms - DAY_MS:
            return have.height
    rows = await info.post({"type": "candleSnapshot", "req": {
        "coin": coin, "interval": "1d", "startTime": max(0, now_ms - MAX_CANDLES * DAY_MS), "endTime": now_ms}},
        lane=lane)
    df = pl.DataFrame({"time": [int(r["t"]) for r in rows or []], "close": [float(r["c"]) for r in rows or []]},
                      schema={"time": pl.Int64, "close": pl.Float64}).unique("time").sort("time")
    p.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(p)
    return df.height


def daily_mark_provider(root: Path) -> Callable[[str, int], float | None]:
    """mark(coin, t_ms): close of the daily candle containing t (None if no candle covers t)."""
    cache: dict[str, tuple[list[int], list[float]]] = {}

    def mark(coin: str, t: int) -> float | None:
        if coin not in cache:
            p = daily_path(root, coin)
            if p.exists():
                df = pl.read_parquet(p)
                cache[coin] = (df["time"].to_list(), df["close"].to_list())
            else:
                cache[coin] = ([], [])
        ts, cl = cache[coin]
        if not ts:
            return None
        i = bisect.bisect_right(ts, t) - 1
        return cl[i] if i >= 0 and t - ts[i] < DAY_MS else None

    return mark
