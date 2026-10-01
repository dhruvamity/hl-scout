"""P3 acceptance: vet N random S1-pass wallets; report reconcile pass rate and failures."""
import asyncio
import random
import sys
from pathlib import Path

import polars as pl

from hlscout.clients.info import InfoClient
from hlscout.clients.ratelimit import RateLimiter
from hlscout.recon.vet import vet_address

N = int(sys.argv[1]) if len(sys.argv) > 1 else 20
root = Path("data")
lb = pl.read_parquet(sorted((root / "leaderboard").glob("date=*.parquet"))[-1])
cand = lb.filter((pl.col("account_value") >= 5000) & (pl.col("vlm_month") >= 100_000)
                 & (pl.col("vlm_month") < 3e7) & (pl.col("pnl_allTime") > 0)
                 & (pl.col("vlm_allTime") >= 1e6) & (pl.col("vlm_allTime") < 5e8))["address"].to_list()
random.seed(7)
sample = random.sample(cand, N)


async def main():
    info = InfoClient(RateLimiter())
    ok = 0
    for a in sample:
        try:
            r = await vet_address(info, a, root)
        except Exception as e:  # noqa: BLE001
            print(a, "ERROR", repr(e)[:120], flush=True)
            continue
        rec = r["reconcile"]
        ok += bool(rec["ok"])
        print(a, f"fills={r['n_fills']} trips={r['n_round_trips']} ok={rec['ok']} "
              f"resid%={rec['residual_pct'] and round(rec['residual_pct'], 2)} "
              f"gaps={len(r['coins_with_gaps'])} trunc={r['history_truncated']}", flush=True)
    print(f"RECONCILE PASS {ok}/{N}")
    await info.aclose()

asyncio.run(main())
