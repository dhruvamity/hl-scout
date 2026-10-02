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


URGENT = 1e9  # re-vet requests from the monitor jump the queue


def next_item(con: sqlite3.Connection, deep_cap: int | None = None) -> tuple[int, str, str] | None:
    """Order: urgent re-vets, then ALL cheap light screens, then deep vets best-coarse-score first.

    Light screens cost ~22 weight; deep vets cost hundreds, so the cheap pass must finish first
    and deep vets are capped (`deep_cap`) to the best-ranked shortlist.
    """
    cap_sql = ""
    args: tuple = ()
    if deep_cap is not None:
        cap_sql = ("AND (kind IN ('light','refresh') OR priority >= ? OR (SELECT COUNT(*) FROM queue q2 WHERE q2.kind='deep' "
                   "AND q2.state IN ('done','running') AND q2.priority < ?) < ?)")
        args = (URGENT, URGENT, deep_cap)
    row = con.execute(
        "SELECT id, address, kind FROM queue WHERE state='pending' AND attempts < 3 " + cap_sql +
        " ORDER BY CASE WHEN priority >= 1000000000 THEN 0 WHEN kind='light' THEN 1 "
        "WHEN kind='refresh' THEN 2 ELSE 3 END, "
        "priority DESC, id LIMIT 1", args).fetchone()
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
    sc = cfg.screen
    pnl = eq["cum_pnl"].fill_null(0.0)
    dd = float((pnl.cum_max() - pnl).max()) / max(float(eq["equity"].max()), 1.0)
    if dd > sc.max_coarse_dd:
        return False, f"coarse_dd>{sc.max_coarse_dd:.0%}"
    cutoff = now_ms - sc.recent_days * DAY_MS
    before = eq.filter(eq["time"] <= cutoff)
    ref = float(before["cum_pnl"][-1]) if not before.is_empty() else float(pnl[0])
    if float(pnl[-1]) == ref:
        return False, "inactive_recent"
    st = light.get("state")
    if st:
        ms = st.get("marginSummary", {})
        av = float(ms.get("accountValue", 0))
        if av > 0 and float(ms.get("totalNtlPos", 0)) / av > sc.max_open_leverage:
            return False, "open_leverage"
    return True, "ok"


def coarse_score(light: dict[str, Any]) -> float:
    """Shortlist rank: all-time PnL over median equity (capped so one lucky multiple can't dominate)."""
    eq = equity_series(light["portfolio"])
    return min(float(eq["cum_pnl"][-1]) / max(float(eq["equity"].median()), 1.0), 50.0)


def enqueue_refresh(con: sqlite3.Connection, addresses: list[str], priority: float = 0.0) -> int:
    """(Re)queue incremental refreshes; idempotent per address."""
    con.execute("BEGIN")
    n = 0
    for a in addresses:
        con.execute("INSERT OR IGNORE INTO queue(address, kind, lane, priority, updated_at) "
                    "VALUES (?, 'refresh', 'deep_vet', ?, ?)", (a, priority, datetime.now(UTC).isoformat()))
        cur = con.execute("UPDATE queue SET state='pending', attempts=0, priority=? WHERE address=? "
                          "AND kind='refresh' AND state IN ('done','failed')", (priority, a))
        n += cur.rowcount
    con.execute("COMMIT")
    return n


async def refresh_wallet(info: Any, con: sqlite3.Connection, root: Path, cfg: Config, address: str) -> None:
    from hlscout.recon.vet import assess_cached, audit, load_raw

    await hydrate_deep(info, address, root, lane="deep_vet")
    r = assess_cached(root, address, cfg)
    a = audit(address, load_raw(root, address))
    con.execute("INSERT INTO scores(entity, run_id, gates_json, metrics_json, score, stage, category, p_algo)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (address, "refresh", json.dumps(r["gates"], default=str),
                 json.dumps({k: v for k, v in r["metrics"].items() if k != "months"}, default=str),
                 None, r["stage"], r["category"]["category"], r["category"]["p_algo"]))
    con.execute("UPDATE addresses SET stage=?, reconcile_ok=?, history_truncated=?, last_hydrated=? WHERE address=?",
                (r["stage"], int(a["reconcile_ok"]), int(a["history_truncated"]),
                 datetime.now(UTC).isoformat(), address))
    log.info("refresh %s -> %s %s", address[:10], r["stage"], r["reasons"][:6])


async def hft_prescreen(info: Any, address: str, cfg: Config) -> dict[str, Any] | None:
    """One `userFills` call (~22 weight, newest <= 2000 fills) to skip HFT/MM books before a
    full pull that can cost thousands of weight. Returns the reason dict, or None to proceed."""
    rows = await info.post({"type": "userFills", "user": address, "aggregateByTime": False},
                           lane="deep_vet")
    if not isinstance(rows, list) or len(rows) < 1500:
        return None  # sparse book: cannot be a high-frequency one
    t = [int(r["time"]) for r in rows]
    span_d = max((max(t) - min(t)) / DAY_MS, 1e-3)
    tpd = len(rows) / span_d
    maker = sum(1 for r in rows if r.get("crossed") is False) / len(rows)
    g = cfg.gates
    if tpd > g.trades_per_day_max:
        return {"trades_per_day": round(tpd), "span_days": round(span_d, 2)}
    if maker > g.maker_share_max:
        return {"maker_share": round(maker, 2)}
    return None


async def process(info: Any, con: sqlite3.Connection, root: Path, cfg: Config,
                  item: tuple[int, str, str], now_ms: int) -> None:
    qid, address, kind = item
    if kind == "refresh":  # incremental re-pull + re-assess of an already-vetted wallet (no prescreen, no cap)
        await refresh_wallet(info, con, root, cfg, address)
    elif kind == "light":
        light = await hydrate_light(info, address, lane="light_hydrate", with_role=False)
        ok, why = s2_screen(light, cfg, now_ms)
        con.execute("UPDATE addresses SET stage=?, role=?, last_hydrated=? WHERE address=?",
                    ("s2_pass" if ok else "screened_out", json.dumps(light["role"]),
                     datetime.now(UTC).isoformat(), address))
        if ok:
            enqueue(con, [address], "deep", "deep_vet", priority=coarse_score(light))
        else:
            log.info("S2 drop %s: %s", address[:10], why)
    else:
        from hlscout.recon.vet import assess_cached, audit, load_raw

        skip = await hft_prescreen(info, address, cfg)
        if skip:
            con.execute("UPDATE addresses SET stage='vet_fail', last_hydrated=? WHERE address=?",
                        (datetime.now(UTC).isoformat(), address))
            con.execute("INSERT INTO scores(entity, run_id, gates_json, metrics_json, score, stage, category, p_algo)"
                        " VALUES (?, 'worker', '[]', ?, NULL, 'vet_fail', 'MM_HFT', NULL)",
                        (address, json.dumps({"prescreen": skip})))
            log.info("deep %s -> prescreen %s", address[:10], skip)
            con.execute("UPDATE queue SET state='done', updated_at=? WHERE id=?",
                        (datetime.now(UTC).isoformat(), qid))
            return
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


async def _loop(info: Any, con: sqlite3.Connection, root: Path, cfg: Config, stop: asyncio.Event,
                idle_s: float) -> None:
    import time

    while not stop.is_set():
        item = next_item(con, cfg.screen.deep_cap)  # no await between select and update: claim is atomic
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


async def run_worker(info: Any, con: sqlite3.Connection, root: Path, cfg: Config,
                     stop: asyncio.Event, idle_s: float = 30.0) -> None:
    """`cfg.api.worker_concurrency` loops share one rate limiter, so concurrency hides network
    latency without raising the weight spent per minute."""
    requeue_stale(con)
    await asyncio.gather(*(_loop(info, con, root, cfg, stop, idle_s)
                           for _ in range(max(1, cfg.api.worker_concurrency))))


def candidates(root: Path, con: sqlite3.Connection) -> list[str]:
    """S1-pass addresses ordered by a recent-green hint then all-time PnL."""
    lb = pl.read_parquet(sorted((root / "leaderboard").glob("date=*.parquet"))[-1])
    ok = {r[0] for r in con.execute("SELECT address FROM addresses WHERE stage='s1_pass'")}
    lb = lb.filter(pl.col("address").is_in(list(ok))).with_columns(
        ((pl.col("pnl_month") > 0) & (pl.col("pnl_allTime") > 0)).alias("green"))
    return lb.sort(["green", "pnl_allTime"], descending=True)["address"].to_list()
