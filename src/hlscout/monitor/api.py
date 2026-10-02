"""Read-only JSON feed for downstream tools (versioned schema, see docs/API.md). No write endpoints, no keys."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

SCHEMA_VERSION = 1
LIST_STAGES = ("qualified", "provisional")


def _metrics(mj: str | None) -> dict[str, Any]:
    keep = ("track_days", "genuine_months", "twr_all", "max_dd_twr", "sharpe", "tstat", "dsr_prob", "net_180d",
            "win_rate", "profit_factor", "expectancy_bps", "median_hold_s", "lev_daily_p95")
    m = json.loads(mj or "{}")
    return {k: m.get(k) for k in keep if k in m}


def watchlist(con: sqlite3.Connection, stages: tuple[str, ...] = LIST_STAGES) -> dict[str, Any]:
    q = ",".join("?" * len(stages))
    rows = con.execute(
        f"SELECT entity, stage, category, score, p_algo, metrics_json FROM scores WHERE run_id='latest' "
        f"AND stage IN ({q}) ORDER BY stage, category, score DESC", stages).fetchall()
    return {"schema_version": SCHEMA_VERSION, "count": len(rows), "wallets": [
        {"address": a, "tier": st, "category": c, "score": sc, "p_algo": pa, "metrics": _metrics(mj)}
        for a, st, c, sc, pa, mj in rows]}


def wallet(con: sqlite3.Connection, address: str) -> dict[str, Any] | None:
    a = address.lower()
    r = con.execute("SELECT entity, stage, category, score, p_algo, gates_json, metrics_json FROM scores "
                    "WHERE run_id='latest' AND entity=?", (a,)).fetchone()
    if r is None:
        return None
    det = con.execute("SELECT code, severity, penalty, evidence_json FROM detector_results WHERE run_id='latest' "
                      "AND entity=?", (a,)).fetchall()
    cl = con.execute("SELECT cluster_id, confidence, members FROM clusters WHERE members LIKE ?",
                     (f'%{a}%',)).fetchone()
    return {"schema_version": SCHEMA_VERSION, "address": r[0], "tier": r[1], "category": r[2], "score": r[3],
            "p_algo": r[4], "gates": json.loads(r[5] or "[]"), "metrics": _metrics(r[6]),
            "findings": [{"code": c, "severity": s, "penalty": p, "detail": json.loads(e)} for c, s, p, e in det],
            "cluster": {"id": cl[0], "confidence": cl[1], "members": json.loads(cl[2])} if cl else None}


def events(con: sqlite3.Connection, since: int = 0, limit: int = 500) -> dict[str, Any]:
    rows = con.execute("SELECT address, ts, event, coin, notional, source FROM watch_events WHERE ts > ? "
                       "ORDER BY ts LIMIT ?", (since, min(limit, 5000))).fetchall()
    ev = [{"address": a, "ts": t, "event": e, "coin": c, "notional": n, "source": s} for a, t, e, c, n, s in rows]
    return {"schema_version": SCHEMA_VERSION, "count": len(ev), "next_since": ev[-1]["ts"] if ev else since,
            "events": ev}
