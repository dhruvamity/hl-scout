"""Daily/weekly jobs (plan §10.2). Each job runs as a subprocess at nice 10 so a crash is isolated."""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from hlscout.monitor.alerts import Notifier
from hlscout.ops.health import check, on_battery_low

log = logging.getLogger(__name__)

# (name, hour, minute, weekday or None, CLI args)
JOBS = [
    ("universe", 0, 15, None, ["universe"]),
    ("enqueue", 0, 45, None, ["enqueue"]),
    ("discover", 1, 0, None, ["discover"]),
    ("refresh_watch", 1, 15, None, ["refresh", "--scope", "watch"]),
    ("links", 3, 0, None, ["links", "--no-enqueue-members"]),
    ("score", 3, 20, None, ["score"]),
    ("refresh_all", 4, 0, 6, ["refresh", "--scope", "all"]),  # Sundays
    ("backup", 5, 0, None, None),
]


def run_cli(args: list[str], config: str) -> int:
    cmd = ["nice", "-n", "10", sys.executable, "-m", "hlscout.cli", *args, "--config", config]
    return subprocess.run(cmd, check=False).returncode


def backup_state(root: Path, keep: int = 7) -> Path:
    import sqlite3

    d = Path(root) / "backups"
    d.mkdir(exist_ok=True)
    dest = d / f"state-{datetime.now(UTC):%Y%m%d}.sqlite"
    src = sqlite3.connect(Path(root) / "state.sqlite")
    dst = sqlite3.connect(dest)
    src.backup(dst)
    dst.close()
    src.close()
    for old in sorted(d.glob("state-*.sqlite"))[:-keep]:
        old.unlink()
    return dest


def due(now: datetime, last_run: dict[str, str]) -> list[tuple]:
    out = []
    for job in JOBS:
        name, h, m, wd, _ = job
        key = now.strftime("%Y-%m-%d")
        if last_run.get(name) == key or (wd is not None and now.weekday() != wd):
            continue
        if (now.hour, now.minute) >= (h, m):
            out.append(job)
    return out


async def run_scheduler(root: Path, config: str, con, stop: asyncio.Event) -> None:
    notifier = Notifier(root)
    last_run: dict[str, str] = {}
    alerted: set[str] = set()
    while not stop.is_set():
        now = datetime.now(UTC)
        for name, _h, _m, _wd, args in due(now, last_run):
            if on_battery_low():
                break  # try again next tick, heavy jobs wait for power
            last_run[name] = now.strftime("%Y-%m-%d")
            if args is None:
                await asyncio.to_thread(backup_state, root)
                continue
            rc = await asyncio.to_thread(run_cli, args, config)
            if rc:
                await notifier.send("health", f"job {name} exited {rc}")
        problems = set(check(root, con, expect_monitor=False))
        for p in problems - alerted:
            await notifier.send("health", p)
        alerted = problems  # re-alert only after a problem clears and returns
        try:
            await asyncio.wait_for(stop.wait(), timeout=60)
        except TimeoutError:
            pass
