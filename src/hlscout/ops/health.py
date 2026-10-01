"""Health checks (plan §10.3): tape silence, stalled queue, disk, stale monitor."""

from __future__ import annotations

import shutil
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path


def _age(p: Path, now: float) -> float | None:
    try:
        return now - float(p.read_text()) if p.suffix == ".heartbeat" else now - p.stat().st_mtime
    except (OSError, ValueError):
        return None


def check(root: Path, con: sqlite3.Connection, now: float | None = None, min_free_gb: float = 5.0,
          expect_monitor: bool = False) -> list[str]:
    """Return a list of human-readable problems (empty = healthy)."""
    now = now or time.time()
    root = Path(root)
    out = []
    tape = _age(root / "tape.heartbeat", now)
    if tape is None or tape > 120:
        out.append(f"tape silent ({'no heartbeat' if tape is None else f'{tape:.0f}s'})")
    pending = con.execute("SELECT COUNT(*) FROM queue WHERE state='pending'").fetchone()[0]
    last = con.execute("SELECT MAX(updated_at) FROM queue WHERE state IN ('done','running')").fetchone()[0]
    if pending and last:
        age = now - datetime.fromisoformat(last).replace(tzinfo=UTC).timestamp()
        if age > 900:
            out.append(f"queue stalled ({age / 60:.0f} min since last progress, {pending} pending)")
    free = shutil.disk_usage(root).free / 1e9
    if free < min_free_gb:
        out.append(f"low disk: {free:.1f} GB free")
    if expect_monitor:
        mon = _age(root / "monitor.heartbeat", now)
        if mon is None or mon > 300:
            out.append("monitor not running")
    return out


def on_battery_low(threshold: int = 30) -> bool:
    """macOS: True when on battery below `threshold`% (heavy jobs should pause). False if unknown."""
    import re
    import subprocess

    try:
        o = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=5).stdout
    except Exception:  # noqa: BLE001
        return False
    m = re.search(r"(\d+)%", o)
    return "Battery Power" in o and bool(m) and int(m.group(1)) < threshold
