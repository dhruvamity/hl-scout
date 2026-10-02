"""Forward validation (plan §8.3, P10): freeze the list, later compare live results to the backtest."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

import numpy as np

from hlscout.recon.roundtrips import build_round_trips
from hlscout.recon.vet import load_raw

DAY_MS = 86_400_000


def freeze(con: sqlite3.Connection, snap_ts: int | None = None) -> int:
    """Copy the current ranked list (qualified/needs_qa/reformed) into forward_lists."""
    ts = snap_ts or int(time.time() * 1000)
    rows = con.execute("SELECT entity, category, score, stage, metrics_json FROM scores WHERE stage IN "
                       "('qualified','provisional','needs_qa','reformed')").fetchall()
    con.execute("BEGIN")
    for a, cat, sc, st, mj in rows:
        m = json.loads(mj or "{}")
        base = {k: m.get(k) for k in ("net_180d", "max_dd_twr", "win_rate", "profit_factor", "track_days")}
        con.execute("INSERT OR REPLACE INTO forward_lists VALUES (?,?,?,?,?,?)",
                    (ts, a, cat, sc, st, json.dumps(base)))
    con.execute("COMMIT")
    return len(rows)


def live_stats(root: Path, address: str, since_ms: int) -> dict[str, Any]:
    raw = load_raw(root, address)
    trips, _ = build_round_trips(raw["fills"], raw["funding"], address)
    t = trips.filter(trips["close_ts"] >= since_ms) if not trips.is_empty() else trips
    if t.is_empty():
        return {"n": 0, "net": 0.0, "dd": 0.0, "win_rate": None}
    net = (t["pnl"] - t["fees"] + t["funding"]).to_numpy()
    cum = np.cumsum(net)
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]
    eq = float(raw["portfolio"].get("perpAllTime", {}).get("accountValueHistory", [[0, "0"]])[-1][1]) or 1.0
    return {"n": int(t.height), "net": float(net.sum()), "dd": float(((peak - cum) / max(eq, 1.0)).max()),
            "win_rate": float((net > 0).mean())}


def report(con: sqlite3.Connection, root: Path, snap_ts: int, now_ms: int | None = None) -> dict[str, Any]:
    """Per-wallet live vs baseline, plus list-level hit rate and score-vs-forward rank correlation."""
    now = now_ms or int(time.time() * 1000)
    rows = con.execute("SELECT address, category, score, stage, baseline_json FROM forward_lists "
                       "WHERE snap_ts=?", (snap_ts,)).fetchall()
    out, scores, nets = [], [], []
    for a, cat, sc, st, bj in rows:
        base = json.loads(bj)
        try:
            live = live_stats(root, a, snap_ts)
        except FileNotFoundError:
            continue
        dd_limit = (base.get("max_dd_twr") or 0.3) * 1.5
        out.append({"address": a, "category": cat, "stage": st, "score": sc, **live,
                    "breach": live["dd"] > dd_limit, "profitable": live["net"] > 0})
        if sc is not None and live["n"]:
            scores.append(sc)
            nets.append(live["net"])
    dropped = [r[0] for r in con.execute(
        "SELECT f.address FROM forward_lists f JOIN scores s ON s.entity=f.address WHERE f.snap_ts=? "
        "AND s.stage NOT IN ('qualified','provisional','needs_qa','reformed')", (snap_ts,))]
    active = [r for r in out if r["n"]]
    corr = None
    if len(scores) >= 5:
        rs = np.argsort(np.argsort(scores))
        rn = np.argsort(np.argsort(nets))
        corr = float(np.corrcoef(rs, rn)[0, 1])
    return {"days": (now - snap_ts) / DAY_MS, "listed": len(rows), "active": len(active),
            "hit_rate": (sum(r["profitable"] for r in active) / len(active)) if active else None,
            "breaches": sum(r["breach"] for r in out), "dropped_since": dropped,
            "score_rank_corr": corr, "wallets": out}
