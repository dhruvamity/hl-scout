# Bulk / archive data sources (from the Grok pass of 2026-10-01; verification noted)

Used in code now
- Info API weights: +1 per 20 rows (fills/funding/ledger), +1 per 60 candles (`candleSnapshot`) -> `clients/info.py`.
- Hypedexer free tier: 5,000 credits/month, REST = 1 credit/call + 1 per 25 rows (~125k rows/month) ->
  `archive/hypedexer.py` `CreditBudget` (default cap 4,500). Backfill is spent only on truncated wallets with no
  veto and a clean reconcile, best net PnL first (`archive/backfill.py`).

Not built (needs AWS account with billing; requester-pays egress ~ $0.09/GB, ~ $2-3 per month of fills)
1. `s3://hl-mainnet-node-data/` (`node_fills_by_block`, `node_fills`, `node_trades`, `replica_cmds`,
   `misc_events_by_block`): only documented source with fills + L1 actions + transfers/funding. Not per-user indexed.
2. Artemis `s3://artemis-hyperliquid-data/raw/`: node fills from 2025-08-17 with `user, fee, dir, close_pnl,
   liquidation` (maps 1:1 onto our FILL_SCHEMA). Filter `_metadata = true`. No ledger.
3. Hydromancer Reservoir `s3://hydromancer-reservoir/`: fills, 1s candles, daily account-value snapshots; field-level
   schema UNVERIFIED - open one sample parquet before coding a reader.
Decision needed from the owner: an AWS account for (1)-(3). Until then P7 is Hypedexer-only.

Notes: the "~10k fills" cap is a builder's observation, not documented; truncation is detected from data
(fills start long after first ledger activity), not assumed.
