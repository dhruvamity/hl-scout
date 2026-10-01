"""Fetch per-dex state for already-hydrated addresses, then re-audit them."""
import asyncio
import json
import sys
from pathlib import Path

import polars as pl

from hlscout.clients.info import InfoClient
from hlscout.clients.ratelimit import RateLimiter
from hlscout.ingest.hydrate import raw_path
from hlscout.recon.vet import audit, load_raw

root = Path("data")
addrs = sys.argv[1:] or [p.stem for p in (root / "raw/fills").glob("*.parquet")]

async def main():
    info = InfoClient(RateLimiter())
    ok = 0
    for a in addrs:
        f = pl.read_parquet(raw_path(root, "fills", a), columns=["coin"])
        dexes = [""] + sorted({c.split(":")[0] for c in f["coin"].unique().to_list() if ":" in c})
        states = [{"dex": d, "state": await info.post({"type": "clearinghouseState", "user": a, "dex": d}, lane="deep_vet")} for d in dexes]
        raw_path(root, "state", a).with_suffix(".json").parent.mkdir(parents=True, exist_ok=True)
        raw_path(root, "state", a).with_suffix(".json").write_text(json.dumps(states))
        r = audit(a, load_raw(root, a)); rec = r["reconcile"]; ok += bool(rec["ok"])
        print(a[:10], rec["ok"], round(rec["residual_pct"], 2), flush=True)
    print(f"PASS {ok}/{len(addrs)}")
    await info.aclose()
asyncio.run(main())
