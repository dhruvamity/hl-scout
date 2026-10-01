"""Backfill truncated wallets from an archive source and mark them for coarse early-month grading."""

from __future__ import annotations

import json
import time
from pathlib import Path

import polars as pl

from hlscout.archive.hypedexer import Getter, derive_closed_pnl, fetch_fills
from hlscout.ingest.hydrate import FILL_SCHEMA, _merge_write, raw_path


async def backfill_address(g: Getter, root: Path, address: str) -> dict:
    root = Path(root)
    fp = raw_path(root, "fills", address)
    have = pl.read_parquet(fp)
    first_local = int(have["time"].min())
    led = pl.read_parquet(raw_path(root, "ledger", address))
    start = int(led["time"].min()) if not led.is_empty() else first_local - 365 * 86_400_000
    pf = json.loads(raw_path(root, "portfolio", address).with_suffix(".json").read_text())
    hist = pf.get("perpAllTime", {}).get("accountValueHistory") or []
    if hist:
        start = min(start, int(hist[0][0]))
    rows = await fetch_fills(g, address, start - 86_400_000, first_local)
    new = pl.DataFrame(rows, schema=FILL_SCHEMA) if rows else pl.DataFrame(schema=FILL_SCHEMA)
    merged = derive_closed_pnl(pl.concat([new, have], how="vertical_relaxed").unique(
        subset=["coin", "tid"], keep="last").sort("time"))
    _merge_write(fp, merged, ["coin", "tid"])
    mp = raw_path(root, "meta", address).with_suffix(".json")
    mp.parent.mkdir(parents=True, exist_ok=True)
    meta = json.loads(mp.read_text()) if mp.exists() else {}
    meta["archive"] = {"done": True, "source": "hypedexer", "fetched": len(rows),
                       "at": int(time.time() * 1000)}
    mp.write_text(json.dumps(meta))
    return meta["archive"]


def truncated_wallets(root: Path) -> list[str]:
    """Wallets that look truncated and have not yet had an archive pass."""
    from hlscout.recon.vet import audit, load_raw

    out = []
    for p in sorted((Path(root) / "raw" / "fills").glob("*.parquet")):
        raw = load_raw(root, p.stem)
        if raw["meta"].get("archive", {}).get("done"):
            continue
        if audit(p.stem, raw)["history_truncated"]:
            out.append(p.stem)
    return out
