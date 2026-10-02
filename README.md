# hl-scout

Read-only Hyperliquid perp trader scanner. Full spec: [PROJECT_PLAN.md](PROJECT_PLAN.md). Research inputs: `docs/research/`.

## Status
See [docs/ROADMAP_STATUS.md](docs/ROADMAP_STATUS.md) (phase-by-phase) and [docs/AUDIT_AND_PLAN.md](docs/AUDIT_AND_PLAN.md) (audit and plan).

## Run
```
uv sync
cp .env.example .env               # HYPEDEXER_API_KEY, optional TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
uv run hlscout init
uv run hlscout universe            # leaderboard snapshot + S1 screen   (--rescreen after changing thresholds)
uv run hlscout enqueue             # queue new S1 passes
uv run hlscout tape &              # 24/7 trade recorder
uv run hlscout worker &            # light screen -> quick pre-vet -> deep vet (shared rate limit)
uv run hlscout marks               # daily mark prices for every traded coin
uv run hlscout twap                # TWAP slice fills for hydrated wallets
uv run hlscout links               # clusters
uv run hlscout score               # reports/latest.md
uv run hlscout sensitivity         # reports/sensitivity.md
uv run hlscout dossier             # reports/dossiers/<address>.html
uv run hlscout backfill --dry-run  # archive credit plan (Hypedexer)
uv run hlscout tracker             # live progress + read-only JSON feed on 127.0.0.1:8765
uv run hlscout monitor             # watchlist polling + alerts
uv run hlscout freeze              # then, weeks later: hlscout forward
uv run hlscout health
```
24/7 setup: [docs/DEPLOY.md](docs/DEPLOY.md). JSON feed: [docs/API.md](docs/API.md).

## Known gaps
Deferred: D-C3 (needs per-coin OI/volume), D-C4 (ADL tags), margin usage (account-level daily leverage is used for G8). D-M3/M4 need the explorer action log (only recent history); D-C7 needs BTC marks loaded.
Manual-vs-algo weights unvalidated. Marks come from hourly candles. Arbitrum funder links (P6b) and S3 bulk backfill not built (optional / need credentials).
