"""Backfill truncated wallets from an archive source and mark them for coarse early-month grading."""

from __future__ import annotations

import json
import time
from pathlib import Path

import polars as pl

from hlscout.archive.hypedexer import Getter, derive_closed_pnl, fetch_fills
from hlscout.ingest.hydrate import FILL_SCHEMA, _merge_write, raw_path


DAY_MS = 86_400_000


def plan_backfill(root: Path, address: str) -> dict:
    """Window to fetch from the archive: account start -> the start of the reliable local window.

    Local fills before `reliable_since` are sparse (the public API drops old fills), so the archive is asked for
    that whole span and merged by (coin, tid). `est_credits` = rows/25 + calls, with the row rate taken from the
    reliable window (so market-maker-like books show up as expensive before any credit is spent)."""
    import bisect

    from hlscout.recon import equity as eq
    from hlscout.recon.roundtrips import perp_only, reliable_since

    root = Path(root)
    have = perp_only(pl.read_parquet(raw_path(root, "fills", address)))
    pf = json.loads(raw_path(root, "portfolio", address).with_suffix(".json").read_text())
    t: list[int] = []
    v: list[float] = []
    if "perpAllTime" in pf:
        e = eq.equity_series(pf)
        t, v = e["time"].to_list(), e["equity"].to_list()

    def at(x: int) -> float | None:
        i = bisect.bisect_right(t, x) - 1
        return v[i] if i >= 0 else None

    rel, _ = reliable_since(have, at)
    first_local = int(have["time"].min())
    end = rel if rel is not None else first_local
    led = pl.read_parquet(raw_path(root, "ledger", address))
    start = min([int(led["time"].min())] if not led.is_empty() else [first_local - 365 * DAY_MS])
    if t:
        start = min(start, int(t[0]))
    recent = have.filter(pl.col("time") >= end)
    rate = recent.height / max(1.0, (int(have["time"].max()) - end) / DAY_MS) if recent.height else 50.0
    days = max(0.0, (end - start) / DAY_MS)
    rows = rate * days
    return {"start": start, "end": end, "days": days, "est_rows": rows,
            "est_credits": int(rows / 25) + int(rows / 1000) + 2}


async def backfill_address(g: Getter, root: Path, address: str, budget=None) -> dict:
    root = Path(root)
    fp = raw_path(root, "fills", address)
    have = pl.read_parquet(fp)
    plan = plan_backfill(root, address)
    rows = await fetch_fills(g, address, plan["start"] - DAY_MS, plan["end"] + 3_600_000, budget=budget)
    new = pl.DataFrame(rows, schema=FILL_SCHEMA) if rows else pl.DataFrame(schema=FILL_SCHEMA)
    merged = derive_closed_pnl(pl.concat([new, have], how="vertical_relaxed").unique(
        subset=["coin", "tid"], keep="last").sort("time"))  # local rows win on a (coin, tid) clash
    _merge_write(fp, merged, ["coin", "tid"])
    mp = raw_path(root, "meta", address).with_suffix(".json")
    mp.parent.mkdir(parents=True, exist_ok=True)
    meta = json.loads(mp.read_text()) if mp.exists() else {}
    meta["archive"] = {"done": True, "source": "hypedexer", "fetched": len(rows),
                       "window": [plan["start"], plan["end"]], "at": int(time.time() * 1000)}
    mp.write_text(json.dumps(meta))
    return meta["archive"]


SOFT_FOR_BACKFILL = {"G1", "G1b", "G2", "G6", "G7", "G11"}  # misses that more history could cure


def backfill_candidates(root: Path, max_credits_per_wallet: int = 1200) -> list[dict]:
    """Wallets worth spending archive credits on, best first.

    Worth it = history cut/short, no veto in what we can see, only 'more history could cure it' gates failing
    on the recent window, and an affordable estimate. Ranked by net PnL on the reliable window."""
    from hlscout.recon.vet import assess_cached, audit, load_raw

    out: list[dict] = []
    for p in sorted((Path(root) / "raw" / "fills").glob("*.parquet")):
        try:
            raw = load_raw(root, p.stem)
        except FileNotFoundError:  # hydrate still in progress (or interrupted): skip
            continue
        if raw["meta"].get("archive", {}).get("done"):
            continue
        a = audit(p.stem, raw)
        if not (a["history_truncated"] or a.get("partial_history")) or not (a["reconcile_ok"] or a["reconcile"].get("soft")):
            continue
        r = assess_cached(root, p.stem)
        if r["verdict"]["vetoes"]:
            continue
        # evaluate the recent window as if history were complete: which gates would fail?
        failed = {g["gate"].split()[0] for g in r.get("gates", []) if g["pass"] is False}
        if failed and not failed <= SOFT_FOR_BACKFILL:
            continue
        plan = plan_backfill(root, p.stem)
        if plan["est_credits"] > max_credits_per_wallet or plan["days"] < 30:
            continue
        out.append({"address": p.stem, "net": a.get("net_trading_pnl") or 0.0, **plan})
    return sorted(out, key=lambda x: -x["net"])
