"""Tape recorder: WS `trades` for every perp coin -> hourly Parquet (plan §4.3).

Each trade carries users=[buyer, seller]; `side` is the taker (aggressor) side, so
taker = buyer if side == "B" else seller. Writes are atomic (tmp + rename), deduped on
(coin, tid), and outages are recorded in `tape_gaps` and gap-filled from recentTrades.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import polars as pl

log = logging.getLogger(__name__)

TAPE_SCHEMA = {
    "time": pl.Int64, "coin": pl.Utf8, "px": pl.Float64, "sz": pl.Float64, "side": pl.Utf8,
    "tid": pl.Int64, "hash": pl.Utf8, "buyer": pl.Utf8, "seller": pl.Utf8,
}
SUBS_PER_MSG_DELAY = 0.02


def parse_trade(t: dict[str, Any]) -> dict[str, Any] | None:
    users = t.get("users") or []
    if len(users) != 2:
        return None
    return {
        "time": int(t["time"]), "coin": t["coin"], "px": float(t["px"]), "sz": float(t["sz"]),
        "side": t["side"], "tid": int(t["tid"]), "hash": t.get("hash", ""),
        "buyer": users[0].lower(), "seller": users[1].lower(),
    }


class TradeBuffer:
    """In-memory dedupe + buffer; flushes to hour-partitioned Parquet files."""

    def __init__(self, root: Path, dedupe_size: int = 2_000_000) -> None:
        self.root = Path(root)
        self.rows: list[dict[str, Any]] = []
        self._seen: OrderedDict[tuple[str, int], None] = OrderedDict()
        self._dedupe_size = dedupe_size
        self._seq = 0

    def preload(self, days: int = 2) -> int:
        """Seed the dedupe set from recent files so restarts/snapshots don't duplicate."""
        n = 0
        for d in sorted(self.root.glob("date=*"))[-days:]:
            files = [str(f) for f in d.rglob("*.parquet")]
            if files:
                for coin, tid in pl.read_parquet(files, columns=["coin", "tid"]).iter_rows():
                    self._seen[(coin, tid)] = None
                    n += 1
        return n

    def add(self, row: dict[str, Any]) -> bool:
        key = (row["coin"], row["tid"])
        if key in self._seen:
            return False
        self._seen[key] = None
        if len(self._seen) > self._dedupe_size:
            self._seen.popitem(last=False)
        self.rows.append(row)
        return True

    def flush(self) -> int:
        if not self.rows:
            return 0
        rows, self.rows = self.rows, []
        df = pl.DataFrame(rows, schema=TAPE_SCHEMA)
        df = df.with_columns(pl.from_epoch("time", time_unit="ms").alias("_dt"))
        df = df.with_columns(
            pl.col("_dt").dt.strftime("%Y-%m-%d").alias("_date"), pl.col("_dt").dt.hour().alias("_hour")
        )
        written = 0
        for (date, hour), part in df.group_by(["_date", "_hour"]):
            d = self.root / f"date={date}" / f"hour={hour:02d}"
            d.mkdir(parents=True, exist_ok=True)
            self._seq += 1
            name = f"part-{int(time.time() * 1000)}-{self._seq}.parquet"
            tmp = d / (name + ".tmp")
            part.drop(["_dt", "_date", "_hour"]).write_parquet(tmp, compression="zstd")
            tmp.rename(d / name)
            written += part.height
        return written


async def fetch_coins(info_post: Callable[[dict[str, Any]], Awaitable[Any]]) -> list[str]:
    """All perp coins incl. HIP-3 dexes (`dex:COIN`)."""
    coins: list[str] = []
    meta = await info_post({"type": "meta"})
    coins += [u["name"] for u in meta["universe"] if not u.get("isDelisted")]
    dexs = await info_post({"type": "perpDexs"})
    for dex in dexs or []:
        if not dex:  # first entry is null for the default dex
            continue
        m = await info_post({"type": "meta", "dex": dex["name"]})
        coins += [u["name"] for u in m["universe"] if not u.get("isDelisted")]
    return sorted(set(coins))


class TapeRecorder:
    def __init__(
        self,
        buffer: TradeBuffer,
        state: sqlite3.Connection,
        coins_fn: Callable[[], Awaitable[list[str]]],
        connect: Callable[[], Any],
        gapfill_fn: Callable[[str], Awaitable[list[dict[str, Any]]]] | None = None,
        ping_s: int = 30,
        flush_s: int = 30,
        coin_resync_s: int = 3600,
    ) -> None:
        self.buffer, self.state, self.coins_fn = buffer, state, coins_fn
        self.connect, self.gapfill_fn = connect, gapfill_fn
        self.ping_s, self.flush_s, self.coin_resync_s = ping_s, flush_s, coin_resync_s
        self.last_msg_ms = 0
        self.coins: list[str] = []
        self.stop = asyncio.Event()
        self.heartbeat_path: Path | None = None

    def record_gap(self, start_ms: int, end_ms: int, reason: str) -> None:
        self.state.execute(
            "INSERT INTO tape_gaps(coin, start_ts, end_ts, reason) VALUES ('*',?,?,?)",
            (start_ms, end_ms, reason),
        )

    def handle_message(self, raw: str) -> int:
        msg = json.loads(raw)
        if msg.get("channel") != "trades":
            return 0
        n = 0
        for t in msg["data"]:
            row = parse_trade(t)
            if row and self.buffer.add(row):
                n += 1
        self.last_msg_ms = int(time.time() * 1000)
        return n

    async def _subscribe(self, ws: Any, coins: list[str]) -> None:
        for c in coins:
            await ws.send(json.dumps(
                {"method": "subscribe", "subscription": {"type": "trades", "coin": c}}))
            await asyncio.sleep(SUBS_PER_MSG_DELAY)

    async def _session(self) -> None:
        self.coins = await self.coins_fn()
        self.buffer.preload()
        disconnected_at = self.last_msg_ms
        async with self.connect() as ws:
            await self._subscribe(ws, self.coins)
            # keep-alive and live handling start first; gap fill must never starve the socket
            tasks = [asyncio.create_task(self._ping(ws)), asyncio.create_task(self._flusher()),
                     asyncio.create_task(self._resync(ws)), asyncio.create_task(self._beat())]
            if disconnected_at:
                self.record_gap(disconnected_at, int(time.time() * 1000), "reconnect")
                if self.gapfill_fn:
                    tasks.append(asyncio.create_task(self._gapfill()))
            try:
                async for raw in ws:
                    self.handle_message(raw)
                    if self.stop.is_set():
                        break
            finally:
                for t in tasks:
                    t.cancel()
                self.buffer.flush()

    async def _gapfill(self) -> None:
        for c in self.coins:
            try:
                for t in await self.gapfill_fn(c):
                    row = parse_trade(t)
                    if row:
                        self.buffer.add(row)
            except Exception as e:
                log.warning("gap fill %s failed: %s", c, type(e).__name__)

    async def _ping(self, ws: Any) -> None:
        while True:
            await asyncio.sleep(self.ping_s)
            await ws.send(json.dumps({"method": "ping"}))

    async def _flusher(self) -> None:
        while True:
            await asyncio.sleep(self.flush_s)
            n = self.buffer.flush()
            log.info("flushed %d trades", n)

    async def _beat(self) -> None:
        """Heartbeat = last time a WS message arrived (so a silent socket goes stale)."""
        while True:
            await asyncio.sleep(15)
            if self.heartbeat_path and time.time() * 1000 - self.last_msg_ms < 60_000:
                self.heartbeat_path.write_text(str(int(self.last_msg_ms / 1000)))

    async def _resync(self, ws: Any) -> None:
        while True:
            await asyncio.sleep(self.coin_resync_s)
            new = await self.coins_fn()
            added = sorted(set(new) - set(self.coins))
            if added:
                log.info("new coins: %s", added)
                await self._subscribe(ws, added)
            self.coins = new

    async def run(self) -> None:
        backoff = 1.0
        while not self.stop.is_set():
            try:
                await self._session()
                backoff = 1.0
            except Exception as e:
                log.warning("ws session failed: %s; retry in %.0fs", e, backoff)
            await asyncio.sleep(backoff)
            backoff = min(60.0, backoff * 2)


def compact_day(tape_root: Path, out_root: Path, date: str) -> Path | None:
    """Aggregate one day of tape into per-address stats (plan §4.3, `addr_day_stats`)."""
    src = tape_root / f"date={date}"
    if not src.exists():
        return None
    glob = str(src / "hour=*" / "*.parquet")
    out = out_root / f"date={date}.parquet"
    out_root.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(":memory:")
    con.execute(f"""
        CREATE VIEW t AS SELECT DISTINCT * FROM read_parquet('{glob}');
        CREATE VIEW legs AS
          SELECT buyer AS address, seller AS cp, time, coin, px*sz AS notional, 'B' AS dir,
                 (side = 'B') AS is_taker FROM t
          UNION ALL
          SELECT seller, buyer, time, coin, px*sz, 'S', (side = 'A') FROM t;
        CREATE VIEW gaps AS
          SELECT address, (time - lag(time) OVER (PARTITION BY address ORDER BY time)) / 1000.0 AS g
          FROM legs;
        CREATE VIEW cps AS
          SELECT address, cp, sum(notional) AS n,
                 row_number() OVER (PARTITION BY address ORDER BY sum(notional) DESC) AS rk
          FROM legs GROUP BY address, cp;
        COPY (
          SELECT l.address, DATE '{date}' AS date, count(*) AS trades, sum(notional) AS notional,
                 count(*) FILTER (WHERE dir='B') AS buys, count(*) FILTER (WHERE dir='S') AS sells,
                 count(DISTINCT coin) AS coins, 1 - avg(is_taker::INT) AS maker_share_proxy,
                 min(time) AS first_ts, max(time) AS last_ts,
                 (SELECT median(g) FROM gaps WHERE gaps.address = l.address) AS median_gap_s,
                 (SELECT list(cp ORDER BY rk) FROM cps WHERE cps.address = l.address AND rk <= 5)
                   AS top_counterparties
          FROM legs l GROUP BY l.address
        ) TO '{out}' (FORMAT PARQUET, COMPRESSION ZSTD);
    """)
    return out


def prune_raw(tape_root: Path, keep_days: int, today: datetime | None = None) -> list[str]:
    today = today or datetime.now(UTC)
    removed = []
    for d in sorted(tape_root.glob("date=*")):
        day = datetime.strptime(d.name[5:], "%Y-%m-%d").replace(tzinfo=UTC)
        if (today - day).days > keep_days:
            for f in d.rglob("*"):
                if f.is_file():
                    f.unlink()
            for sub in sorted(d.rglob("*"), reverse=True):
                sub.rmdir()
            d.rmdir()
            removed.append(d.name)
    return removed


async def nightly_maintenance(root: Path, retain_days: int, run_at_utc: tuple[int, int] = (0, 30)) -> None:
    """Daily at 00:30 UTC: compact yesterday's tape, then prune raw beyond retention."""
    from datetime import timedelta

    while True:
        now = datetime.now(UTC)
        nxt = now.replace(hour=run_at_utc[0], minute=run_at_utc[1], second=0, microsecond=0)
        if nxt <= now:
            nxt += timedelta(days=1)
        await asyncio.sleep((nxt - now).total_seconds())
        day = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")
        try:
            await asyncio.to_thread(compact_day, root / "tape", root / "addr_day_stats", day)
            prune_raw(root / "tape", retain_days)
            log.info("compacted %s", day)
        except Exception:
            log.exception("nightly maintenance failed")
