"""Position-continuity report: mid-history startPosition breaks per wallet (missing fills show up as breaks).

Usage: uv run python scripts/continuity.py [--stage reconcile_fail] [--limit N]
"""
import collections
import sqlite3
import sys
from pathlib import Path

import polars as pl

from hlscout.recon.roundtrips import _ordered_rows, perp_only

root = Path("data")
stage = sys.argv[sys.argv.index("--stage") + 1] if "--stage" in sys.argv else None
limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 10**9
con = sqlite3.connect(root / "state.sqlite")
if stage:
    addrs = list(dict.fromkeys(r[0] for r in con.execute(
        "select entity from scores where run_id='latest' and stage=?", (stage,))))
else:
    addrs = sorted(p.stem for p in (root / "raw" / "fills").glob("*.parquet"))
addrs = addrs[:limit]
tot = collections.Counter()
per = {}
for a in addrs:
    try:
        f = perp_only(pl.read_parquet(root / "raw" / "fills" / f"{a}.parquet"))
    except Exception:
        continue
    mid = first = 0
    for _, g in f.sort(["coin", "time", "tid"]).group_by("coin", maintain_order=True):
        pos, seen = 0.0, False
        for r in _ordered_rows(g):
            sp = r["start_position"]
            if sp is not None and abs(sp - pos) > max(1e-6, 1e-6 * abs(sp)):
                first += not seen
                mid += seen
                pos = sp
            seen = True
            pos += r["sz"] if r["side"] == "B" else -r["sz"]
    per[a] = mid
    tot["mid"] += mid
    tot["first"] += first
    tot["wallets"] += 1
    tot["wallets_with_mid"] += mid > 0
print(dict(tot))
print("top wallets by mid-history breaks:", sorted(per.items(), key=lambda x: -x[1])[:5])
