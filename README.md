# hl-scout

Read-only Hyperliquid perp trader scanner. Full spec: [PROJECT_PLAN.md](PROJECT_PLAN.md). Research inputs: `docs/research/`.

## Status
| Phase | State |
|---|---|
| P0–P5 foundation, tape, universe, reconstruction, detectors, scoring, report | done, tested |
| P6 link graph, clusters, D-H1..H6, D-M7 | done (`hlscout links`; cluster-level re-judging uses PnL, not full re-scoring) |
| P7 archive | Hypedexer backfill + coarse months done (needs `HYPEDEXER_API_KEY`); S3 bulk path not built (needs AWS creds, bucket layout unverified) |
| P8 monitor, alerts, dashboard | done (`hlscout monitor`, Telegram via `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`) |
| P9 hardening | launchd plists, scheduler, health, backups done; 14-day unattended run NOT yet verified |
| P10 forward validation | `freeze` / `forward` done; needs 30-60 days of wall-clock time |

## Run
```
uv sync
uv run hlscout init
uv run hlscout universe            # leaderboard snapshot + S1 screen
uv run hlscout tape &              # 24/7 trade recorder
uv run hlscout worker &            # S2 -> deep vet queue (rate limited)
uv run hlscout score               # reports/latest.md
uv run hlscout links               # clusters; queues unhydrated members
uv run hlscout backfill            # archive pass for truncated wallets
uv run hlscout tracker             # live progress page, http://127.0.0.1:8765
uv run hlscout monitor             # watchlist + dashboard on 127.0.0.1:8765
uv run hlscout freeze              # then, weeks later: hlscout forward
uv run hlscout health
```
24/7: `uv run python scripts/make_launchd.py`, then follow the instructions in that script (not auto-installed).

## Known gaps
Deferred: D-C3 (needs per-coin OI/volume), D-C4 (ADL tags), G8 margin usage (leverage gate used instead). D-M3/M4 need the explorer action log (only recent history); D-C7 needs BTC marks loaded.
Manual-vs-algo weights unvalidated. Marks come from hourly candles. Arbitrum funder links (P6b) and S3 bulk backfill not built (optional / need credentials).
