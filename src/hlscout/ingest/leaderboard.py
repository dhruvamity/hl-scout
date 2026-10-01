"""Leaderboard snapshot, address registry and day-over-day diff (plan §3.2 U, §2.1)."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import httpx
import polars as pl

WINDOWS = ("day", "week", "month", "allTime")
ALLOWED_HOST = "stats-data.hyperliquid.xyz"


def download(url: str, dest: Path, timeout: float = 300) -> Path:
    if httpx.URL(url).host != ALLOWED_HOST:
        raise ValueError("leaderboard host not allowlisted")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    with httpx.stream("GET", url, timeout=timeout) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            f.writelines(r.iter_bytes())
    tmp.rename(dest)
    return dest


def parse(path: Path) -> pl.DataFrame:
    """Flatten rows to: address, account_value, display_name, {pnl,roi,vlm}_{window}."""
    rows = json.loads(Path(path).read_text())["leaderboardRows"]
    out: list[dict] = []
    for r in rows:
        d = {"address": r["ethAddress"].lower(), "account_value": float(r["accountValue"]),
             "display_name": r.get("displayName")}
        perf = dict(r["windowPerformances"])
        for w in WINDOWS:
            p = perf.get(w, {})
            for k in ("pnl", "roi", "vlm"):
                d[f"{k}_{w}"] = float(p.get(k, 0) or 0)
        out.append(d)
    return pl.DataFrame(out)


def snapshot(df: pl.DataFrame, root: Path, date: str | None = None) -> Path:
    date = date or datetime.now(UTC).strftime("%Y-%m-%d")
    out = root / "leaderboard" / f"date={date}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(out, compression="zstd")
    return out


def previous_snapshot(root: Path, before: str) -> pl.DataFrame | None:
    files = sorted(f for f in (root / "leaderboard").glob("date=*.parquet") if f.stem[5:] < before)
    return pl.read_parquet(files[-1]) if files else None


def diff(prev: pl.DataFrame | None, cur: pl.DataFrame) -> dict[str, list[str]]:
    if prev is None:
        return {"new": cur["address"].to_list(), "gone": []}
    p, c = set(prev["address"]), set(cur["address"])
    return {"new": sorted(c - p), "gone": sorted(p - c)}


def register(con: sqlite3.Connection, addresses: list[str], source: str) -> int:
    """Upsert into the address registry, appending `source`; returns count of new rows."""
    now = datetime.now(UTC).isoformat()
    before = con.execute("SELECT count(*) FROM addresses").fetchone()[0]
    con.execute("BEGIN")
    for a in addresses:
        con.execute(
            "INSERT INTO addresses(address, first_seen, sources) VALUES (?,?,?) "
            "ON CONFLICT(address) DO UPDATE SET sources = CASE "
            "WHEN instr(',' || sources || ',', ',' || ? || ',') > 0 THEN sources "
            "ELSE sources || ',' || ? END",
            (a, now, source, source, source),
        )
    con.execute("COMMIT")
    return con.execute("SELECT count(*) FROM addresses").fetchone()[0] - before
