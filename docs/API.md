# Read-only feed (local, 127.0.0.1:8765)

Started by `hlscout tracker` or `hlscout monitor`. JSON only, GET only, no authentication (bound to localhost).
Every payload carries `schema_version` (currently **1**). Fields may be added; existing fields are not renamed
within a version.

| Endpoint | Returns |
|---|---|
| `/api/watchlist` | `{count, wallets:[{address, tier: qualified\|provisional, category: MDT\|ADT\|UNSURE, score, p_algo, metrics{...}}]}` ordered by tier, category, score |
| `/api/wallet/<address>` | gate table (value / threshold / pass), detector findings with evidence, metrics, cluster {id, confidence, members} |
| `/api/events?since=<ms>&limit=<n>` | watch events (open/add/reduce/close/flip/liquidation/rescue_inflow/...) with `next_since` for polling |
| `/progress.json`, `/health` | pipeline progress and health |

The bot never signs or sends anything; a consumer decides what to do with the list. `tier = provisional` means the wallet is
integrity-clean but missed soft gates and is being forward-tracked, not proven.
