# HL-Scout — Project Plan

**A 24/7 laptop bot that scans Hyperliquid perp wallets and keeps only traders with a real edge: consistent, disciplined intraday traders with 6+ months of record and no window dressing.**

| | |
|---|---|
| **As of** | 2026-10-01 |
| **Status** | Plan (no code yet) |
| **Mode** | **Read-only.** No private keys, agent wallets, builder-fee approvals or copy execution, ever |
| **Inputs** | [`docs/research/HL_trader_discovery_master.md`](docs/research/HL_trader_discovery_master.md) (the "compendium", cited below as `§n`) and [`docs/research/grok_results_compiled.json`](docs/research/grok_results_compiled.json) (Grok verification of 64 X posts, merged into compendium §14) |
| **Output** | Two ranked, explainable lists, **Manual Disciplined Traders** and **Algorithmic Disciplined Traders**, with every pass/fail reason, a watchlist monitored live, daily reports and alerts |
| **Decisions (2026-10-01)** | (1) Score each wallet's **entire history**, as far back as data exists. A longer genuine record ranks higher, but the record must be genuine **throughout**: a wallet that only "cleaned up" recently does not qualify (§7.0). (2) Algo traders are **tracked and ranked in their own category**, not excluded (§6.5, §8) |

> **What this bot can and cannot promise.** The best public study (935k wallets) found last month's top-10% stayed top-10% only **19%** of the time (R² 0.036, compendium §6.5). No filter can guarantee future profit, and some cheating (hedges on a CEX, funding from fresh CEX withdrawals) leaves no on-chain trace. The bot's job is to **remove every trader whose record is inflated, hedged, rescued or lucky**, and to hand over a short list that then has to prove itself in **forward tracking**. This is research tooling, not financial advice.

---

## Contents

1. [Goals, non-goals and definition of a qualified trader](#1-goals-non-goals-and-definition-of-a-qualified-trader)
2. [Resource inventory: every HL tool and its job in the bot](#2-resource-inventory-every-hl-tool-and-its-job-in-the-bot)
3. [System architecture](#3-system-architecture)
4. [Data acquisition layer (endpoints, budgets, limits)](#4-data-acquisition-layer)
5. [Ground-truth reconstruction (PnL, equity, positions)](#5-ground-truth-reconstruction)
6. [**Integrity detectors**: catching manipulation and illicit behaviour](#6-integrity-detectors)
7. [Consistency and discipline scoring (6+ months, intraday)](#7-consistency-and-discipline-scoring)
8. [Decision engine: gates, score, explanations](#8-decision-engine)
9. [Live watchlist monitoring and re-vetting](#9-live-watchlist-monitoring)
10. [Running 24/7 on a laptop](#10-running-247-on-a-laptop)
11. [Storage schema](#11-storage-schema)
12. [Repository layout and tech stack](#12-repository-layout-and-tech-stack)
13. [Phased roadmap with acceptance criteria](#13-phased-roadmap)
14. [Testing and calibration](#14-testing-and-calibration)
15. [Security guardrails](#15-security-guardrails)
16. [Risks, limitations and open questions](#16-risks-limitations-and-open-questions)
- [Appendix A: endpoint cheat-sheet](#appendix-a--endpoint-cheat-sheet)
- [Appendix B: ledger delta type → detector map](#appendix-b--ledger-delta-type--detector-map)
- [Appendix C: default config](#appendix-c--default-config-configyaml)
- [Appendix D: glossary](#appendix-d--glossary)

---

## 1. Goals, non-goals and definition of a qualified trader

### 1.1 Goals
1. **Scan continuously.** Cover the official leaderboard (~47k rows) **plus** every address that trades, captured from the public trade tape (~84k active addresses/day per the Hypedexer stats in compendium §14.4), including HIP-3 books.
2. **Rebuild the truth.** Recompute each wallet's PnL, equity and positions from raw fills, funding and the ledger. Never trust a leaderboard row or a vendor score (compendium §1 #3, §8.3).
3. **Detect manipulation** (§6): deposit-inflated numbers, rescue deposits, margin top-ups, martingaling, hedges across linked wallets, wash trading, sybil/rotation clusters, funding farming, lottery hits and more.
4. **Qualify consistency** (§7): regular, efficient, disciplined **intraday** trading over the **entire history** (minimum 6 months; a longer genuine record ranks higher, and it must be genuine throughout), with statistical significance after multiple-testing correction.
5. **Categorise** every qualified trader as **Manual Disciplined (MDT)** or **Algorithmic Disciplined (ADT)**, and track and rank both.
6. **Explain every verdict** with reason codes and evidence links (HypurrScan / Hyperdash / HyperX pages for human QA).
7. **Monitor the survivors live** and drop them automatically when behaviour changes.

### 1.2 Non-goals
- Placing, copying or signing trades (copy tools are listed only so they can be excluded; compendium §3.5).
- De-anonymising people beyond on-chain linkage (§15).
- Market-maker, vault or HFT research (classified and excluded, not studied).

### 1.3 Definition: "Qualified Intraday Trader" (QIT)
A wallet (or, correctly, a **wallet cluster**, §6.2) is a QIT only if **all** hard gates pass. Every QIT is then placed in a **category** (§6.5 D-B2):

| Category | Meaning | Ranked? |
|---|---|---|
| **MDT: Manual Disciplined Trader** | Passes all gates; behaviour looks human (routine hours, irregular timing, low order-spam, no API agent pattern) | Yes, own leaderboard |
| **ADT: Algorithmic Disciplined Trader** | Passes all gates; behaviour looks automated (bot fingerprint) but directional, not MM/HFT | Yes, own leaderboard |
| **UNSURE** | Passes all gates; classifier confidence < 0.7 | Listed under both, marked "unsure" until more data or QA |
| MM / HFT | Uncopyable inventory or high-frequency book (D-B1) | Tracked for reference, never ranked |

**History window:** the **entire available history** (§7.0). The 180-day figures below are the *minimum*; they are not the evaluation window. Gates G5–G9 and G11 are evaluated on the full history **and** on every rolling period inside it. Defaults below are configurable (Appendix C). The source of each number is tagged: `[C§x]` = compendium section, `[SYNTH]` = this plan's own synthesis, to be tuned during calibration.

| # | Gate | Default | Source |
|---|---|---|---|
| G1 | Track record | first perp fill ≥ **180 days** ago (minimum; longer ranks higher, §7.0), **and** active in ≥ 6 of the last 6 calendar months | user requirement |
| G1b | Genuine **throughout** | genuine coverage ≥ **90%** of active months across the whole history, no hard-veto event in **any** period, and the genuine record must start within the first **3 active months** (no "reformed recently" wallets, §7.0) | user requirement |
| G2 | Regularity | ≥ **60%** of weeks with ≥ 3 active trading days; no gap > 21 days in the last 180 | [SYNTH] |
| G3 | Intraday style | median hold **5 min – 8 h**; ≥ **70%** of round trips closed within 24 h | [C§6.1] hold-time rules + [SYNTH] |
| G4 | Not HFT/MM | avg hold ≥ 3 min; maker share < 80%; trades/day < 300; requests per fill below the configured bound | [C§6.2 HyperX], [C§4.1 Whale Street] |
| G5 | Real profitability | flow-adjusted (TWR) return > 0 **and** net PnL after fees and funding > 0 over the entire history **and** the last 180 days | [C§8.3] |
| G6 | Consistency | ≥ **4 of 6** months positive; no single month > **40%** of 180-day net PnL; top 5 trades < **35%** of net PnL | [C§6.1 concentration] + [SYNTH] |
| G7 | Drawdown | flow-adjusted max DD ≤ **30%** (aim < 15%) | [C§6.2] HyperX 50%, Niakris 22% / 15% |
| G8 | Leverage and margin | effective leverage (time-weighted) ≤ **10x**; p95 margin usage ≤ 80% | [C§6.2] HyperX 25x veto; Cipher 2–5x |
| G9 | Liquidations | **0** liquidations in the last 180 days and ≤ **1** in the entire history (configurable) | [C§10.2] 0x337afda, mk4_lul |
| G10 | Integrity | **no** hard-veto detector fired (§6) | this plan |
| G11 | Statistical edge | daily-return t-stat ≥ 2.0 **and** Deflated Sharpe probability ≥ 0.90 (correcting for the number of wallets scanned) | [SYNTH] |
| G12 | Size floor | median equity ≥ **$5k** (keeps ROI meaningful and avoids tiny-account ROI spikes) | [C§6.2] Minara $10k, relaxed |

Survivors of G1–G12 are then **ranked** by the composite score (§8.2). Rank only orders traders who already passed; it never rescues a gate failure.

---

## 2. Resource inventory: every HL tool and its job in the bot

Every resource found in the research is assigned one of: **INTEGRATE** (code talks to it), **ENRICH** (optional API add-on, budgeted), **QA** (human/Claude manual check, linked from reports), **IDEA** (concept re-implemented natively), **EXCLUDE** (execution/unsafe/off-scope, with reason).

### 2.1 Official Hyperliquid (the backbone)

| Resource | Role | Job in the bot |
|---|---|---|
| Leaderboard JSON `stats-data.hyperliquid.xyz/Mainnet/leaderboard` | INTEGRATE | Daily universe snapshot + day-over-day diff; board-vs-account check (§6.4 D-C1). ~39 MB, batch only |
| Info API `POST api.hyperliquid.xyz/info` | INTEGRATE | Ground truth: `portfolio`, `userFillsByTime`, `userFunding`, `userNonFundingLedgerUpdates`, `clearinghouseState`, `allDexsClearinghouseState`, `spotClearinghouseState`, `subAccounts`, `userRole`, `userRateLimit`, `historicalOrders`, `extraAgents`, `userToMultiSigSigners`, `borrowLendUserState`, `userVaultEquities`, `perpDexs`, `meta`, `marginTable`, `candleSnapshot`, `fundingHistory` (Appendix A) |
| WebSocket `wss://api.hyperliquid.xyz/ws` | INTEGRATE | (a) **Tape recorder**: `trades` on every coin incl. HIP-3. Each trade carries `users: [buyer, seller]`, so the whole venue's counterparties are recorded with **no** 10-user cap. (b) Watchlist user subscriptions (≤ 10 users/IP) |
| Explorer RPC `rpc.hyperliquid.xyz/explorer` (`userDetails`, `txDetails`) | INTEGRATE | Recent **L1 action log** per user: `updateIsolatedMargin`, `updateLeverage`, order/cancel actions. Needed for margin top-up detection (§6.1 D-M3). Weight ~40; recent history only |
| Official S3 `s3://hl-mainnet-node-data/` (`node_fills_by_block` from 2025-07-27), `s3://hyperliquid-archive/` | INTEGRATE (Phase 7) | Requester-pays, LZ4. Full-universe **historical fills with `closedPnl`, `dir`, `startPosition`** → 6–12-month backfill without the 10k-fill wall. Three schemas (compendium G2) |
| API docs (gitbook, append `.md`) | INTEGRATE | `scripts/check_docs.py` re-reads rate limits and schemas weekly and diffs them |
| HIP-3 `perpDexs` + `allDexs*` | INTEGRATE | So `xyz:`-prefixed books are never dropped (compendium G8); exclude backstop liquidator `0x4000…+dex_index` (G9) |
| Stats / ASXN HyperScreener | IDEA | Market-regime labels (trend/chop, funding regime) for alpha-vs-beta checks (§7.4) |

### 2.2 Trackers and explorers

| Resource | Role | Job |
|---|---|---|
| **HypurrScan** `hypurrscan.io/address/{a}#perps` | QA | Link in every report row; confirms vault/TWAP/spot tabs |
| **HyperTracker** (+ API `docs.coinmarketman.com`) | ENRICH | 100 free tokens/day: cross-check wallet age, style segment (scalper/day/swing), directional bias for top candidates only. "Money Printer" cohort ≠ skill |
| **CoinGlass HL** | QA | Liquidation map / crowded-side context for the watchlist |
| **Proliquid whales** | IDEA / discovery | Whale-liquidation feed → **negative list** seeds (blow-ups) |
| CoinClass, PerpFinder, Beacon, Isobath, Hypermonitor, Higher.money, HyperPulse, HyperStats | QA (watch) | Optional seed sources and sanity checks only; several are stale or inconsistent (compendium §3.2) |
| **Perpy** TG feed, **Mirrorly Live** | discovery | Parse `0x…` only (resolve nicknames first); never treat a card as a pass |
| Hyperfolio Pulse, Hypervisor | EXCLUDE | Coin tape only / no evidence |

### 2.3 Analytics and screeners

| Resource | Role | Job |
|---|---|---|
| **Hyperdash** `hyperdash.com/address/{a}` | QA | Cross-check style, Sharpe, max DD and the deposit/withdrawal panel. No bulk API: link only, no heavy scraping |
| **HyperX** wallet-discover / trader page | QA + IDEA | Its posted thresholds feed our defaults; its HFT/MM / direction-neutral tags are a cross-check. Distrust copy-fit = 100 (compendium N10) |
| **Hyperank** method | IDEA | Re-implemented: board-vs-account disagreement veto, and minimum copy capital from the $10 min order |
| **MinaraCN** 43,618-row method | IDEA | Stage-1 screen (§3.2) |
| **Bet or Book** | IDEA | Bet vs hedge vs inventory classifier → §6.2/§6.3 |
| **PerpPilot** | IDEA | Profit factor; "flock" signal (≥ 2 qualified traders same side within 15 min) in the monitor |
| **Exit Window** | IDEA | Exit-lag metric (seconds from a trader's first reduce to −1% adverse) in the monitor |
| **Whale Street** six checks | IDEA | Mapped 1:1 onto detectors: track record (G1), size (G12), human vs bot (§6.5), linked-wallet hedges (§6.2), concentration (G6), uniqueness (§6.5 D-B4 copier) |
| **Senpi leak scanner** | IDEA | Disposition-effect metric (holding losers longer, §6.3 D-S3) |
| **Liquary** momentum states | IDEA | accelerating / cooling / flat / crashed tag on the watchlist |
| LabelYX | QA | Calendar view sanity check |
| Dexly, Copin, HyperX copy, Hyperdash copy, Mirrorly copytrader, vault deposits | EXCLUDE | Execution / builder-fee approval |
| Cashboard, OpenCatz | EXCLUDE | Market widgets / generic bot |

### 2.4 Data, indexers and archives

| Resource | Role | Job |
|---|---|---|
| **Hypedexer** (REST/WS/MCP, fills since Nov 2024, round trips) | ENRICH | **Overflow history** for survivors with > 10k fills; free tier 5,000 credits/month → budgeted per candidate. MCP for Claude-assisted QA |
| **Hydromancer Reservoir** (daily parquet on S3, HIP-3 incl.) | INTEGRATE (Phase 7) | Preferred bulk backfill if its schema has per-user fills; compare against official S3 |
| **Dune** `hyperliquid.perp_accounts_daily` | ENRICH | Independent cross-check of daily `net_pnl_usd` for the final short list (catches bugs in our reconstruction) |
| Bitquery, Allium, Uniblock, SonarX, GoldRush, Dwellir | ENRICH (fallback) | Paid / non-rate-limited throughput if the public API budget is the bottleneck |
| 0xArchive | ENRICH | 1-minute candle history beyond the 5,000-candle cap (for rescue/martingale mark reconstruction) |
| Nansen (Smart HL Perps Trader label, perp screener) | ENRICH (optional, paid) | Extra label; label bias noted |
| **Arkham** | QA | Entity/cluster confirmation; source of **CEX hot-wallet labels** for the link-graph ignore list |
| DoubleZero Edge | EXCLUDE | Uncapped L4 only matters for MM reconstruction |

### 2.5 SDKs, MCPs and agent tooling

| Resource | Role | Job |
|---|---|---|
| Raw `httpx` + `websockets` (Python) | INTEGRATE | Primary client: full control over weight accounting |
| Official Python SDK (`Info` only) | INTEGRATE (optional) | Convenience; **never import `Exchange`** |
| nktkas/hyperliquid (TS) | reference | Most complete typed schemas (78 info methods); used to write our pydantic models |
| kitsune-de/hyperliquid-mcp, Hypedexer MCP | QA | Read-only MCPs for interactive Claude deep-dives on a flagged wallet |
| edkdev / Dakkshin / patricleehua / 0xikalgo MCPs, @liquidbots, Scarlett, Senpi execution suite | **EXCLUDE** | Take keys / place orders |
| `@2oolkit/hyperliquid-cli` 0.2.2 | **EXCLUDE (malicious, MAL-2026-3679)** | Silent `approveBuilderFee` |

### 2.6 People / X desks (discovery and negative calibration)
`@lookonchain`, `@OnchainLens`, `@EmberCN`, `@hypurrdash`, `@HyperTracker`, `@CryptHypoBuster`, `@Hyperbotai`: parse posted `0x` addresses into the **discovery queue** and the **blow-up list** (compendium §5, §10). There is no X API in the plan; ingestion is a manual paste or a periodic Grok export into `data/seeds/x_addresses.csv`. A viral card is never a pass.

---

## 3. System architecture

### 3.1 Big picture

```
                         ┌──────────────────────────── 24/7 LAPTOP ────────────────────────────┐
                         │                                                                      │
 WS trades (all coins) ──┼─► [T] Tape Recorder ──► parquet/tape/date=…/coin=…                   │
                         │        │  (buyer, seller, px, sz, time, tid)                         │
                         │        ▼                                                             │
 Leaderboard JSON ───────┼─► [U] Universe Builder ◄── seeds (X desks, Perpy, Proliquid, …)      │
                         │        │  address registry + daily per-address tape stats            │
                         │        ▼                                                             │
                         │  [S1] Cheap Screen (no per-user IO)                                  │
                         │        ▼                                                             │
 Info API (budgeted) ────┼─► [H] Hydrator ──► raw fills / funding / ledger / state / actions    │
 Explorer RPC ───────────┤        │      ▲                                                      │
 Hypedexer / S3 archive ─┼────────┘      └── overflow history when > 10k fills                  │
                         │        ▼                                                             │
                         │  [R] Reconstructor: positions, round trips, equity, flows, TWR       │
                         │        ▼                                                             │
                         │  [L] Link Graph: transfers, subaccounts, agents, tape co-trading     │
                         │        ▼                                                             │
                         │  [D] Integrity Detectors (§6) ──► flags + evidence                   │
                         │        ▼                                                             │
                         │  [Q] Consistency & Edge Scoring (§7)                                 │
                         │        ▼                                                             │
                         │  [E] Decision Engine (§8): gates → score → stage                     │
                         │        ▼                                                             │
 WS user subs (≤10) ─────┼─► [M] Watchlist Monitor (§9) ──► re-vet triggers                     │
 clearinghouseState poll ┤        ▼                                                             │
                         │  [O] Outputs: daily report, local dashboard, Telegram alerts         │
                         └──────────────────────────────────────────────────────────────────────┘
```

### 3.2 The funnel (why the laptop can afford it)

| Stage | Input | What happens | Cost per wallet | Expected out |
|---|---|---|---|---|
| **U** Universe | board ~47k + tape ~84k/day (cumulative 200k+) | Registry of every address seen | 0 (batch/stream) | all |
| **S1** Cheap screen | registry | Leaderboard + **tape-derived** stats: active days, trades/day, median inter-trade gap, maker share proxy, volume. Drop $0-volume holders, protocol/backstop addresses, known vaults, < 60 active tape days (once tape is ≥ 60 days old) | 0 | ~5–15k |
| **S2** Light hydrate | S1 survivors | `portfolio` (perp windows) + `userRole` + `clearinghouseState` → first-fill age proxy, perp equity history, flow-vs-PnL ratio, role (vault/agent/subAccount) | ~82 weight | ~2–5k |
| **H** Deep hydrate | S2 survivors | Full fills (paged), funding, ledger, subAccounts, historicalOrders, rate-limit stats, explorer actions, borrow state | ~1,000–1,300 weight | ~2–5k |
| **D/Q/E** | hydrated | Reconstruct + detectors + scoring (pure CPU, local) | CPU only | ~20–200 QIT |
| **M** Monitor | QIT + watch | Live; re-vet on triggers | low | — |

Budget math (public API, one IP, 1,200 weight/min ≈ **1.73M weight/day**): reserving 25% for the monitor leaves ~1.3M/day. That is about **1,000–1,300 deep vets/day**, or ~15k light hydrates/day. The whole leaderboard-derived candidate set clears in days. Afterwards the bot runs incrementally: only new addresses and changed wallets are re-pulled.

---

## 4. Data acquisition layer

### 4.1 Global rate limiter (single source of truth)
- A **token bucket in weight units**: 1,200/min, refill continuous, with headroom set to 90% of the cap.
- Each request declares its base weight. The row surcharge (+1 per 20 rows on `userFills*`, `userFunding`, `userNonFundingLedgerUpdates`, `historicalOrders`, `fundingHistory`, `recentTrades`, candles per the docs; **verify at run time**) is debited **after** the response from the actual row count.
- **Priority lanes:** `monitor` (25% reserved) > `deep_vet` > `light_hydrate` > `backfill`.
- On HTTP 429: exponential backoff with jitter, global pause, and the event is logged. The bot never retries in parallel.
- No IP rotation to dodge limits. If more throughput is needed, pay a non-rate-limited provider (§2.4).

### 4.2 Pagination recipes
| Data | Recipe |
|---|---|
| Fills | `userFillsByTime` with `aggregateByTime=false` (keeps scale-in clips visible, compendium G13). Page by `startTime = last.time + 1`, ≤ 2,000/call; stop when < 2,000 returned or the ~10k cap is reached → **mark `history_truncated=true`** and queue the overflow source (Hypedexer, else S3) |
| Funding | `userFunding` paged by time over the full window |
| Ledger | `userNonFundingLedgerUpdates` paged by time from first activity; it is small, so pull it **all** (critical for §6.1) |
| Orders | `historicalOrders` (≤ 2,000 most recent) for cancel/modify ratios and stop-loss usage (trigger orders, `reduceOnly`) |
| State | `clearinghouseState` + `allDexsClearinghouseState` + `spotClearinghouseState` |
| Hierarchy | `subAccounts(master)` → repeat everything per child; `userRole` resolves agent → master (never score an agent address, compendium G6); `extraAgents`; `userToMultiSigSigners` |
| Actions | Explorer `userDetails` → `updateIsolatedMargin`, `updateLeverage` history (recent only). The live monitor fills the gap going forward |
| Marks | `candleSnapshot` 1m/5m per coin, cached locally and shared by all wallets (5,000-candle cap → keep a rolling local store from day 1, or 0xArchive) |

### 4.3 Tape recorder (the laptop's main 24/7 job)
- One multiplexed WS connection. Subscribe `trades` for every perp coin from `meta`, plus every coin on each HIP-3 dex from `perpDexs` (coins prefixed `dex:COIN`). Spot is out of scope. Re-sync the coin list hourly (new listings, delistings, HIP-4 purges).
- Ping every 30 s (idle close at 60 s); auto-reconnect with backoff; on reconnect, gap-fill each coin from `recentTrades` and record the gap in `tape_gaps`.
- Write each trade once (dedupe on `tid`): `time, coin, px, sz, side, tid, hash, buyer, seller` → hourly Parquet files (zstd).
- A nightly job compacts each day into `addr_day_stats` (per address per day: trades, notional, buys/sells, coins, first/last time, median inter-trade gap, counterparties top-k), so raw tape can be kept for N days (default 120) to bound disk use.
- Size estimate: ~7–8M trades/day × ~40 B compressed ≈ **0.3–0.6 GB/day** raw. **Verify after day 1** and set retention.
- What the tape gives that nothing else does: (1) discovery of small intraday traders who are **not** on the leaderboard (inclusion needs ≥ $100k account value or ≥ $10M volume), (2) **who traded against whom** (wash trading, §6.2), (3) **simultaneous opposite trades** by different wallets (hidden hedges, §6.2), (4) **follower lag** (copiers, §6.5).

### 4.4 Historical backfill (the "archive mode", now **required**)
The public API holds only the ~10k most recent fills, and the tape only records from the day it starts. Scoring the **entire history** (§7.0) therefore makes archive mode a core component, not an option. It needs one or more of:
1. **Hypedexer** per wallet (cheap per wallet, credit-limited) for survivors whose `history_truncated=true`.
2. **Bulk S3** (`node_fills_by_block` official or Hydromancer Reservoir, plus the older `node_fills` / `node_trades` schemas for earlier dates): stream each day's file, keep only rows for candidate addresses (or all addresses, aggregated), discard raw. At roughly 0.5–1 GB/day compressed, 6 months is about 100–200 GB of transfer and the full history since launch several times that. Requester-pays egress is roughly **$10–20 per 6 months** of data; **verify** with `aws s3 ls --request-payer requester --summarize` before downloading. Process newest-first so the recent screen is ready early, then keep walking back in time in the background. This also gives the cheap screen (S1) months of history immediately instead of waiting for the tape to age.
3. **`portfolio` allTime** for periods older than any fill archive: coarse equity/PnL history used only as described in §7.0 point 8.

### 4.5 Arbitrum side (Phase 6b, optional)
HL USDC deposits arrive through the Arbitrum bridge contract (Bridge2, commonly cited as `0x2Df1c51E09aECF9cacB7bc98cB1742757f163dF7`; **verify**). The depositing EVM address is credited, and withdrawals go back out on Arbitrum. Pulling the USDC `Transfer` logs of a candidate's Arbitrum address (public RPC `eth_getLogs` or an Arbiscan free key) shows **who funded it**, giving cluster edges that never touch HL. Known CEX hot wallets (Arkham labels) go on an ignore list so "both withdrew from Binance" is not treated as a link.

---

## 5. Ground-truth reconstruction

All metrics are computed **perp-only**, from our own data. Vendor numbers are stored for comparison only.

### 5.1 Position and round-trip engine
- Replay fills in time order per `(address, coin)` (HL is **one-way** per coin per account: a hedge on the same coin requires another account or subaccount, which is why §6.2 matters).
- Use `startPosition` to seed and check continuity. Any jump means a missing fill → mark the coin's history incomplete.
- A **round trip** is flat → non-zero → flat. Record: open time, close time, hold, side, max |size|, number of adds and reduces, VWAP entry/exit, realized PnL (Σ `closedPnl`), fees (Σ `fee`, **already includes `builderFee`**, compendium G11), funding allocated over the hold, MAE/MFE from 1m candles, and whether any fill was a liquidation (`dir` contains "Liquidat" or `liquidation{}` present) or ADL.
- Keep TWAP slices (`twapId != null`) tagged; a TWAP-heavy book is not intraday discretionary.

### 5.2 Account equity and external flows
- **Equity series**: `portfolio` → `perpAllTime` / `perpMonth` `accountValueHistory` + `pnlHistory` (perp-only keys exist, so spot/HYPE holder gains stay out). Cross-check against our fill-based PnL + funding + flows.
- **External flow events** from the ledger (Appendix B): inflow = `deposit`, `internalTransfer`/`send`/`spotTransfer` received, `subAccountTransfer` in, `accountClassTransfer` spot→perp (`toPerp:true`), `vaultWithdraw`, borrow via `borrowLend`; outflow = the mirror set. **Non-trading income** (`rewardsClaim`, `vaultLeaderCommission`, `vaultDistribution`, staking) is never counted as trading PnL.
- **Borrowed capital** (manual borrows since 2026-09-18): `borrowLendUserState` is subtracted from "own trading equity" (compendium §9.1).

### 5.3 Flow-adjusted returns (the core anti-inflation tool)
For each day *t*: equity `E_t`, net external flow `F_t`, and Modified-Dietz daily return

```
r_t = (E_t − E_{t−1} − F_t) / (E_{t−1} + w_t · F_t)        # w_t = fraction of day the flow was present
TWR  = Π (1 + r_t) − 1                                       # deposits/withdrawals cannot move this
MaxDD_TWR, Sharpe/Sortino on r_t, Ulcer index on the TWR curve
```

A deposit raises `E_t` but not `r_t`. A trader who "grows" an account by depositing shows a flat TWR, so the bot reads the TWR curve and ignores the account value curve.

### 5.4 Reconciliation check (data-quality gate)
`|Σ closedPnl − Σ fee + Σ funding − ΔE_perp + ΣF| / max(E)` must be < 2% over the window. If not, the wallet is marked `reconcile_fail` and is **not scored** (bad data must never produce a pass). Common causes: missing subaccount, HIP-3 dex not queried, truncated fills, spot/perp class mix-up under unified margin (compendium G17).

---

## 6. Integrity detectors

Each detector returns `{code, severity: VETO | FLAG | INFO, score_penalty, evidence[]}`; evidence is timestamps, tx hashes and amounts, so every verdict can be audited by hand on HypurrScan. Thresholds are defaults for calibration (Appendix C).

### 6.1 Capital-flow manipulation ("adding money to look better or stay alive")

| Code | Behaviour | How it is detected | Default severity |
|---|---|---|---|
| **D-M1 Deposit inflation** | Equity/PnL optics driven by new money | `flow_share = Σ inflows / (E_end − E_start + Σ outflows)`; TWR vs naive ROI gap; inflows clustered right before leaderboard windows roll (monthly) | FLAG if flow_share > 0.5; VETO if naive ROI > 0 while TWR ≤ 0 |
| **D-M2 Rescue deposit** | Money added to avoid liquidation | At each inflow τ, reconstruct account state from positions × 1m mark: unrealized PnL / equity and **effective leverage vs the coin's max leverage** (`marginTable`). Rescue if pre-inflow uPnL ≤ −25% of equity **or** distance-to-liquidation < 10%, inflow ≥ 15% of equity, and no reduction of the losing position within ±60 min. Live mode uses exact `liquidationPx` / `marginSummary` from `clearinghouseState` polling | 1 event = FLAG; **≥ 2 in 180 d = VETO** |
| **D-M3 Isolated margin top-up** | `updateIsolatedMargin` adds while underwater | Explorer `userDetails` actions + the live monitor: isolated `marginUsed` ↑ with `szi` unchanged and `unrealizedPnl` < 0, or `liquidationPx` moving away without a size cut | same as D-M2 |
| **D-M4 Leverage-down rescue** | Lowering leverage on an isolated losing position to push liquidation away (adds margin) | `updateLeverage` action (or a `leverage.value` change between snapshots) during a drawdown with no size change | FLAG; counts toward the D-M2 VETO tally |
| **D-M5 Cross-class shuffles** | Spot→perp transfers (`accountClassTransfer`) or subaccount transfers to prop up a losing book | Same rescue logic applied to these deltas; subaccounts are scored as one book | as D-M2 |
| **D-M6 Borrowed buying power** | Trading on manual borrows | `borrowLendUserState` / `borrowLend` deltas; equity net of debt; leverage recomputed on own equity | FLAG; VETO if the debt-adjusted leverage gate fails |
| **D-M7 Loss parking / wallet rotation** | Losing wallet abandoned, fresh wallet starts "clean"; or losses parked in a subaccount | Link graph (§6.2): wallet A drains to B (or a shared funder) and B starts trading within 14 days → **merge histories** and score the cluster | VETO on the "clean" wallet if the merged record fails gates |
| **D-M8 Non-trading income dressing** | Rewards, vault commissions, referral income shown as "PnL" | Excluded by construction (§5.2); flagged if it is > 20% of the portfolio-reported PnL | INFO |

### 6.2 Multi-wallet games (hedging from another wallet, sybils, wash trades)

**Link graph.** Nodes are addresses. Edges, each with a type, weight and evidence:
1. **Hard links:** `subAccounts` parent/child; `userRole` agent→master; `extraAgents`; `userToMultiSigSigners`; vault leader↔vault.
2. **Transfer links:** ledger `internalTransfer`, `send`, `spotTransfer`, `subAccountTransfer` (each carries `user` and `destination`), vault deposits/withdrawals.
3. **Funding-source links** (Phase 6b): same Arbitrum funder (CEX hot wallets ignored).
4. **Behavioural links** from the tape: repeated **direct counterparty** trades; **opposite-side opens** on the same coin within Δt ≤ 60 s with notional within ±25%, ≥ 5 occurrences; position time series with correlation ≤ −0.8.

Connected components over hard + transfer links (behavioural links need ≥ 2 independent signals) form **clusters**. All scoring then happens at the cluster level (compendium N9: Lookonchain's 11 "new" wallets were one whale).

| Code | Behaviour | Detection | Severity |
|---|---|---|---|
| **D-H1 Cross-wallet hedge** | Showing the winning leg while a linked wallet holds the opposite leg | Per cluster, per coin, minute-level positions `p_i(t)`. `hedge_ratio = 1 − |Σ p_i| / Σ |p_i|`, notional-time weighted. A wallet whose cluster hedge_ratio > 0.3 is not a directional trader | **VETO** (score the net cluster book instead) |
| **D-H2 Pair/beta hedge inside one account** | Long BTC / short ETH-style books presented as directional | Rolling correlation of legs' PnL; net beta to BTC ≈ 0 with gross ≫ net | FLAG ("hedged style"); not illicit, but not the target style |
| **D-H3 Wash / self-trading** | Trading against yourself to farm volume, fees tiers, points or to paint PnL | Tape: share of a wallet's volume where the counterparty is in the same cluster; near-zero-PnL round trips at the same price within seconds; volume/equity extreme | **VETO** if same-cluster counterparty volume > 5% |
| **D-H4 Lottery portfolio (sybil survivorship)** | Many wallets funded together with different bets; only the winner is shown | Cluster has ≥ 3 wallets created within 14 days of each other from the same funder, with divergent outcomes → the winner is survivorship, not skill | **VETO** the winner unless the **cluster aggregate** passes |
| **D-H5 Unlinked hedge twin** | Hedge from a wallet with no transfer link | Behavioural edge (opposite opens ± 60 s, repeated) between a candidate and any address; investigated with Arkham/HypurrScan QA before acting | FLAG → VETO after QA confirm |
| **D-H6 Off-venue hedge (invisible)** | Short on a CEX, long on HL | Not observable. Proxies: positions persistently opposite to the funding sign with PnL dominated by funding; near-constant notional for weeks; PnL uncorrelated with price moves. Classified "likely basis/carry" | FLAG; excluded from QIT by G3/G6 in practice |

### 6.3 Risk-behaviour manipulation (looking disciplined without being disciplined)

| Code | Behaviour | Detection | Severity |
|---|---|---|---|
| **D-R1 Martingale / averaging down** | Adding to losers to pull the average entry closer | Per round trip: `underwater_add_share` = notional added at prices worse than the running VWAP entry / total added; `max_size_multiple` = max\|pos\| / first clip. Martingale if share > 0.5 and multiple ≥ 3 in > 10% of round trips | **VETO** if frequent; FLAG if occasional |
| **D-R2 No stop / bag-holding** | Losers held until they come back; realized stats look perfect | MAE distribution: losers' MAE ≫ winners'; ratio of median loser hold to median winner hold (> 3 = disposition); open positions with uPnL ≤ −20% of equity held > 3 days | FLAG; VETO if > 30% of equity is ever in a single zombie position |
| **D-R3 Win-rate farming (negative skew)** | Many tiny wins, rare huge losses | Payoff ratio, skew and tail ratio of trade returns; `max_loss / median_win`; CVaR 5%. High win rate with payoff < 0.3 and negative skew | FLAG; VETO if CVaR erases > 50% of mean edge |
| **D-R4 Liquidation habit** | Recklessness hidden by a few big wins | Count of liquidation fills / ledger `liquidation` entries, % of losses from liquidations | VETO per gate G9 |
| **D-R5 Leverage spikes** | Average leverage looks fine, but there are episodic 30–50x bursts | Time-weighted effective leverage distribution: p95 / p99, max; size relative to equity per trade (CV) | FLAG if p99 > 2× gate; VETO if p99 > 25x |
| **D-R6 Size inconsistency** | "Discipline" broken by revenge sizing after losses | Notional/equity after a losing trade vs after a winning trade (tilt ratio); size CV | FLAG if tilt ratio > 1.5 |
| **D-R7 Unrealized-loss hiding at window edges** | Avoiding realizing losses before month-end or leaderboard rolls | Realized-loss timing histogram vs calendar edges; month-end open uPnL vs realized | FLAG |

### 6.4 Statistical and optical manipulation

| Code | Behaviour | Detection | Severity |
|---|---|---|---|
| **D-C1 Board ≠ account** | Official 30d PnL green while the account's own 30d is flat/red | Compare the leaderboard row with the reconstruction (compendium: 1,935 wallets) | **VETO** |
| **D-C2 Lottery hit / concentration** | One trade, one coin or one month makes the record | Top-1 / top-5 trade share; top-coin share; best-month share (G6); Gini of trade PnL | VETO via G6 |
| **D-C3 Market-impact profits (manipulation)** | Profiting from moving thin markets (JELLY/oracle-style attacks), especially thin HIP-3 books | For each profitable round trip: the wallet's share of coin volume in the window, position notional vs coin OI and 24h volume, price impact around its fills. Profits where share-of-volume > 20% on low-liquidity coins | **VETO** if > 25% of PnL comes from such trades |
| **D-C4 ADL / liquidation windfalls** | PnL from auto-deleveraging or backstop fills | `dir`/`liquidation.method` tags; exclude ADL PnL from edge | INFO (excluded from PnL) |
| **D-C5 Funding farming as "trading"** | PnL mostly from funding | `|funding| / |realized directional|` > 0.5 with long holds | FLAG (fails G3 anyway) |
| **D-C6 Tiny-account ROI spikes** | +2,000,000% ROI on $50 | Size floor G12; ROI computed on max(own equity, $1k) | VETO via G12 |
| **D-C7 Beta masquerading as skill** | Long-only in a bull run | Daily-return regression on BTC (and the coin traded): alpha t-stat, beta; PnL in down-market weeks; long/short split | FLAG if alpha is not significant; feeds score |
| **D-C8 Event-window concentration** | Profits only around a few announcements (possible insider info) | PnL clustering in ≤ 3 short windows; entries shortly before large moves with no history in that coin. **Cannot prove intent**, so it is a flag only | FLAG for human QA |

### 6.5 Automation, copying and identity

| Code | Behaviour | Detection | Severity |
|---|---|---|---|
| **D-B1 HFT / market-maker** | Uncopyable inventory books | Avg hold < 3 min; maker share (`crossed=false`) > 80%; two-sided quoting; trades/day > 300; open legs > 5 | **VETO** (G4) |
| **D-B2 Manual vs algo categoriser** | Decides **MDT vs ADT** (never a veto) | Weighted evidence → `p_algo` 0–1: `userRateLimit.nRequestsUsed / fills` (order-spam ratio); cancel/modify ratio from `historicalOrders`; inter-trade timing regularity (low entropy, sub-second reactions); 24/7 activity with no daily sleep gap vs a stable human session window; `extraAgents` present; cloid usage; identical clip sizes; reaction time to price moves. `p_algo ≥ 0.7` → ADT, `≤ 0.3` → MDT, else UNSURE. Recomputed monthly so a switch in style is visible | CATEGORY (both tracked) |
| **D-B3 Vault / protocol / backstop** | Not a person's book | `userRole == vault`, HLP/vault addresses, `0x4000…+dex_index`, known system addresses | **VETO** |
| **D-B4 Copier** | Follows another wallet; the edge isn't theirs | Tape: ≥ 70% of opens within 5–120 s after the same-side open of one specific wallet | FLAG (score the leader instead) |
| **D-B5 Calibration blacklist** | Known MM/hedge/blow-up books | Compendium §10.3 addresses (Wintermute-labelled, Abraxas-labelled, Machi, Garrett-labelled, pension-usdt, Dexter's HFT example) | VETO (also used as tests) |
| **D-B6 TWAP-dominated** | Execution algos, not intraday decisions | Share of volume via TWAP slices > 40% | FLAG (fails G3) |

### 6.6 Severity policy
- Any **VETO** → stage `vet_fail` with reason codes.
- **FLAGs** subtract from the score (§8.2); ≥ 3 distinct FLAG families → `needs_qa` (the human/Claude-assisted review queue with pre-filled HypurrScan/Hyperdash links).
- Detectors run on the **cluster book** and on each member; a member can never pass if its cluster fails.

---

## 7. Consistency and discipline scoring

Computed on the **entire available history** of the cluster book, after detector exclusions, plus the same metrics per calendar month and per rolling 90-day period.

### 7.0 Full-history window and "genuine throughout"
**Goal:** the longer the genuine record, the better the trader. A record that only turned genuine recently counts for nothing extra.

1. **Segment the history** into calendar months (from first perp fill to today).
2. **Grade every month**: `genuine` if no VETO-class detector fires inside it (rescue, margin top-up, martingale, hedge, wash, liquidation, market impact…), the month's DD and leverage stay inside the gates, and data coverage is complete; `inactive` if fewer than the regularity threshold of active days; `violation` otherwise; `unknown` if data is missing.
3. **Genuine coverage** = genuine months / (active months − unknown months). Must be ≥ 0.90 (G1b).
4. **No late start:** if the first genuine run begins after the 3rd active month (early history full of violations, clean only lately), the wallet is labelled `reformed` and **not qualified**. It goes on a separate "reformed watch" list instead, so it can be revisited after its clean record is long on its own terms (configurable).
5. **Any hard VETO event anywhere in history** (e.g. a rescue deposit two years ago) → not qualified, under the default `history_violation_policy: strict`. A `lenient` mode allows violations older than N months to be forgiven, for experiments only.
6. **Genuine tenure** = number of genuine active months. It feeds the ranking with diminishing returns (`log(1 + months)`), so 36 months beats 12, and 12 beats 6, without letting age outweigh quality.
7. **Consistency throughout:** the edge must exist in each third of the history (early / middle / recent tercile each net-positive after costs) and the rolling 90-day TWR must be positive in ≥ 70% of windows. One great early year followed by a fade fails; so does a flat history with one recent hot run.
8. **Coverage honesty:** months before our archive coverage (S3 node fills from 2025-07-27, Hypedexer from Nov 2024, older `node_trades` schema further back) are graded from the coarser `portfolio` equity/PnL history + ledger flows only, tagged `coarse`. Coarse months can count toward tenure only if flows show no deposit inflation or rescues; they never count toward detectors that need fills.

### 7.1 Regularity ("trades regularly")
- Active days, active weeks, longest gap, **weekly activity coverage** (G2).
- Trades per active day: median and coefficient of variation (stable routine vs bursts).
- Months active (G1) and **monthly PnL table**: positive months, best-month share (G6).

### 7.2 Intraday-ness
- Hold-time distribution: median, IQR, % closed < 24 h (G3), % held overnight (relative to the trader's own active-hours profile).
- Session profile: entropy of the hour-of-day histogram (a human has a routine; a 24/7 flat profile suggests a bot, D-B2).

### 7.3 Efficiency and edge (after fees and funding)
| Metric | Notes |
|---|---|
| Net expectancy per trade (USD and bps of notional) | Must clear plausible copy costs (taker fee + builder fee ≤ 0.1% + slippage) to be "efficient" |
| Profit factor | Gross win / gross loss; no community cutoff exists (compendium §6.1). Default soft floor 1.3 |
| Payoff ratio and win rate | Read together; win rate is never used alone (compendium heuristic #10) |
| Sharpe, Sortino (daily TWR) | Annualised; default Sharpe soft floor 1.5 (Niakris) |
| Calmar, Recovery factor, Ulcer index | Recovery > 1000 = anomaly (HyperX) |
| % positive weeks / months | Consistency |
| **t-stat of mean daily return**, bootstrap p-value | G11 |
| **Deflated Sharpe Ratio** | Corrects for scanning N wallets: with 50k wallets, some will look brilliant by chance |

### 7.4 Discipline ("efficiently and disciplined")
| Metric | Good sign |
|---|---|
| Loss truncation: max loss / median loss; % of losers cut before MAE > 2× median MAE | Stops are honoured |
| Stop usage: share of round trips with a reduce-only trigger order (`historicalOrders`) | Pre-planned exits |
| Sizing stability: CV of notional/equity; tilt ratio (D-R6) | Same risk per trade |
| Leverage profile: time-weighted, p95 (G8, D-R5) | Moderate and stable |
| No martingale, no rescue, no zombie positions (§6) | — |
| Drawdown behaviour: does size shrink during DD? Time to recover | Risk-down in losing stretches ("drawdown first", compendium §4.1) |
| Regime robustness: positive in ≥ 2 of {up, down, chop} market regimes; alpha t-stat (D-C7) | Edge isn't beta |
| Persistence: walk-forward. Score months 1–4 and check months 5–6 hold up (no collapse) | Guards against the 19% persistence problem |

---

## 8. Decision engine

### 8.1 Stages
`discovered → screened_out | light_ok → deep_ok | reconcile_fail | vet_fail | reformed | needs_qa → qualified → watch → (forward_validated | dropped)`

Each `qualified` wallet also carries `category ∈ {MDT, ADT, UNSURE}` and `p_algo`. MM/HFT wallets get `category = MM_HFT` and stay at `vet_fail` (tracked, not ranked).

### 8.2 Composite score (only for wallets that passed every gate) `[SYNTH]`
Scores are computed **separately within each category** (MDT and ADT have their own leaderboards, so bots never crowd out humans). Each component is a **percentile rank** within the category's qualified set (robust to scale), then weighted:

| Component | Weight |
|---|---|
| **Genuine tenure** (`log(1 + genuine months)`, §7.0) | 20 |
| Statistical edge (DSR, t-stat, Sortino) | 20 |
| Consistency throughout (positive months, terciles, rolling-90d hit rate, best-month share) | 20 |
| Risk discipline (DD, loss truncation, leverage stability, sizing CV) | 15 |
| Efficiency (net expectancy bps after costs, profit factor) | 10 |
| Regularity (weekly coverage, routine stability) | 8 |
| Alpha vs beta / regime robustness | 7 |
| **Minus** FLAG penalties (default −5 each, −15 per FLAG family cap) | — |

Tie-break: longer genuine tenure first.

**Outputs per wallet:** stage, score, gate table (pass/fail + value + threshold), detector list with evidence, cluster members, data-completeness flags, and links (`hypurrscan.io/address/…`, `hyperdash.com/address/…`, `hyperx.trade/hyperliquid/trader?address=…`). Optional extra: **minimum copy capital** (Hyperank $10-ticket method).

### 8.3 Forward validation
A newly `qualified` wallet goes to `watch` and must stay within its own historical envelope (DD, leverage, hold time, trade frequency) for **30 days** (default) before it is labelled `forward_validated`. Paper-tracked PnL is shown next to the backtest numbers.

---

## 9. Live watchlist monitoring

- **Top 10 watch wallets**: WS user subscriptions (`userFills`, `userFundings`, `userNonFundingLedgerUpdates`, `allDexsClearinghouseState`); the first frame is `isSnapshot:true` and must be skipped for alerts.
- **The rest of the watchlist**: `clearinghouseState` (+ `allDexs…`) polling at 30–120 s, adaptive (faster when positions are open), within the monitor's 25% weight lane. ~600 calls/min is the theoretical ceiling; plan for ≤ 150/min.
- **Tape**: watch-wallet trades are already visible on the tape recorder in real time (no user-sub needed for fills).
- **Events** → `watch_events`: open / add / reduce / close / liquidation / deposit / withdraw / transfer / margin_update / leverage_change.
- **Immediate re-vet triggers** (from compendium §7.7 plus §6): any liquidation; a rescue-pattern inflow (D-M2/M3 live, which is precise here); DD breach vs the stored envelope; leverage > gate; new linked wallet; 7d PnL flip while 30d green (Liquary "crashed"); hold-time drift out of intraday band.
- **Signals for the user (read-only)**: flock (≥ 2 qualified traders same coin/side within 15 min, PerpPilot idea); exit lag (Exit Window idea).
- **Alerts**: Telegram bot (send-only, no trading commands) + local dashboard. Alert types: new qualified trader, watch-wallet trade, integrity flag tripped, wallet dropped, bot health problems.

---

## 10. Running 24/7 on a laptop

### 10.1 Hardware and OS
| Item | Minimum | Recommended |
|---|---|---|
| CPU / RAM | 4 cores / 8 GB | 8 cores / 16 GB |
| Free SSD | 100 GB (API mode, tape kept 120 days) | 500 GB+ (archive mode, §4.4) |
| Network | Stable broadband; HL REST/WS reachable | Wired/ethernet; UPS or battery for the laptop |
| OS | Linux, macOS or Windows (WSL2 fine) | Linux |

### 10.2 Process model
Three long-lived processes managed by a supervisor, plus scheduled jobs:

| Process | Job |
|---|---|
| `tape` | WS trades recorder (§4.3) |
| `worker` | Rate-limited queue consumer: light/deep hydrate, backfill, reconstruct, detect, score |
| `monitor` | Watchlist WS + polling + alerts |
| scheduler (inside `worker`) | 00:15 UTC leaderboard snapshot + diff; 00:30 tape daily compaction; hourly coin-list sync; 01:00 enqueue new/changed addresses; weekly full rescore + recluster + docs check; monthly calibration report |

### 10.3 Staying up
- **Supervisor**: `systemd` user services (Linux), `launchd` (macOS) or NSSM / Task Scheduler (Windows). Restart on failure, start on boot.
- **Prevent sleep**: `systemd-inhibit` / `caffeinate -s` / `powercfg /requestsoverride`; set lid-close to "do nothing" on AC power.
- **Crash safety**: every queue item is idempotent with checkpoints (`last_fill_time` per address, ledger cursor, tape hour files written atomically via temp+rename). SQLite in WAL mode for state.
- **Gaps are recorded, not hidden**: tape gaps and API outages go into `tape_gaps` / `ingest_gaps`, and affected days are marked incomplete for scoring.
- **Health**: heartbeat file + `/health` on the local dashboard; Telegram alert if the tape is silent > 2 min or the queue is stalled > 15 min; daily disk-usage check with automatic raw-tape pruning.
- **Thermals / battery**: CPU-heavy jobs (backfill, rescore) run at `nice` 10 and pause on battery < 30%.
- **Laptop-off fallback**: the same container image runs on a small VPS if needed; because state is files + SQLite, it can be moved with `rsync`.

---

## 11. Storage schema

Raw data in **Parquet** (append-only, partitioned by date), state and queue in **SQLite**, analytics in **DuckDB** (queries Parquet + SQLite directly).

| Table / dataset | Key fields |
|---|---|
| `tape/` (parquet) | date, hour, coin, tid, time, px, sz, side, buyer, seller, hash |
| `addr_day_stats` | address, date, trades, notional, coins, maker_share_proxy, first_ts, last_ts, median_gap_s, top_counterparties |
| `leaderboard_snapshots` | snap_date, address, account_value, pnl/roi/vlm × {day, week, month, allTime} |
| `addresses` | address, first_seen, sources[], role, master, is_vault, cluster_id, stage, last_hydrated, history_truncated, reconcile_ok |
| `fills/` (parquet) | address, coin, dex, time, px, sz, side, dir, start_position, closed_pnl, fee, builder_fee, crossed, oid, tid, twap_id, liquidation_method |
| `funding` | address, time, coin, usdc, szi, funding_rate |
| `ledger` | address, time, hash, type, usdc/amount/token, counterparty (user/destination), to_perp, fee, raw_json |
| `actions` | address, time, hash, action_type (updateIsolatedMargin, updateLeverage, …), payload |
| `state_snapshots` | address, ts, account_value, margin_used, withdrawable, positions_json, borrow_usd |
| `round_trips` | address, coin, open_ts, close_ts, side, max_size, adds, reduces, vwap_in, vwap_out, pnl, fees, funding, mae, mfe, liquidated, underwater_add_share |
| `daily_equity` | address/cluster, date, equity, net_flow, r_t, twr_index, dd |
| `links` | src, dst, edge_type, weight, first_ts, last_ts, evidence |
| `clusters` | cluster_id, members[], method, confidence |
| `detector_results` | entity, run_id, code, severity, penalty, evidence_json |
| `scores` | entity, run_id, gates_json, metrics_json, score, stage |
| `watch_events` | address, ts, event, coin, notional, source |
| `ingest_gaps`, `tape_gaps`, `runs` | operational audit |

---

## 12. Repository layout and tech stack

**Stack:** Python 3.12 · `asyncio` + `httpx` + `websockets` · `pydantic` v2 models (ported from nktkas schemas) · `polars` + `duckdb` + `pyarrow` · `sqlite3` (WAL) · `typer` CLI · `streamlit` (local dashboard) · `python-telegram-bot` (send-only) · `pytest` + `hypothesis` · `ruff` + `mypy` · `uv` for locked dependencies. Optional: `boto3` (S3 requester-pays), `web3`/raw JSON-RPC (Arbitrum).

```
hl-scout/
├── PROJECT_PLAN.md
├── docs/research/                  # compendium + Grok JSON (inputs to this plan)
├── config/config.yaml              # thresholds, budgets, paths (Appendix C)
├── data/                           # gitignored: parquet, sqlite, duckdb, seeds/
├── src/hlscout/
│   ├── clients/        info.py · ws.py · explorer.py · ratelimit.py · hypedexer.py · s3archive.py · arbitrum.py
│   ├── models/         pydantic schemas for every endpoint used
│   ├── ingest/         tape.py · leaderboard.py · hydrate.py · backfill.py · seeds.py
│   ├── recon/          positions.py · roundtrips.py · equity.py · reconcile.py · marks.py
│   ├── graph/          links.py · clusters.py · behavioural.py
│   ├── detectors/      flows.py (D-M*) · multiwallet.py (D-H*) · risk.py (D-R*) · optics.py (D-C*) · automation.py (D-B*)
│   ├── scoring/        consistency.py · edge.py · discipline.py · dsr.py · engine.py
│   ├── monitor/        watch.py · triggers.py · signals.py · alerts.py
│   ├── reports/        daily.py · dashboard.py
│   ├── scheduler.py
│   └── cli.py          hlscout tape | worker | monitor | vet <addr> | report | calibrate
├── tests/              unit/ (synthetic fixtures per detector) · calibration/ (compendium §10 addresses) · golden/
├── deploy/             systemd/ · launchd/ · windows/ · Dockerfile
└── scripts/            check_docs.py · disk_prune.py · export_seeds.py
```

`hlscout vet 0x…` runs the full pipeline on one address and prints the gate table and detector evidence. This is the main debugging and QA tool.

---

## 13. Phased roadmap

Estimates assume one developer working with Claude Code, part-time. Each phase ends with a demo and a passing acceptance test.

| Phase | Scope | Duration | Acceptance criteria |
|---|---|---|---|
| **P0 Foundations** | Repo, `uv`, config, logging, SQLite/Parquet/DuckDB plumbing, pydantic models, **weight-aware rate limiter** with tests | 3–4 days | Limiter never exceeds 1,080 weight/min under a load test; 429 handling tested with a mock server |
| **P1 Tape recorder** | WS trades for all perps + HIP-3 dexes, reconnect/gap-fill, hourly Parquet, daily `addr_day_stats` | 1 week | 72 h unattended run; gaps < 0.1% of minutes and all logged; dedupe on `tid` verified against `recentTrades` |
| **P2 Universe + cheap screen** | Leaderboard snapshot/diff, seeds import, S1 rules (MinaraCN + tape stats), registry | 3–4 days | Daily universe built; S1 output count and drop reasons logged |
| **P3 Hydrator + reconstruction** | All Appendix A calls, pagination, subaccounts, agent→master, truncation flags; position/round-trip engine; flows; TWR; reconciliation gate | 1.5–2 weeks | `hlscout vet` reproduces `portfolio` perp PnL within 2% on 20 random wallets; `reconcile_fail` rate reported |
| **P4 Integrity detectors** | D-M*, D-R*, D-C*, D-B* (single-wallet detectors) with evidence output | 2 weeks | Every detector has ≥ 3 synthetic positive and negative fixtures; calibration negatives (§14.2) fail for the right reasons |
| **P5 Consistency + decision engine** | §7 metrics incl. monthly grading, genuine coverage/tenure, terciles; DSR, walk-forward, gates, MDT/ADT categoriser, per-category scores, stages, daily Markdown report | 1–1.5 weeks | First end-to-end daily report with ≥ 1,000 deep-vetted wallets, two category leaderboards and explanations; synthetic "reformed recently" wallet is labelled `reformed` |
| **P6 Link graph + multi-wallet detectors** | Ledger/hard links, clustering, cluster-level books, D-H1–D-H5 from tape | 1.5 weeks | Cluster-level re-scoring works; a synthetic hedge pair and wash pair are caught; the Lookonchain-style rotation class is merged |
| **P6b Arbitrum funding links** (optional) | Bridge deposits, USDC funder edges, CEX ignore list | 4–5 days | Funder edges added with confidence scores |
| **P7 Archive mode (required)** | Hypedexer overflow; S3/Hydromancer backfill walking back to launch (newest first); all three S3 schemas; coarse-month grading from `portfolio` | 1.5–2 weeks | `history_truncated` wallets fully reconstructed; every month of every candidate graded fill-level or `coarse`; backfill cost logged and within budget |
| **P8 Monitor + alerts + dashboard** | WS/poll watchlist, triggers, live rescue detection, flock/exit-lag, Telegram, Streamlit | 1 week | Simulated liquidation/rescue triggers a drop within one poll cycle; alerts delivered |
| **P9 24/7 hardening** | Services, sleep inhibit, health checks, pruning, backups, docs-drift check | 3–4 days | 14-day unattended run with no manual intervention |
| **P10 Forward validation** | 30–60 days of watch; compare live vs backtest envelopes; tune thresholds | ongoing | Calibration report: drop reasons, false-positive review of ≥ 30 `needs_qa` cases |

**Milestones:** M1 (end P3): truthful single-wallet audit. M2 (end P5): first qualified list. M3 (end P6): cluster-aware list, the first one to trust. M4 (end P8): live system. M5 (end P10): forward-validated list.

---

## 14. Testing and calibration

### 14.1 Unit and property tests
- Rate limiter, pagination cursors, dedupe, schema parsing for the three S3 fill schemas.
- Position engine: property tests (random fill streams → position never jumps; Σ realized + open uPnL = mark-to-market PnL).
- TWR: deposits/withdrawals with zero trading must give TWR = 0 exactly.
- Each detector: hand-built synthetic wallets (a martingaler, a rescuer, a hedged pair, a wash pair, a lottery-hit trader, an MM book, a clean intraday trader) as golden fixtures.

### 14.2 Calibration set (compendium §10). The scorer must:
| Address (label is a public claim) | Expected verdict | Expected reason |
|---|---|---|
| `0xecb63caa…2b00` (Wintermute-labelled) | vet_fail | D-B1 MM/two-sided, D-H6 |
| `0x5b5d5120…c060` + `0xb83de012…6e36` (Abraxas-labelled) | vet_fail | D-H6 carry/hedge, G7 DD |
| `0x92ea19EC…50e9` (Garrett-labelled) | vet_fail | G5/G6 (net loss over window), G8 |
| `0x0ddf9bae…a902` (pension-usdt) | vet_fail | G9 liquidation, D-R5 |
| `0x020ca66c…5872` (Machi) | vet_fail | G5 lifetime loss, G8 40x |
| `0xb7e0b9fb…d1aa` (Dexter example) | vet_fail | G1 < 6 months, D-B1 HFT/MM, G8 25x |
| `0x337afda1…7a06` | vet_fail | G9 (7 liqs), G1/G6 (profit almost all recent) |
| `0x77375a8c…bf66` (mk4_lul) | vet_fail | G9 (25 liqs) |
| `0xbf732ea0…5d58` | not qualified | G1 short public record, D-R5 40x clips |
| `0x3b11267d…8112`, `0xe6503009…f1a9` | evaluate | Must be re-pulled; no pre-judged outcome |
| Class tests | — | Board-green/account-red → D-C1; $0-volume rows → S1 drop; 11-wallet rotation pattern → one cluster |

### 14.3 Ongoing quality loop
- Weekly: random sample of 20 `vet_fail` and all `qualified` wallets → Claude-assisted QA using the read-only MCPs (kitsune-de / Hypedexer) and HypurrScan/Hyperdash; disagreements become new fixtures.
- Monthly: threshold sensitivity report (how many QITs each gate removes; whether a 10% change flips results).
- Cross-check the final list against Dune `perp_accounts_daily` net PnL (independent source).

---

## 15. Security guardrails
1. **Read-only, forever.** No private keys, seed phrases, API/agent wallets or builder-fee approvals anywhere in the repo or config. CI greps for `Exchange(`, `private_key`, `approveBuilderFee` and fails the build.
2. **Host allowlist:** `api.hyperliquid.xyz`, `wss://api.hyperliquid.xyz/ws`, `stats-data.hyperliquid.xyz`, `rpc.hyperliquid.xyz`, plus explicitly configured third parties. Never follow links from search ads or X "claim" posts (compendium §9.3, §11).
3. **Dependencies:** locked with hashes (`uv.lock`); no unsigned "Hyperliquid MCP/CLI" packages; `@2oolkit/hyperliquid-cli` is banned.
4. **Secrets** (Telegram token, optional API keys) live in `.env`, are gitignored, and are never logged.
5. **Ethics/privacy:** link analysis stays on-chain; no off-chain identity attribution. Labels from analysts are stored as `claim`, never as fact. The tool does not publish wallet lists publicly by default.

---

## 16. Risks, limitations and open questions

| Risk / limitation | Impact | Mitigation |
|---|---|---|
| Persistence is weak even for genuine traders (R² 0.036) | High | Gates on risk behaviour, DSR, walk-forward, mandatory forward validation; communicate as watchlist, not guarantee |
| Off-venue hedges and CEX-funded sybils are invisible | High | Proxies (D-H6, behavioural links, Arbitrum funders); conservative style gates; QA queue |
| 10k-fill API cap hides older history | High for active intraday traders | Hypedexer overflow; S3 archive mode (P7); never score a truncated history as complete |
| Public API rate limit (1,200 weight/min/IP) | Medium | Funnel design; incremental updates; optional paid non-rate-limited provider |
| Tape only covers time since start | Medium | S3 backfill; tape-based screens activate after 60 days |
| Rescue detection on history needs mark/liq reconstruction | Medium | 1m candle store; maintenance-margin table; exact in live mode |
| Laptop downtime (sleep, updates, travel) | Medium | Gap logging, gap-fill, VPS fallback, idempotent jobs |
| Schema/protocol drift (HIP-3, HIP-4, borrows changed things within 90 days) | Medium | Weekly docs-diff job; pydantic strict parsing alerts on unknown fields |
| Third-party tools vanish (hackathon projects) | Low | Concepts re-implemented natively; no runtime dependency on them |
| Thresholds conflict across sources (DD 15/22/50%) | Low | Config-driven; sensitivity reports; calibration |

**Open questions to settle during P0–P3 (verify against live docs):**
1. Exact weights and row surcharges for `userFunding`, `userNonFundingLedgerUpdates`, `historicalOrders`, explorer `userDetails`, and their per-call row caps.
2. How far back explorer `userDetails` goes; whether S3 node data includes the action log (for historical `updateIsolatedMargin`/`updateLeverage`) and ledger events.
3. Hydromancer Reservoir per-user fill schema and real daily size vs official `node_fills_by_block`.
4. Bridge2 contract address and whether deposit ledger entries expose the Arbitrum tx hash.
5. Final "intraday" band: 5 min–8 h median hold (default) vs a stricter 15 min–4 h.
6. Calibrate the MDT/ADT classifier: label ~50 wallets by hand (Claude-assisted QA) and tune feature weights until agreement ≥ 85%.

**Settled:** algo traders are tracked and ranked as ADT (not excluded); the window is the entire history, with tenure rewarded and genuineness required throughout (§7.0).

---

## Appendix A — Endpoint cheat-sheet

All `POST https://api.hyperliquid.xyz/info` with `{"type": …}` unless noted. Weights are from the compendium §8.1; **re-verify at run time**.

| type | Params | Used for | Weight (approx.) |
|---|---|---|---|
| `clearinghouseState` | user, dex | Positions, liqPx, leverage, marginSummary | 2 |
| `allDexsClearinghouseState` | user | Same across HIP-3 dexes | verify |
| `spotClearinghouseState` | user | Spot/unified balances (G17) | 2 |
| `portfolio` | user | accountValueHistory, pnlHistory, vlm for day/week/month/allTime + perp* variants | 20 |
| `userFillsByTime` | user, startTime, endTime, aggregateByTime | Fills (≤ 2k/call, ~10k most recent) | 20 + 1/20 rows |
| `userFills` | user | Most recent 2k fills | 20 + 1/20 rows |
| `userFunding` | user, startTime, endTime | Funding payments | 20 + rows (verify) |
| `userNonFundingLedgerUpdates` | user, startTime, endTime | Deposits, withdrawals, transfers (with counterparties), liquidations, vault flows, borrows | 20 + rows (verify) |
| `historicalOrders` | user | ≤ 2k recent orders: cancels, triggers, reduce-only | 20 + rows |
| `subAccounts` | user | Child accounts | 20 |
| `userRole` | user | user / agent (→ master) / vault / subAccount (→ master) / missing | 60 |
| `extraAgents` | user | Approved API/agent wallets (bot signal) | 20 |
| `userToMultiSigSigners` | user | Multisig signers (hard links) | 20 |
| `userRateLimit` | user | cumVlm, nRequestsUsed, nRequestsCap (bot fingerprint) | 20 |
| `borrowLendUserState`, `userBorrowLendInterest` | user | Manual-borrow debt | 20 |
| `userVaultEquities`, `vaultDetails` | user / vaultAddress | Vault exposure (kept separate) | 20 |
| `userTwapSliceFillsByTime`, `twapHistory` | user | TWAP share | 20 |
| `meta`, `perpDexs`, `marginTable`, `metaAndAssetCtxs` | dex | Coin list, HIP-3 dexes, maintenance margin tiers, OI | 20 |
| `candleSnapshot` | req{coin, interval, startTime, endTime} | Marks for MAE/MFE/rescue (5k-candle cap) | 20 + rows |
| `fundingHistory` | coin, startTime | Funding regime | 20 + rows |
| `recentTrades` | coin | Tape gap-fill | 20 + rows |
| Explorer `userDetails` (`rpc.hyperliquid.xyz/explorer`) | user | L1 actions incl. margin/leverage updates | ~40 |
| WS `trades` | coin | Tape with `users:[buyer, seller]` | sub (≤ 1,000 subs/IP) |
| WS `userFills`, `userFundings`, `userNonFundingLedgerUpdates`, `allDexsClearinghouseState` | user | Watchlist (≤ 10 users/IP) | sub |
| GET `stats-data.hyperliquid.xyz/Mainnet/leaderboard` | — | Universe snapshot | n/a |

## Appendix B — Ledger delta type → detector map

Types confirmed from the `userNonFundingLedgerUpdates` schema (nktkas/hyperliquid, Oct 2026):

| Delta `type` | Fields of interest | Detectors |
|---|---|---|
| `deposit` | usdc | D-M1, D-M2 |
| `withdraw` | usdc, fee, nonce | D-M1, D-M7 |
| `internalTransfer` | usdc, **user, destination**, fee | D-M1/M2/M7, link graph, D-H1/H4 |
| `send` | token, amount, usdcValue, **user, destination**, sourceDex, destinationDex | same as above |
| `spotTransfer` | token, amount, usdcValue, **user, destination** | same as above |
| `subAccountTransfer` | usdc, **user, destination** | D-M5, hard links |
| `accountClassTransfer` | usdc, toPerp | D-M5 (spot→perp rescue) |
| `liquidation` | liquidatedNtlPos, accountValue, leverageType, liquidatedPositions[] | D-R4, G9 |
| `vaultCreate` / `vaultDeposit` / `vaultWithdraw` / `vaultDistribution` / `vaultLeaderCommission` | vault, usdc, requestedUsd, commission, basis | D-B3, D-M8, links |
| `borrowLend` | token, amount, interest | D-M6 |
| `rewardsClaim`, `cStakingTransfer`, `spotGenesis`, `deployGasAuction`, `activateDexAbstraction` | — | D-M8 (excluded from trading PnL) |

## Appendix C — Default config (`config.yaml`)

```yaml
window: full_history               # evaluate everything available; 180 d is only the minimum
history:
  violation_policy: strict          # strict = any hard veto anywhere disqualifies; lenient = forgive older than forgive_after_months
  forgive_after_months: 24          # used only when lenient
  genuine_coverage_min: 0.90
  genuine_start_max_month: 3        # genuine run must start within first N active months
  rolling90_positive_min: 0.70
  terciles_all_positive: true
  coarse_months_count_for_tenure: true
categories:
  algo_p_threshold: 0.70            # >= ADT
  manual_p_threshold: 0.30          # <= MDT; between = UNSURE
  rank_separately: true
api:
  weight_per_min: 1200
  headroom: 0.90
  lanes: {monitor: 0.25, deep_vet: 0.50, light_hydrate: 0.15, backfill: 0.10}
tape:
  retain_raw_days: 120
  ping_s: 30
gates:
  min_track_days: 180
  min_active_months_of_last6: 6
  weekly_coverage_min: 0.60        # weeks with >= 3 active days
  max_gap_days: 21
  hold_median_min_s: 300
  hold_median_max_s: 28800
  intraday_close_share_min: 0.70
  hft_avg_hold_min_s: 180
  maker_share_max: 0.80
  trades_per_day_max: 300
  positive_months_min_of6: 4
  best_month_share_max: 0.40
  top5_trades_share_max: 0.35
  max_dd_twr: 0.30
  eff_leverage_tw_max: 10
  margin_usage_p95_max: 0.80
  liquidations_window_max: 0
  tstat_min: 2.0
  dsr_prob_min: 0.90
  median_equity_min_usd: 5000
detectors:
  rescue: {upnl_eq_max: -0.25, dist_to_liq_max: 0.10, inflow_eq_min: 0.15, window_min: 60, veto_count: 2}
  deposit_inflation_flag: 0.5
  hedge_ratio_veto: 0.30
  wash_same_cluster_vol_veto: 0.05
  martingale: {underwater_add_share: 0.5, size_multiple: 3, freq_veto: 0.10}
  market_impact: {vol_share: 0.20, pnl_share_veto: 0.25}
  behavioural_link: {dt_s: 60, notional_tol: 0.25, min_events: 5}
  copier: {lag_min_s: 5, lag_max_s: 120, share: 0.70}
scoring:
  weights: {tenure: 20, edge: 20, consistency: 20, discipline: 15, efficiency: 10, regularity: 8, alpha: 7}
  flag_penalty: 5
forward_validation_days: 30
alerts:
  telegram: {enabled: false}
```

## Appendix D — Glossary
**TWR**: time-weighted return; removes the effect of deposits and withdrawals. **Modified Dietz**: daily return formula that weights flows by time present. **DSR**: Deflated Sharpe Ratio; probability a Sharpe is real after accounting for the number of strategies/wallets tried. **MAE/MFE**: maximum adverse/favourable excursion during a trade. **Round trip**: flat → position → flat on one coin. **Cluster**: set of addresses judged to be one book (hard/transfer/behavioural links). **Rescue deposit**: inflow made while a position is near liquidation instead of cutting it. **Martingale**: adding size to a losing position. **HIP-3**: builder-deployed perp dexes (coins prefixed `dex:`). **ADL**: auto-deleveraging. **QIT**: Qualified Intraday Trader (§1.3). **MDT / ADT**: Manual / Algorithmic Disciplined Trader, the two ranked categories. **Genuine tenure**: number of active months graded genuine (§7.0). **Reformed**: wallet whose early history has violations and only recent history is clean; tracked separately, not qualified.
