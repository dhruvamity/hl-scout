"""Rate-limited queue consumer: light hydrate (S2) -> deep hydrate -> assess (plan §3.2, §10.2).

Queue items are idempotent (UNIQUE(address, kind)); a crash leaves them `pending`/`running` and
`requeue_stale` returns running items to pending on startup.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from hlscout.config import Config
from hlscout.ingest.hydrate import hydrate_deep, hydrate_light
from hlscout.recon.equity import equity_series

log = logging.getLogger(__name__)
DAY_MS = 86_400_000


def enqueue(con: sqlite3.Connection, addresses: list[str], kind: str, lane: str,
            priority: float = 0.0) -> int:
    con.execute("BEGIN")
    n = 0
    for a in addresses:
        cur = con.execute(
            "INSERT OR IGNORE INTO queue(address, kind, lane, priority, updated_at) VALUES (?,?,?,?,?)",
            (a, kind, lane, priority, datetime.now(UTC).isoformat()))
        n += cur.rowcount
    con.execute("COMMIT")
    return n


def requeue_stale(con: sqlite3.Connection) -> None:
    con.execute("UPDATE queue SET state='pending' WHERE state='running'")


def next_item(con: sqlite3.Connection) -> tuple[int, str, str] | None:
    # finish deep vets before starting new light hydrates
    row = con.execute(
        "SELECT id, address, kind FROM queue WHERE state='pending' AND attempts < 3 "
        "ORDER BY CASE kind WHEN 'deep' THEN 0 ELSE 1 END, priority DESC, id LIMIT 1").fetchone()
    if row:
        con.execute("UPDATE queue SET state='running', attempts=attempts+1, updated_at=? WHERE id=?",
                    (datetime.now(UTC).isoformat(), row[0]))
    return row


def s2_screen(light: dict[str, Any], cfg: Config, now_ms: int) -> tuple[bool, str]:
    """Cheap per-wallet screen from `portfolio` + `userRole` (plan S2)."""
    role = (light.get("role") or {}).get("role")
    if role not in (None, "user"):
        return False, f"role:{role}"
    pf = light["portfolio"]
    if "perpAllTime" not in pf:
        return False, "no_perp_history"
    eq = equity_series(pf)
    if eq.is_empty():
        return False, "no_perp_history"
    age_d = (now_ms - int(eq["time"].min())) / DAY_MS
    if age_d < cfg.gates.min_track_days:
        return False, "too_young"
    if float(eq["cum_pnl"][-1]) <= 0:
        return False, "perp_pnl<=0"
    if float(eq["equity"].median()) < cfg.gates.median_equity_min_usd:
        return False, "low_median_equity"
    return True, "ok"


async def process(info: Any, con: sqlite3.Connection, root: Path, cfg: Config,
                  item: tuple[int, str, str], now_ms: int) -> None:
    qid, address, kind = item
    if kind == "light":
        light = await hydrate_light(info, address, lane="light_hydrate")
        ok, why = s2_screen(light, cfg, now_ms)
        con.execute("UPDATE addresses SET stage=?, role=?, last_hydrated=? WHERE address=?",
                    ("s2_pass" if ok else "screened_out", json.dumps(light["role"]),
                     datetime.now(UTC).isoformat(), address))
        if ok:
            enqueue(con, [address], "deep", "deep_vet", priority=1)
        else:
            log.info("S2 drop %s: %s", address[:10], why)
    else:
        from hlscout.recon.vet import assess_cached, audit, load_raw

        await hydrate_deep(info, address, root, lane="deep_vet")
        raw = load_raw(root, address)
        a = audit(address, raw)
        r = assess_cached(root, address, cfg)
        con.execute("INSERT INTO scores(entity, run_id, gates_json, metrics_json, score, stage, category, p_algo)"
                    " VALUES (?,?,?,?,?,?,?,?)",
                    (address, "worker", json.dumps(r["gates"], default=str),
                     json.dumps({k: v for k, v in r["metrics"].items() if k != "months"}, default=str),
                     None, r["stage"], r["category"]["category"], r["category"]["p_algo"]))
        con.execute("UPDATE addresses SET stage=?, reconcile_ok=?, history_truncated=?, last_hydrated=? "
                    "WHERE address=?", (r["stage"], int(a["reconcile_ok"]), int(a["history_truncated"]),
                                        datetime.now(UTC).isoformat(), address))
        log.info("deep %s -> %s %s", address[:10], r["stage"], r["reasons"][:6])
    con.execute("UPDATE queue SET state='done', updated_at=? WHERE id=?",
                (datetime.now(UTC).isoformat(), qid))


async def run_worker(info: Any, con: sqlite3.Connection, root: Path, cfg: Config,
                     stop: asyncio.Event, idle_s: float = 30.0) -> None:
    requeue_stale(con)
    import time

    while not stop.is_set():
        item = next_item(con)
        if item is None:
            await asyncio.sleep(idle_s)
            continue
        try:
            await process(info, con, root, cfg, item, int(time.time() * 1000))
        except Exception as e:  # noqa: BLE001
            log.warning("queue item %s failed: %r", item, e)
            con.execute("UPDATE queue SET state=? WHERE id=?",
                        ("failed" if con.execute("SELECT attempts FROM queue WHERE id=?",
                                                 (item[0],)).fetchone()[0] >= 3 else "pending", item[0]))


def candidates(root: Path, con: sqlite3.Connection) -> list[str]:
    """S1-pass addresses ordered by a recent-green hint then all-time PnL."""
    lb = pl.read_parquet(sorted((root / "leaderboard").glob("date=*.parquet"))[-1])
    ok = {r[0] for r in con.execute("SELECT address FROM addresses WHERE stage='s1_pass'")}
    lb = lb.filter(pl.col("address").is_in(list(ok))).with_columns(
        ((pl.col("pnl_month") > 0) & (pl.col("pnl_allTime") > 0)).alias("green"))
    return lb.sort(["green", "pnl_allTime"], descending=True)["address"].to_list()
