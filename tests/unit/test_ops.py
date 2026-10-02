import sqlite3
import time
from datetime import UTC, datetime, timedelta

from hlscout.ops.health import check
from hlscout.ops.scheduler import backup_state, due
from hlscout.storage import SCHEMA


def db():
    con = sqlite3.connect(":memory:", isolation_level=None)
    con.executescript(SCHEMA)
    return con


def test_health_flags_silent_tape_and_stalled_queue(tmp_path):
    con = db()
    assert any("tape silent" in p for p in check(tmp_path, con))
    (tmp_path / "tape.heartbeat").write_text(str(int(time.time())))
    assert check(tmp_path, con) == []
    old = (datetime.now(UTC) - timedelta(minutes=40)).isoformat()
    con.execute("INSERT INTO queue(address, kind, lane, state, updated_at) VALUES ('a','light','l','done',?)", (old,))
    con.execute("INSERT INTO queue(address, kind, lane, state) VALUES ('b','light','l','pending')")
    assert any("queue stalled" in p for p in check(tmp_path, con))


def test_due_runs_once_per_day():
    now = datetime(2026, 10, 2, 1, 30, tzinfo=UTC)
    names = {j[0] for j in due(now, {})}
    assert {"universe", "enqueue", "discover", "refresh_watch"} <= names and "score" not in names
    assert "universe" not in {j[0] for j in due(now, {"universe": "2026-10-02"})}


def test_backup_rotates(tmp_path):
    from hlscout.storage import connect_state

    connect_state(tmp_path)
    p = backup_state(tmp_path, keep=1)
    assert p.exists()
