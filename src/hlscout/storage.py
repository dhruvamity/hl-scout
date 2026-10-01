"""SQLite (WAL) for state/queue, Parquet for raw data, DuckDB for analytics."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import duckdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS addresses (
  address TEXT PRIMARY KEY, first_seen TEXT, sources TEXT, role TEXT, master TEXT,
  is_vault INTEGER DEFAULT 0, cluster_id TEXT, stage TEXT DEFAULT 'discovered',
  last_hydrated TEXT, history_truncated INTEGER DEFAULT 0, reconcile_ok INTEGER
);
CREATE TABLE IF NOT EXISTS queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT, address TEXT NOT NULL, kind TEXT NOT NULL,
  lane TEXT NOT NULL, priority INTEGER DEFAULT 0, state TEXT DEFAULT 'pending',
  checkpoint TEXT, attempts INTEGER DEFAULT 0, updated_at TEXT,
  UNIQUE(address, kind)
);
CREATE TABLE IF NOT EXISTS leaderboard_snapshots (
  snap_date TEXT, address TEXT, account_value REAL, raw_json TEXT,
  PRIMARY KEY (snap_date, address)
);
CREATE TABLE IF NOT EXISTS detector_results (
  entity TEXT, run_id TEXT, code TEXT, severity TEXT, penalty REAL, evidence_json TEXT
);
CREATE TABLE IF NOT EXISTS scores (
  entity TEXT, run_id TEXT, gates_json TEXT, metrics_json TEXT, score REAL, stage TEXT,
  category TEXT, p_algo REAL
);
CREATE TABLE IF NOT EXISTS watch_events (address TEXT, ts INTEGER, event TEXT, coin TEXT, notional REAL, source TEXT);
CREATE TABLE IF NOT EXISTS ingest_gaps (source TEXT, start_ts INTEGER, end_ts INTEGER, reason TEXT);
CREATE TABLE IF NOT EXISTS tape_gaps (coin TEXT, start_ts INTEGER, end_ts INTEGER, reason TEXT);
CREATE TABLE IF NOT EXISTS links (
  src TEXT, dst TEXT, edge_type TEXT, weight REAL, first_ts INTEGER, last_ts INTEGER, evidence TEXT
);
CREATE TABLE IF NOT EXISTS clusters (cluster_id TEXT PRIMARY KEY, members TEXT, method TEXT, confidence REAL);
CREATE TABLE IF NOT EXISTS forward_lists (
  snap_ts INTEGER, address TEXT, category TEXT, score REAL, stage TEXT, baseline_json TEXT,
  PRIMARY KEY (snap_ts, address)
);
CREATE TABLE IF NOT EXISTS api_usage (
  minute INTEGER, lane TEXT, weight REAL, calls INTEGER, PRIMARY KEY (minute, lane)
);
CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, kind TEXT, started_at TEXT, finished_at TEXT, notes TEXT);
"""


def connect_state(data_dir: str | Path) -> sqlite3.Connection:
    d = Path(data_dir)
    d.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(d / "state.sqlite", isolation_level=None)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.executescript(SCHEMA)
    return con


def analytics(data_dir: str | Path) -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB for ad-hoc queries over Parquet under data_dir (read_parquet globs)."""
    return duckdb.connect(":memory:")


def usage_recorder(data_dir: str | Path):
    """Callable (lane, weight) that tallies API weight per minute per lane, shared across processes."""
    import time

    con = connect_state(data_dir)

    def rec(lane: str, weight: float) -> None:
        m = int(time.time() // 60)
        try:
            con.execute("INSERT INTO api_usage VALUES (?,?,?,1) ON CONFLICT(minute, lane) DO UPDATE "
                        "SET weight=weight+?, calls=calls+1", (m, lane, weight, weight))
        except sqlite3.Error:
            pass  # stats must never break ingestion

    return rec
