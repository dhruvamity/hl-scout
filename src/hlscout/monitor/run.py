"""Watchlist monitor: poll clearinghouse states + ledger, emit events, trip re-vets (plan §9)."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from hlscout.ingest.hydrate import raw_path
from hlscout.monitor.alerts import Notifier
from hlscout.monitor.events import Envelope, Event, Snap, check_triggers, diff_state, flock

WATCH_STAGES = ("qualified", "needs_qa", "reformed")


def watchlist(con: sqlite3.Connection) -> list[str]:
    q = ",".join("?" * len(WATCH_STAGES))
    return [r[0] for r in con.execute(f"SELECT address FROM addresses WHERE stage IN ({q})", WATCH_STAGES)]


def interval_for(snap: Snap | None, base_s: int = 120, fast_s: int = 30) -> int:
    return fast_s if snap and snap.positions else base_s


def record(con: sqlite3.Connection, e: Event, source: str = "poll") -> None:
    con.execute("INSERT INTO watch_events(address, ts, event, coin, notional, source) VALUES (?,?,?,?,?,?)",
                (e.address, e.ts, e.event, e.coin, e.notional, source))


def request_revet(con: sqlite3.Connection, address: str) -> None:
    con.execute("INSERT OR IGNORE INTO queue(address, kind, lane, priority) VALUES (?, 'deep', 'deep_vet', 1000000000)",
                (address,))
    con.execute("UPDATE queue SET state='pending', attempts=0, priority=1000000000 WHERE address=? AND kind='deep'",
                (address,))
    con.execute("UPDATE addresses SET stage='revet' WHERE address=?", (address,))


async def poll_once(info: Any, con: sqlite3.Connection, notifier: Notifier, address: str,
                    prev: Snap | None, env: Envelope, dexes: list[str], cursor: int) -> tuple[Snap, int]:
    now = int(time.time() * 1000)
    states = []
    for d in dexes:
        payload = {"type": "clearinghouseState", "user": address}
        if d:
            payload["dex"] = d
        states.append({"dex": d, "state": await info.post(payload, lane="monitor")})
    cur = Snap.from_states(states, now)
    led = await info.post({"type": "userNonFundingLedgerUpdates", "user": address,
                           "startTime": cursor + 1}, lane="monitor") or []
    inflows = [(int(r["time"]), float(r["delta"].get("usdc") or 0)) for r in led
               if r["delta"].get("type") == "deposit"]
    new_cursor = max([cursor] + [int(r["time"]) for r in led])
    events = diff_state(address, prev, cur) + check_triggers(address, prev, cur, env, inflows)
    con.execute("BEGIN")
    for e in events:
        record(con, e)
        if e.revet:
            request_revet(con, address)
    con.execute("COMMIT")
    for e in events:
        if e.revet or e.event in ("open", "close", "flip"):
            await notifier.send("integrity" if e.revet else "trade",
                                f"{address[:10]} {e.event} {e.coin or ''} ${e.notional:,.0f}", address=address)
    return cur, new_cursor


async def run_monitor(info: Any, con: sqlite3.Connection, root: Path, stop: asyncio.Event,
                      base_s: int = 120, fast_s: int = 30) -> None:
    notifier = Notifier(root)
    snaps: dict[str, Snap | None] = {}
    nxt: dict[str, float] = {}
    cursors: dict[str, int] = {}
    hb = Path(root) / "monitor.heartbeat"
    while not stop.is_set():
        now = time.time()
        for a in watchlist(con):
            if nxt.get(a, 0) > now:
                continue
            sp = raw_path(root, "state", a).with_suffix(".json")
            dexes = [s["dex"] for s in json.loads(sp.read_text())] if sp.exists() else [""]
            try:
                cur, cursors[a] = await poll_once(info, con, notifier, a, snaps.get(a), Envelope(),
                                                  dexes, cursors.get(a, int(now * 1000)))
                snaps[a] = cur
                nxt[a] = now + interval_for(cur, base_s, fast_s)
            except Exception as ex:  # noqa: BLE001 - one bad wallet must not stop the loop
                nxt[a] = now + base_s
                await notifier.send("health", f"poll failed for {a[:10]}: {type(ex).__name__}")
        recent = con.execute("SELECT address, ts, event, coin, notional FROM watch_events WHERE ts > ?",
                             (int(now * 1000) - 900_000,)).fetchall()
        evs = [Event(r[0], r[1], r[2], r[3], r[4], detail={"to": 1 if r[2] in ("open", "add") else 0})
               for r in recent]
        for f in flock(evs):
            await notifier.send("flock", f"{len(f['wallets'])} watched wallets {f['dir']} {f['coin']}")
        hb.write_text(str(int(now)))
        try:
            await asyncio.wait_for(stop.wait(), timeout=5)
        except TimeoutError:
            pass
