"""Live progress snapshot for the tracker page: queue, funnel, API usage, credits, tape."""

from __future__ import annotations

import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BUDGET_PER_MIN = 1080  # 1,200 x 0.90 headroom


def _age(path: Path, now: float) -> float | None:
    try:
        return now - float(path.read_text())
    except (OSError, ValueError):
        return None


def snapshot(root: Path, con: sqlite3.Connection, now: float | None = None,
             deep_cap: int | None = None) -> dict[str, Any]:
    now = now or time.time()
    root = Path(root)
    q: dict[str, dict[str, int]] = {}
    for kind, state, n in con.execute("SELECT kind, state, COUNT(*) FROM queue GROUP BY 1,2"):
        q.setdefault(kind, {})[state] = n
    for k in q.values():
        k["total"] = sum(k.values())
    deep = q.get("deep", {})
    # the worker stops deep vets at deep_cap (non-urgent ones done or running), so that is the real target
    counted = con.execute("SELECT COUNT(*) FROM queue WHERE kind='deep' AND state IN ('done','running') "
                          "AND priority < 1000000000").fetchone()[0]
    deep["target"] = min(deep_cap, deep.get("total", 0)) if deep_cap else deep.get("total", 0)
    deep["counted"] = counted
    cutoff = datetime.fromtimestamp(now - 900, UTC).isoformat()
    done15 = dict(con.execute("SELECT kind, COUNT(*) FROM queue WHERE state='done' AND updated_at > ? "
                              "GROUP BY 1", (cutoff,)).fetchall())
    light = q.get("light", {})
    light_rate = done15.get("light", 0) / 15
    eta_h = (light.get("pending", 0) / light_rate / 60) if light_rate else None
    deep_rate = done15.get("deep", 0) / 15
    deep_left = max(0, deep["target"] - counted)
    deep_eta_h = (deep_left / deep_rate / 60) if deep_rate and deep_left else (0.0 if not deep_left else None)
    last = con.execute("SELECT MAX(updated_at) FROM queue WHERE state='done'").fetchone()[0]
    last_age = (now - datetime.fromisoformat(last).replace(tzinfo=UTC).timestamp()) if last else None

    funnel = dict(con.execute("SELECT stage, COUNT(*) FROM addresses GROUP BY 1").fetchall())

    m0 = int(now // 60)
    rows = con.execute("SELECT minute, lane, weight, calls FROM api_usage WHERE minute > ?", (m0 - 60,)).fetchall()
    per_min: dict[int, float] = {}
    lanes: dict[str, float] = {}
    for m, lane, w, _ in rows:
        per_min[m] = per_min.get(m, 0) + w
        if m >= m0 - 4:
            lanes[lane] = lanes.get(lane, 0) + w
    series = [round(per_min.get(m, 0)) for m in range(m0 - 59, m0 + 1)]
    recent = [v for v in series[-6:-1]]  # last 5 complete minutes
    avg5 = sum(recent) / len(recent) if recent else 0.0

    try:
        used = con.execute("SELECT used FROM credits WHERE month=?",
                           (datetime.now(UTC).strftime("%Y-%m"),)).fetchone()
    except sqlite3.Error:
        used = None
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    files = list((root / "tape").glob(f"date={day}/hour=*/*.parquet"))
    gaps = con.execute("SELECT COUNT(*) FROM tape_gaps WHERE end_ts > ?", (int((now - 86400) * 1000),)).fetchone()[0]
    return {
        "updated": int(now),
        "queue": q, "light_rate_per_min": round(light_rate, 2), "deep_rate_per_min": round(deep_rate, 2),
        "deep_eta_hours": round(deep_eta_h, 1) if deep_eta_h is not None else None, "eta_hours": round(eta_h, 1) if eta_h else None,
        "last_progress_age_s": round(last_age) if last_age is not None else None,
        "funnel": funnel,
        "wallets_hydrated": len(list((root / "raw" / "fills").glob("*.parquet"))),
        "api": {"budget_per_min": BUDGET_PER_MIN, "avg_last_5min": round(avg5), "series_60min": series,
                "by_lane_5min": {k: round(v) for k, v in lanes.items()}},
        "hypedexer_credits": {"used": used[0] if used else 0, "cap": 4500},
        "tape": {"heartbeat_age_s": (round(a) if (a := _age(root / "tape.heartbeat", now)) is not None else None),
                 "files_today": len(files), "mb_today": round(sum(f.stat().st_size for f in files) / 1e6, 1),
                 "gaps_24h": gaps},
        "monitor_age_s": (round(a) if (a := _age(root / "monitor.heartbeat", now)) is not None else None),
    }
