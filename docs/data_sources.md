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

## Measured 2026-10-02 (supersedes advertised claims)
* **Public Info API fill history is incomplete for older periods** even when it returns rows: for a heavy wallet Hypedexer counted
  23,108 fills in April 2025 against 1,201 from `userFillsByTime`. Recent windows agree within 0.3%, and for ordinary wallets older windows
  agree too (e.g. 761 vs 777 in May 2025). The bot detects the gap from position-continuity breaks (`reliable_since`), not from a fill count.
* **Hypedexer coverage** starts around Mar–Apr 2025 for the wallets probed (0 fills for Feb 2025), not Nov 2024. `total_count` with `limit=1`
  (about 2 credits) is a cheap completeness oracle for any window.
* `userTwapSliceFillsByTime` is required for TWAP fills and costs +1 weight per 20 rows like the other fill endpoints.
