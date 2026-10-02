# Roadmap status (updated 2026-10-01)

| Phase | What | Status |
|---|---|---|
| P0-P2 | scaffold, rate limiter, tape recorder, leaderboard universe, S1 screen | done |
| P3 | ground-truth rebuild (round trips, TWR, reconcile) | done, 20/21 wallets reconcile within 2% |
| P4 | single-wallet detectors + algo classifier | done |
| P5 | monthly grading, DSR, gates, ranking, report, queue worker | done |
| P6 | link graph, clusters, multi-wallet detectors | done (cluster re-judging by PnL) |
| P7 | archive | Hypedexer backfill (credit-budgeted) done; S3 route dropped by owner decision |
| P8 | monitor, alerts, dashboard, live tracker | done |
| P9 | 24/7 hardening | code done; 14-day unattended run pending |
| P10 | forward validation | code done; needs 30-60 days after the first list |

Now running: stage-2 screen of 6,897 wallets (~49/min), then capped deep vets (top 400 by coarse score),
then `hlscout links`, `hlscout backfill` (finalists only), `hlscout score` -> reports/latest.md, `hlscout freeze`.

Full audit (2026-10-02) and the forward plan: [AUDIT_AND_PLAN.md](AUDIT_AND_PLAN.md).
