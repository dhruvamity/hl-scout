# Hyperliquid Perp-Trader Discovery — Master Research Compendium

**As of:** 2026-10-01 (incl. Grok verification pass) · **Purpose:** hand to an AI agent that finds, vets and monitors genuinely skilled Hyperliquid (HL) perp traders · **Compiled from:** one raw agent research file (~2,800 lines, 7 research passes over X/CT plus linked pages)

> This file merges, de-duplicates and cross-checks everything in the raw research. Every claim carries a provenance tag so the consuming agent knows how much to trust it. Anything the raw file only *pointed at* (bare tweet links, truncated addresses, unopened articles) was sent to Grok (which can read X directly); the verified results are merged in [Section 14](#14-grok-follow-up-results-verification-of-vague-and-rule-bearing-posts). Items Grok could not retrieve or find are listed in §14.7.

## Contents
1. [Executive summary](#1-executive-summary) · 2. [Evidence base](#2-evidence-base-and-how-reliable-it-is)
3. [Tool and resource registry](#3-tool-and-resource-registry) — official · trackers · analytics/screeners · data/indexers · SDKs/MCPs · excluded leads
4. [Guides, articles, studies](#4-guides-articles-and-studies) · 5. [People and accounts](#5-people-and-accounts)
6. [Metrics and screening criteria](#6-metrics-and-screening-criteria) (every stated threshold)
7. [Agent architecture](#7-agent-architecture-schema-request-graph-screenvet-rules) · 8. [Data mechanics and API gotchas](#8-data-mechanics-and-api-gotchas)
9. [Last 90 days](#9-what-changed-in-the-last-90-days-2026-07-01--2026-10-01) · 10. [Calibration addresses](#10-calibration-set--public-addresses-every-row-is-a-claim-verify-on-chain)
11. [Security guardrails](#11-security-and-scope-guardrails-hard-rules-for-the-agent) · 12. [Audit of first-pass top 15](#12-audit-of-the-first-pass-top-15-liveness-and-trust)
13. [Discrepancies found](#13-discrepancies-ambiguities-and-corrections-found-while-compiling) · 14. [Grok follow-up results](#14-grok-follow-up-results-verification-of-vague-and-rule-bearing-posts) · 15. [Gaps](#15-gaps--searched-and-not-found-or-too-weak)
Appendices: A X registry · B non-X links · C addresses · D glossary

---

## 0. How to read this file

### Provenance tags (used throughout)

| Tag | Meaning |
|---|---|
| **[X]** | Found through an X post; post is listed in [Appendix A](#appendix-a--x-source-registry-101-links) |
| **[WEB]** | Found on a web page/docs only (not an X-native source). Kept because the raw agent used it to verify X-found tools |
| **[VENDOR]** | A number or score the tool's own vendor computes. Treat as a hint, never as proof of skill |
| **[CLAIM]** | An analyst or account's statement (address attribution, PnL). Must be re-verified on-chain |
| **[SYNTH]** | Synthesis by the research agent (not a rule anyone posted). Treat as a starting heuristic |
| **[DOCS]** | Official Hyperliquid or vendor documentation |

### Scope rule that governs everything below
The agent is **read-only**. No agent wallets, no builder-fee approvals, no private keys, no MCP/CLI that signs. Copy/execution products appear here only to be *classified and excluded*.

---

## 1. Executive summary

**Goal:** find skilled, *copyable or at least understandable* HL perp traders — not the biggest PnL.

**The ten conclusions the research converges on**

1. **Never rank on raw or short-window PnL.** A study of ~935k wallets over one year found last month's top-10% stayed top-10% next month only **19%** of the time (R² of historic vs future success **0.036**). `[X: @chase_mew_]`
2. **Official leaderboard = discovery only.** It holds ~47k accounts (1D/7D/30D/all-time PnL, ROI, volume). Many top-PnL rows have **$0 volume** (holders, not traders): on 2026-09-30, 8 of the top 10 by 30d PnL had $0 30d volume. `[WEB: Cipher]`
3. **Board ≠ account.** 1,935 wallets show a green official 30d PnL while their own fill-derived 30d PnL is flat/negative. Always rebuild PnL from fills + funding + ledger. `[X: @hypeRankio]` `[VENDOR]`
4. **Public `/info` is not an archive.** `userFills` returns ≤2,000 rows; only the ~10,000 most recent fills exist. Long-horizon scoring needs an indexer (Hypedexer, Dune, Bitquery, Allium, Hydromancer) or the requester-pays S3 archive.
5. **Size ≠ skill.** The longest-lived, loudest green books (Wintermute-labelled, Abraxas-labelled) are market-making / hedge / basis books — uncopyable as directional signals.
6. **Reject uncopyable styles:** HFT/MM (avg hold < 3 min, hundreds of trades/day, many open legs), one leg of a delta-neutral multi-venue book, vaults (unless intentionally studying vaults), linked-wallet clusters scored as separate traders.
7. **Read drawdown and leverage first**, win rate last. A +$8.57M BTC book ran at **35% win rate**; 100%-WR rows with 12–52 trades are concentration luck.
8. **Copyability is separate from skill:** HL $10 minimum order (median minimum copy capital ≈ $386), builder fees, exit lag (one measured smart-money exit left **67 seconds** before price moved −1%).
9. **2026 protocol changes broke older methods:** manual borrows (2026-09-18), HIP-3 books (need `dex`/`allDexs*` calls), HIP-4 markets purged after settle, backstop liquidator addresses `0x4000…`.
10. **Practitioner consensus:** *filter out uncopyable books, then follow a specialist through a losing stretch* — rather than "find the #1 PnL wallet."

**Minimum viable stack**

| Layer | Use |
|---|---|
| Discover | Official leaderboard JSON; Hyperdash Explore; HyperX wallet-discover; HyperTracker leaderboards API; X ingest (0x + HypurrScan links from `@lookonchain`, `@OnchainLens`, `@EmberCN`, `@hypurrdash`) |
| Hydrate / ground truth | Official `/info` + WS (`clearinghouseState`, `allDexsClearinghouseState`, `portfolio`, `userFillsByTime`, `userFunding`, `subAccounts`, ledger WS) + an indexer for fills beyond 10k |
| Human QA | HypurrScan address page (perps, TWAP, vaults, spot) |
| Classify | HyperTracker / Hyperdash style, Bet-or-Book, Hyperank fill audit, Arkham (clusters only) |
| Monitor | WS (≤10 user subscriptions/IP) + `clearinghouseState` polling + HyperTracker / Proliquid / CoinGlass position deltas |

---

## 2. Evidence base and how reliable it is

The raw file contains seven research passes. Only the first three are discovery; the rest are calibration and audit.

| Pass | Content | Notes |
|---|---|---|
| 1 | Core inventory: trackers, analytics, APIs, screeners, guides, people, red flags, metric criteria, data gotchas | Includes the agent schema, request graph and screen/vet functions |
| 2 | Long-tail (low-engagement) tools: Perpy, Mirrorly, Bet or Book, PerpPilot, Exit Window, Whale Street, Hyperank, Cashboard, kitsune-de MCP, Senpi | Mostly Nansen "Meridian" hackathon projects — durability unproven |
| 3 | Practitioner workflows (15 write-ups) + "10 most repeated heuristics" | Best source of numeric thresholds |
| 4 | Public-address calibration set (6 "positives", 11 "negatives") | Every row is a **[CLAIM]** |
| 5 | Developer gotchas (17 items) + PnL recipe + agent tooling | API/WS limits, S3 schemas, HIP-3/HIP-4 |
| 6 | Top-40 account ranking, quote graph, communities, shill/noise patterns | Shill labels are **pattern labels by the agent**, mostly without a linked post |
| 7 | 90-day change audit + re-check of "first-pass top 15" | The "top 15" was *reconstructed* by the agent, not the original list |

**Provenance caveats the consuming agent must know**

- **101 unique X post/article URLs** appear in the raw file. All 101 tweet IDs decode (Twitter snowflake) to plausible dates, and all 66 dates the raw file states next to a link match the decoded date — a useful integrity check, but it does not prove the post text matches the agent's paraphrase. Of the 101, **55** have their content captured (still the agent's paraphrase), **30** are only partly summarized and **16** are bare links with no content — see [Appendix A](#appendix-a--x-source-registry-101-links) and [Section 14](#14-grok-follow-up-results-verification-of-vague-and-rule-bearing-posts) (after the Grok pass: 44 of 46 vague posts, all 18 rule posts and all 12 open questions are now verified, corrected or recorded as not found).
- Some "guides" are **web pages, not X posts** (Cipher Intelligence, LabelYX, TrueHold, tool docs). The raw agent labelled them; this file keeps those labels (`[WEB]`).
- Vendor numbers (HyperX score, Hyperdash copy score, Hyperank score, Money Printer cohort, LabelYX ROI) are vendor-defined and often not reproducible.
- Source JSON wrapped URLs in `<…>` autolinks (e.g. `<https://…>`), and a few have broken markup; all URLs below are cleaned.

---

## 3. Tool and resource registry

**Role codes:** **TRACK** (watch positions/flows) · **ANALYSE** (score/profile traders) · **PARSE/DATA** (APIs, indexers, archives) · **FILTER** (explicit screening rules)
**Verdict codes:** **CORE** (build the pipeline on it) · **USE** (good enrichment) · **OPT** (optional / situational) · **WATCH** (unproven, hackathon, or stale) · **EXCLUDE** (execution, unsafe, or off-scope)
**Access:** `page` = public web page · `api` = programmatic · `login` = account needed

### 3.1 Official Hyperliquid sources `[DOCS]`

| Tool | Endpoint / URL | What it gives | Limits / gotchas | Verdict |
|---|---|---|---|---|
| **Leaderboard (UI)** | `https://app.hyperliquid.xyz/leaderboard` | PnL / ROI / volume for 1D, 7D, 30D, all-time; account value | Inclusion reported as account value ≥ $100k **or** volume ≥ $10M (Cipher, 2026-09-30); ROI is deposit-adjusted | CORE (discover only) |
| **Leaderboard JSON** | `https://stats-data.hyperliquid.xyz/Mainnet/leaderboard` | Same data in bulk: address, account value, per-window PnL/ROI/volume | ~39 MB snapshot (2026-09-26 cited); row counts vary by snapshot (see §13); batch, not a stream | CORE |
| **Info API** | `POST https://api.hyperliquid.xyz/info` | `clearinghouseState`, `allDexsClearinghouseState`, `spotClearinghouseState`, `portfolio`, `userFills`, `userFillsByTime`, `userFunding`, `subAccounts`, `vaultDetails`, `userVaultEquities`, `userTwapSliceFillsByTime`, `twapStates`, `openOrders` | Free, no key for reads. History caps and rate weights in §8 | CORE |
| **WebSocket** | `wss://api.hyperliquid.xyz/ws` | `trades` (both counterparties' addresses), `l2Book`, user subs (`userFills`, `userFundings`, `userNonFundingLedgerUpdates`, `allDexsClearinghouseState`, `userTwap*`) | 10 conns / 1000 subs / **10 unique users** per IP; first user frame is `isSnapshot:true`; idle closes after 60 s without ping; not an archive | CORE |
| **API docs** | `hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api` (+ `/websocket/subscriptions`, `/info-endpoint`, `/rate-limits-and-user-limits`, `/nonces-and-api-wallets.md`, `/hip-3-deployer-actions`, `/info-endpoint/spot.md`) | Source of truth for schemas and limits | Fast-moving; append `.md` for raw text; re-read at run time | CORE |
| **Official explorer** | `https://app.hyperliquid.xyz/explorer` | HyperCore tx/account pages | Weaker for trader forensics than HypurrScan | OPT |
| **Stats / ASXN** | `https://stats.hyperliquid.xyz/` (now opens the ASXN protocol dashboard) · `https://hyperscreener.asxn.xyz/home` | Protocol analytics: volume, OI, liquidations, funding, "top traders", vault risk, builder revenue; HyperScreener listed first on the official tools page | Protocol-level first; per-trader skill scores not documented; weak X footprint | OPT `[WEB]` |
| **Official S3 archives** | `s3://hyperliquid-archive/`, `s3://hl-mainnet-node-data/` | Raw fills (`node_trades` → `node_fills` → `node_fills_by_block` from 2025-07-27), `node_raw_book_diffs_by_block` from 2026-01-22 | Requester-pays, LZ4; three fill schemas (see §8); official archive is validator perps, ~monthly, **no HIP-3** | USE |

### 3.2 Position / wallet trackers and explorers (TRACK)

| Tool | URL · handle | What it gives | Access · cost | Caveats | Verdict |
|---|---|---|---|---|---|
| **HypurrScan** | `hypurrscan.io` · `@HypurrScan` | One-address page: perps (entry, liqPx), open orders, fills incl. TWAP slices, spot, vaults, staking, txs | page · free | Not a ranked screener; no alerts; no documented public API; default paste target of `@lookonchain`, `@EmberCN`, `@OnchainLens`; on official tools page `[X][DOCS]` | CORE (human QA) |
| **HyperTracker** | `hypertracker.io` · `app.coinmarketman.com/hypertracker` · `@HyperTracker` | Wallet/whale tracker, smart-money feed, position-change alerts, cohorts (Whale / Leviathan / Smart Money / Money Printer), directional bias, leverage, wallet age, open exposure; `.hl` name search shipped 2026-09-29 | page free (no account); **API**: 100 tokens/day free then $179–$1,999/mo (Cipher 2026-09-20) | "Money Printer" = all-time realized + unrealized > $1M (vendor-defined, not skill); cohorts mix realized and unrealized; on official tools page `[X][VENDOR]` | CORE |
| **HyperTracker API** | `docs.coinmarketman.com/endpoints/leaderboards` | Curated leaderboards: wallet age, leverage, open exposure, directional bias, multi-window PnL/volume | api · token-metered | Use as enrichment, not as the universe; docs dated 2026-08-25 `[WEB]` | USE |
| **CoinGlass HL whale tracker** | `coinglass.com/hyperliquid` | Largest open positions (entry, liqPx, margin, funding), long/short trader ratio, liquidation map | page free; alerts need account; paid plans from $29/mo (TrueHold 2026-09-03, unverified) | Position scanner, not a skill screener; does not separate MM vs discretionary; no dedicated HL X handle found `[WEB]` | USE (scan layer) |
| **Proliquid whales** | `proliquid.xyz/whales` · `@proliquid_xyz` | Large fills + whale liquidations (buy vs sell notional), per-market largest positions, near-liq wallets | page free, 5-min delay; HyperTracker analytics in the terminal unlock at $10k Proliquid volume | Size tracker, not ROI/skill `[X]` | OPT |
| **CoinClass HL whales** | `coinclass.com/hyperliquid/whales` | Largest positions, coin L/S, "smart-money leaderboard" by realized PnL, $1M+ actions | page free | ROI prints 0.0% on several $10M+ PnL rows; 100% WR rows with 12–52 trades are concentration luck; not cited on X `[WEB]` | WATCH |
| **PerpFinder whales** | `perpfinder.com/tools/whales` | Top 20 by account value, daily PnL, open positions (official board + clearinghouse) | page free | Only 20 rows; notional uses entry not mark; thin X footprint `[WEB]` | OPT |
| **Beacon** | `beacontrade.io/leaderboard` | Top 50 accounts by value, uPnL | page free | Size rank; page total ($196M) disagrees with PerpFinder top-20 ($8.29B) `[WEB]` | WATCH |
| **Isobath** | `isobath.io` | Wallet-change tracker: before/after exposure, rank, coverage for BTC/ETH/SOL/HYPE/XRP/AAVE/ZEC/NEAR | page · cost unverified | Observes a slice of OI (e.g. 21.8% BTC); not a PnL board `[WEB]` | WATCH |
| **Hypermonitor** | `hypermonitor.org` | Wallet discover/track; leaderboard "provided by ASXN" | page free; filters "early access" | Leaderboard "Loading…" on crawl; last explicit date 2026-02-19 `[WEB]` | WATCH |
| **Higher.money** | `higher.money/hyperliquid/leaderboard/` | PnL/ROI/volume + profile positions | page free | Page stamped 2026-07-19 — likely stale `[WEB]` | WATCH |
| **HyperPulse traders** | `hyperpulse.fyi/traders` | Top by volume and **realized** PnL over 1h/24h/7d/30d + live whale positions; exposes SQL | page free | Realized excludes open positions (stated on page) `[WEB]` | OPT |
| **HyperStats** | `hyperstats.org` | Wallets graded S+ to F (~103k tracked, cited 2026-09-20), large open/close/liq feed, Telegram | page free | Secondary listing; no dedicated X posts captured `[WEB]` | WATCH |
| **Perpy** | `perpy.xyz` · `@perpyxyz` · TG `t.me/perpyxyz`, `t.me/perpy_hyperliquid` | Follow any HL address with open/close pushes; whale flow 1h/4h/24h; biggest moves with wallet + PnL context; leaderboard; iOS/Android (App Store lists read-only, no wallet connect) | free TG feed claimed; IAP amount unknown | ~30 followers; no public API; discovery feed, not skill screen `[X]` | WATCH |
| **Mirrorly Live** | `mirrorly.xyz` · `@MirrorlyLive` | High-frequency cards: named Mirrorly traders opening/closing on HL (size, coin, win streak) | feed free; **copy product needs exchange API keys (out of scope)** | Nicknames not always `0x`; ~200 curated leaders; near-zero engagement `[X]` | WATCH |
| **Hyperfolio Pulse** | `app.hyperfolio.fun/en/pulse` · `@Hyperfoliofun` | Portfolio tracker + Pulse 1m/5m/15m coin shocks | page · cost unverified | Market tape, not trader skill `[X]` | EXCLUDE (off-scope) |
| **Hypervisor** | `@Hypervisor_hl` | Custom HL dashboards / bubble viz (community wiki) | login · unverified | Product URL `hypervisor.gg` appears in a 2025-01 post only (Grok C05); no 2026 trader-analytics post; last feature post 2025-01-11 `[X]` | WATCH |

### 3.3 Analytics, scoring and screening tools (ANALYSE / FILTER)

| Tool | URL · handle | What it gives | Access · cost | Caveats | Verdict |
|---|---|---|---|---|---|
| **Hyperdash Explore** | `hyperdash.com` (was hypurrdash.app; legacy `legacy.hyperdash.com`) · docs `docs.hyperdash.com/wallet-explore` · `@hypurrdash`, `@cdottrading`, `@HansonBirringer` | Cohorts by PnL and wallet size, copytrading board, tagged funds, per-asset leaderboards. Filters: 1d/7d/30d/all, account value, PnL, **style** (algo/scalp/intraday/swing/position), **copy score 0–100**. Result cols: PnL, equity, trades, win rate, **Sharpe**, **max DD**, leverage, margin utilization, assets. Profile: equity curve, positions, fills, TWAP, deposits/withdrawals. Address pages: `hyperdash.com/address/{addr}` | analytics free; builder fee 0.015% normal / 0.05% copy (Cipher 2026-09-20; verify) | Copy score is vendor-defined; now also a trading terminal (copy path is execution → out of scope); no public bulk API found | CORE |
| **HyperX wallet-discover** | `hyperx.trade/hyperliquid/wallet-discover` · trader page `hyperx.trade/hyperliquid/trader?address={addr}` · `@hyperx_trade` | Filter a million-wallet universe by HyperX Score components: total, profit, stability, risk control, win rate, copy-fit, median duration, leverage, margin usage, recovery factor, Calmar, completed trades; tags (HFT/MM, direction-neutral, big-loser) | browse free; copy uses builder fee (rate unpublished) | Vendor scores; affiliate refs in many posts; copy-fit can be 100 on an HFT/MM wallet (see §10); only public *numeric* screens found on X in 12 months | CORE (rules) |
| **LabelYX** | `labelyx.com` (`/whales`, `/guides/hyperliquid-leaderboard-copy-trading`) | Paste address → PnL, win rate, drawdown, positions, calendar, money-flow; top-100 board; whale page of ~46k wallets | page free, no signup claimed | Extreme ROI outliers (e.g. +2,641,203%) = tiny equity/deposit artifacts; $0-volume whales; X posts not captured `[WEB]` | OPT |
| **Liquary** | `docs.liquary.xyz/explore/leaderboard`, `/explore/whales` · `@liquary_xyz` | Board with PnL, ROI, win rate, 4-bar trend, tiers; **momentum states** (accelerating / cooling / flat / crashed); watchlist + fill alerts; HIP-4 archive | login · cost unverified | App URL not independently confirmed from X; docs updated 2026-09-16/30 `[WEB]` | OPT |
| **Dexly** | `dexly.trade/hyperliquid/leaderboard` | 1D/7D/1M/all-time board + explorer + one-click copy | browse free; copy builder fee unpublished | Execution product (copy) → exclude copy path `[WEB]` | WATCH |
| **Copin** | `@Copin_io` (exact app URL not captured) | Cross-perp-DEX trader explorer: win rate, PnL, drawdown, trade frequency; optional copy (0.05% of size cited) | page | Multi-DEX; no HL-specific screener posts in last 6 months `[X]` | WATCH |
| **Hyperank** | `hyperank.io` (`/how-scoring-works`) · `@hypeRankio` · X article `x.com/i/article/2096610433134120960` | Public-beta copy scoring: official board (46,867 rows) → fills audit on top 7,400 → 2,720 kept; drops wallets whose board 30d is green but account 30d is flat/negative (**1,935**); publishes **minimum copy capital** vs HL $10 ticket | login/public beta · price unknown | Vendor-computed; the X article body is still unretrieved (Grok fetch failed) — the 2026-09-06 post is a long tweet: copy score = copyability not skill, 0.02% builder fee, 30-day simulator, no numeric score cutoffs | USE (method) |
| **Bet or Book** | `bet-or-book.trade` · `github.com/Sofiia7/bet-or-book` · `@SofiiaBorozan` | Classifies an HL whale position as directional **bet** vs **hedge** vs **MM inventory**, with evidence and blind spots | page free; likely needs a Nansen key to self-host | Nansen Meridian hackathon; depends on Nansen labels; durability unknown `[X]` | OPT |
| **PerpPilot** | `github.com/TheRealNajim/PerpPilot` · `@TheRealNajim` | Discover = Nansen "Smart HL Perps Trader" cohort (past week); track wallet → 30d win rate, **profit factor**, equity curve, 0–100 Copy Score; alerts open/close/flip/add/reduce/near-liq; **flock** signal (2+ tracked traders same side within 15 min) | OSS; runtime needs Nansen API | Profit factor formula not posted; Nansen label bias; hackathon `[X]` | OPT |
| **Exit Window** | `exit-window.fly.dev/waitlist` · `@kamalbuilds` | For your HL address: finds Nansen Smart Money on the same side; time from their first sale to price −1%; liq overlap; alarms; Sentinel (242 labelled wallets, 30 s poll) | waitlist; Nansen-dependent | Copy execution path not read-only; hackathon `[X]` | WATCH |
| **Whale Street** | live URL not captured · `@BazydloMis57623` | Each listed "company" is a real HL trader; NAV from live positions; six-check listing committee (track record, size, human vs bot, linked-wallet hedges, concentration, uniqueness) | play money + optional real mirror via Nansen Trading API | Code URL blank; demo may be demo-only `[X]` | WATCH |
| **Senpi wallet leak scanner** | `@senpi_ai` | Paste address → read-only hold-time / fee / funding "leaks" | page; not an API | Same vendor sells execution products `[X]` | OPT |
| **Senpi HL toolkit** | `@betashop` article (2026-02-24) | Claims 45 MCP tools incl. 5 trader-discovery tools (rank all HL perp traders by ROI, PnL, win rate, drawdown, gain-to-pain across d/w/m/all) | hosted + self-host claimed | Execution-heavy; only the discovery subset is relevant; schema not opened `[X][VENDOR]` | WATCH |
| **Cashboard** | `@CashBoardLive`, `@Story91_` | Canvas of 40+ widgets (HL funding, liquidations, whale bets); public API no key | web free; desktop $29 | Desk UI, not a screener; token ticker in launch post — separate product from token `[X]` | EXCLUDE |
| **OpenCatz AI scouts** | `github.com/dizcorvus/opencatz-ai` · amplified by `@0xAiraa` | OSS bot with 15 scouts across chains incl. HL (pools, whales, breakouts) | free OSS | HL is one chain of many; NFT-gated marketing `[X]` | EXCLUDE |
| **MinaraCN method** | `x.com/MinaraCN/article/2094646483396284853` | Reproducible 43,618-address screen from the full leaderboard CSV (see §6.2) | n/a (method) | Not a hosted tool | USE (rules) |

### 3.4 Data, indexers and archives (PARSE/DATA)

| Tool | URL · handle | What it gives | Cost / access | Caveats | Verdict |
|---|---|---|---|---|---|
| **Hypedexer** | `hypedexer.com` · docs `docs.hypedexer.com/quickstart` · `@hypedexer`, `@Yaugourt`, `@EnigmaValidator` | Indexed HyperCore fills since Nov 2024, **reconstructed round-trips**, HIP-3/HIP-4, builder-code attribution, TWAPs; REST + WS + **78 read-only MCP tools** (vendor/docs claim — *not* in the 2026-09-29 X thread; the 'fills since Nov 2024' claim is confirmed in the 2026-09-28 Trust Wallet post); example calls: `GET /analytics/fills/stats?hours=24`, `/twaps/stats?hours=24`, `/hip3/overview`, `/hip3/top-movers?limit=100`, `/hip3/auctions/history?limit=200`; Trust Wallet cited as customer | api · hosted free tier 5,000 credits/month | V2 + MCP live 2026-09-16; best X-announced read-only agent-shaped archive; pricing tiers unverified `[X]` | **CORE (history)** |
| **Dune curated HL tables** | `docs.dune.com/data-catalog/curated/perpetuals/hyperliquid/overview` (+ `/perp-accounts-daily`) · `@Dune` | `perp_trades` (both legs, fees, realized PnL, liq/ADL), `perp_accounts_daily` (`realized_pnl_usd`, `net_pnl_usd`, `fee_usd`, `funding_paid/received`, volume, liq/ADL volume, collateral flows), `perp_positions_hourly` | login · free tier + paid; HyperCore tables may be gated (HyperEVM free vs HyperCore add-on) | `net_pnl_usd = realized − fees + funding`; open uPnL not included; **no X-verified ready-made "skilled trader" dashboard exists** `[DOCS]` | CORE (warehouse) |
| **Hydromancer** | `docs.hydromancer.xyz` (`/reservoir`) · `@hydromancerxyz` | Non-rate-limited APIs + **Reservoir**: daily requester-pays parquet/S3 fills with liq/ADL/builder/TWAP splits, HIP-3 included | cost unverified | Contrast: official archive is validator perps, ~monthly, no HIP-3 | USE |
| **Bitquery** | `bitquery.io/datastore/datasets/hyperliquid-trades` · video `youtube.com/watch?v=72KUgKEwDrU` (2026-09-09) | Every HyperCore fill both sides, realized PnL, fees, taker flag, liquidations, TWAP status; copy-trading query pack (live fills, positions, order lifecycle) | plans; free IDE claimed | Datastore page says coverage "latest month to yesterday" — confirm full history | USE (fallback) |
| **Allium** | `docs.allium.so/historical-chains/supported-blockchains/hyperliquid` | Indexed historical chain/account/market/order-book data | paywall typical; HL price not found | `[WEB]` | OPT |
| **Uniblock** | `docs.uniblock.dev/guides/hyperliquid/overview` | Non-rate-limited API proxy (official tools list) | unverified | `[DOCS]` | OPT |
| **HypeDexer(Enigma) / SonarX** | `docs.sonarx.com/datasets/HYPERLIQUID/Hyperliquid` | Indexing (official tools page 2026-09-24) | unverified | — | OPT |
| **GoldRush** | `goldrush.dev/docs/api-reference/hyperliquid-info/builder-fills` | `builderFills` / `builderFillsByTime` (2,000/page) — **no official `/info` twin** | docs | Docs-only evidence; not an X launch | OPT |
| **0xArchive** | `@0xArchiveIO` | Paid/free-key historical API (native history + rate limits collide with live bots) | key | 30 days of 1-minute history loaded in a 3-hour live migration; free API key at `0xarchive.io/signup` (2026-09-04 post); pricing tiers not stated `[X]` | OPT |
| **Nansen Perp Screener API** | `docs.nansen.ai/api/hyperliquid/perp-screener` · `@nansen_ai` | Screen HL perps by volume, OI, funding, smart-money long/short; dataset reliable from May 2025; labels incl. "Smart HL Perps Trader" | paywall | Market-level screener, not a public trader-skill board; label bias | OPT |
| **Arkham** | `arkm.com` | Wallet clustering / entity labels (Lookonchain posts HL flows with Arkham entity URLs) | free pages + paid | Use for **cluster/entity resolution only**; sparse HL method posts | OPT (downgraded) |
| **DoubleZero Edge** | `@doublezero` | Uncapped L4 incl. HIP-3 (public WS `l2Book` is only 20 levels/side) | commercial | Needed only to rebuild order books / MM behaviour | OPT |
| **Liquary HIP-4 archive** | `@liquary_xyz` | Keeps HIP-4 prediction markets after the node purge | public Data section | — | OPT |
| **Cipher "13 whale trackers"** | `cipher-intelligence.io/blog/hyperliquid-whale-tracker/` (2026-09-20) | Tool matrix + official-API recipe to build your own tracker | blog | Not X-native `[WEB]` | reference |

### 3.5 SDKs and MCP servers (agent tooling) — safe vs unsafe

| Item | Link | Read-only? | Notes | Verdict |
|---|---|---|---|---|
| **Official Python SDK** | `github.com/hyperliquid-dex/hyperliquid-python-sdk` | Has signing — wrap the `Info` module only | v0.24.0 seen in a 2026-07-22 testnet test | USE (info-only) |
| **nktkas/hyperliquid (TS)** | `github.com/nktkas/hyperliquid` · `jsr.io/@nktkas/hyperliquid` | Yes if you import only info/subscription modules; exchange module signs | Typed REST+WS (`aggregateByTime`, `isSnapshot`); transport docs encode WS quotas; JSR 0.33.3 ~2 months before pull — re-check commit | USE |
| **nomeida/hyperliquid (TS)**, **infinitefield/hypersdk (Rust)**, **CCXT hyperliquid** | `github.com/nomeida/hyperliquid` · `github.com/infinitefield/hypersdk` · `docs.ccxt.com/#/exchanges/hyperliquid` | Some examples need private keys | Prefer info-only clients | OPT |
| **kitsune-de/hyperliquid-mcp** | `github.com/kitsune-de/hyperliquid-mcp` · `npx @kitsune-de/hyperliquid-mcp` · `@kitsunedevs` | **Yes** — public info API only; 2 source files, zero keys, cannot trade | Positions/PnL/liqPx/fills/funding of ANY address + markets/funding/OI/books/candles; same fill-history cap; confirm npm name still matches repo; 3 likes / 24.8k views (2026-07-18) | **USE (default agent adapter)** |
| **Hypedexer MCP** | see §3.4 | Yes (78 tools) | Only X-announced archive-shaped read-only MCP | **CORE** |
| **Aurracloud/hyperliquid-mcp** | `github.com/Aurracloud/hyperliquid-mcp` | Read-capable (`getTraderPositions`, open orders, user fills, markets) | Not found via an X post; check commit recency | WATCH |
| **hypergrok-trading-desk SKILL.md** | `github.com/galleonlabs/hypergrok-trading-desk/blob/main/skills/hyperliquid-api-reference/SKILL.md` | Reference only (parent desk may trade) | Verified against official docs 2026-08-16; lists WS types and caps | USE (reference) |
| edkdev/hyperliquid-mcp · Dakkshin/hyperliquid-mcp · patricleehua/hyperliquid-trader-mcp · 0xikalgo/hyperliquid-mcp | GitHub | **No — require private keys / place orders** | Phishing risk if a random MCP asks for a main wallet key | **EXCLUDE** |
| **@liquidbots MCP** | `@liquidbots` | No (their grid product) | Not a public research toolkit | EXCLUDE |
| **Scarlett.ai API/MCP** | `scarlett.ai/account/` · `@BrendanPlayford` | No (live HL trading is the advertised next step) | Exclude until an info-only mode is proven | EXCLUDE |
| **Mirrorly copytrader / Dexly copy / HyperX copy / Hyperdash copy / Copin copy / vault deposit** | — | No (builder-fee approval or exchange API keys) | Out of scope for the research agent | EXCLUDE |
| **`@2oolkit/hyperliquid-cli` 0.2.2** | npm | **Malicious** — flagged **MAL-2026-3679** (2026-09-30): silent `approveBuilderFee` + referrer on `config init` | Ban unsigned "HL MCP/CLI" packages | **EXCLUDE (hostile)** |
| LouMercatali homemade Claude MCP | no repo | n/a | Anecdote only | ignore |

### 3.6 Found but excluded as leads (web-only, not from X)

| Item | Why it is only a lead |
|---|---|
| Dune web queries `dune.com/queries/6994144` (win rate), `/6994277` (single wallet), `/7667431` (whale PnL) | Found via web, **not via X** — unverified; check whether they were ever posted on X |
| Parse.bot (wrapped leaderboard API), Hyperbot.network (live tape) | Web-found |
| OSS Telegram bots: `walqed/…`, `cobecheng/hypertracker-bot`, `shelteredcorgi/hypescanner-tg`, `rokitgg/hyperliquid-trades-feed`, `Mperomishael/smart-trader-bot` | Exist on GitHub; not linked from any retrieved X post |
| CoinLobster, Buildix, Hyperbot, Flipside HL dashboards | Thin or no X threads in last 6 months; listed from the Sep-2026 comparison article |
| TrueHold "best HL tools 2026" (`truehold.xyz/blog/best-hyperliquid-tools`, 2026-09-03) | Job-sorted tool list; not X-native |

---

## 4. Guides, articles and studies

| # | Item | Link | Date | Type | Key takeaway |
|---|---|---|---|---|---|
| 1 | **Chase: 935k-wallet persistence test** (`@chase_mew_`, builder at `@BounceTech`) | `x.com/chase_mew_/status/2079212386532139461` | 2026-07-20 | `[X]` study | Last month's winners are barely better than chance next month (§6.5). Strongest anti-leaderboard evidence |
| 2 | **HyperX smart-money filter playbook (part 1 / part 2)** | `x.com/hyperx_trade/status/2100489602935210165` · `…/2102973181183332444` | 2026-09-17 / 2026-09-24 | `[X]` | Numeric screen + veto list for copyable vs lucky/HFT wallets (§6.2) |
| 3 | **lucas_faster HyperX workflow** | `x.com/lucas_faster/status/1919348617154101588` | 2025-05-05 | `[X]` | 30d WR/ROI/trade-count band; kill jagged curves; prefer multi-hit PnL. Older but consistent with 2026 posts |
| 4 | **MinaraCN: dissect 43,618 addresses** | `x.com/MinaraCN/article/2094646483396284853` | 2026-09-01 | `[X]` article | Five-step screen from the full leaderboard CSV, then fill forensics |
| 5 | **Hyperank: board → fills → min copy capital** (thread + article) | `x.com/hypeRankio/status/2103800999164960955`, `…/2103902033635852518`, `…/2103806591732531551`, `…/2101640190049550478`, `…/2104257079913697458`, `…/2104257085567324282`, `…/2096629457981235203`; article `x.com/i/article/2096610433134120960`; scoring page `hyperank.io/how-scoring-works` | 2026-09-06 → 09-27 | `[X]` | "Profit ≠ copyable"; fill-audit method; copy-capital math |
| 6 | **@thesogle_ vault allocator thread** | `x.com/thesogle_/status/2097614408440488189` | 2026-09-09 | `[X]` | Don't allocate on APR screenshots; ask drawdown and leverage; survivorship in vault lists |
| 7 | **@thedefiedge tool-chain write-up** | `x.com/thedefiedge/status/2016118571483447674` | 2026-01-27 | `[X]` | HyperTracker → Hyperdash → Super; copy ≤3 wallets; avoid wallets with tons of positions |
| 8 | **HyperTracker style buckets** (`@djkanzen`) | `x.com/djkanzen/status/2079221726991491284` | 2026-07-20 | `[X]` | Five live style segments re-queried every 1–6 h on single-coin performance |
| 9 | **Exit Window thesis** | `x.com/kamalbuilds/status/2104342660500918637` | 2026-09-27 | `[X]` | "Entries without exits = exit liquidity"; measured 1m07s NEAR window |
| 10 | **Bet vs book vs inventory** | `x.com/SofiiaBorozan/status/2104233781192528289` | 2026-09-27 | `[X]` | Don't copy a position until you know whether it is a bet |
| 11 | **Specialist hunt on Hyperdash** (`@reisnertobias`) | `x.com/reisnertobias/status/2049410876109697529` · `…/2049522367680938043` | 2026-04-29 | `[X]` | Single-market specialists (OIL, equities) with 30d DD/WR/Sharpe; alerts via `@lit_trade` |
| 12 | **Developer thread: the 2,000-fill wall** (`@Yaugourt`) | `x.com/Yaugourt/status/2100167855765364826` | 2026-09-16 | `[X]` | Public-API caps, HIP-3, TWAP, builder-fee gotchas (§8) |
| 13 | **Cipher Intelligence: copy-trading 2026** | `cipher-intelligence.io/blog/hyperliquid-copy-trading/` | 2026-09-20 (re-read 09-30) | `[WEB]` | Best written synthesis: official ROI formula, $0-volume trap, vault economics, HFT uncopyability |
| 14 | **Cipher: 13 whale trackers** | `cipher-intelligence.io/blog/hyperliquid-whale-tracker/` | 2026-09-20 | `[WEB]` | Tool matrix + official API recipe |
| 15 | **LabelYX leaderboard-for-copy guide** | `labelyx.com/guides/hyperliquid-leaderboard-copy-trading` | updated Jul 2026 | `[WEB]` | 30d as first filter; cross with all-time; 24h/7d = hot streaks/luck |
| 16 | **TrueHold best HL tools 2026** | `truehold.xyz/blog/best-hyperliquid-tools` | 2026-09-03 | `[WEB]` | Job-sorted tool list |
| 17 | **Bitquery copy-trading query video** | `youtube.com/watch?v=72KUgKEwDrU` | 2026-09-09 | `[WEB]` | Three queries: live fills, positions, order lifecycle |
| 18 | **Senpi trader-discovery article** (`@betashop`) | `x.com/betashop/status/2026375093295919221` | 2026-02-24 | `[X]` vendor | 5 discovery tools inside a 45-tool MCP; not independently opened |

**Weak / not practitioner method (exclude from rule-mining):** `@GoHyperTrend` "114% win rate" · `@Crypto_Retardio` / ALM "$1M member profits, 40%+ WR" (unaudited group claim) · `@zaika_hl` copy advice (Polymarket, not HL) · `@Emmah_Jayy` Quant AI thread (generic copy advice).

### 4.1 Practitioner write-ups in detail (steps, rejects, tools)

**1. `@chase_mew_` — persistence test (a failure of the naïve copy screen)** — 2026-07-20 — builder; goal was copy-trading "best" wallets.
Steps: take ~935,000 HL wallets over one year → rank by monthly performance, mark top 10% each month → test whether last month's winners remain winners.
Numbers stated: top-10% month *t* → top-10% month *t+1*: **19%** · still profitable next month: **~50%** · random user profitable in a month: **42.3%** · prior top trader profitable next month: **45.5%** · R² = **0.036**. Reject rule: treating last month's leaderboard as a copy list.

**2. `@koolkrypto223` — why monthly rank fails for discretionary traders** — 2026-07-20 (reply to Chase). Self-described top-100 all-time HL PnL, runs a fund, posted no address. Don't score discretionary books on "green every month"; expect PnL from **3–5 large trades per year**, flat or slight bleed otherwise; no numeric threshold.

**3. `@totlsota` — don't copy one leg of a book** — 2026-07-20. Quant/HFT/multi-venue. Reject any "top wallet by volume and wildly profitable" that is **one leg of a delta-neutral multi-venue book**.

**4. `@djkanzen` / HyperTracker — style buckets, not all-time PnL** — 2026-07-20. Five live segments: top scalpers, counter scalpers, top day traders, counter day traders, top swing traders; re-query every **1–6 h** on **single-coin** performance; a wallet can enter a segment in the morning and be removed by evening. Reject stale all-time heroes; want current coin specialists.

**5. `@thedefiedge` — watchlist + timeframe filter, no automation** — 2026-01-27 (has *not* automated copy). (1) HyperTracker: size/profit buckets, live positioning, liq map, directional bias → watchlist of consistent outperformers. (2) Crowd tell: smaller and unprofitable wallets skew more bullish. (3) Hyperdash: copy **at most 3** wallets; replicate **net exposure**. (4) Filter swing/position (longer holds). (5) Super: long-only/short-only, token allow/deny, backtester. (6) Own thesis first; tools as gut-check; start small; expect lag. Reject wallets with **tons of open positions** (possible MM) and blind PnL aping. Tool chain: `@HyperTracker` → `@hypurrdash` → `@trysuper_`.

**6. `@hypeRankio` — fill audit, then copy capital** — 2026-09-20 → 09-27. Steps: start from official board (~46,867) → hand-inspect fills on top **7,400**, keep **2,720** → drop wallets whose official 30d is green but account 30d is flat/negative (**1,935**) → compute the **minimum wallet** that can replay the book given HL **$10** minimum order → size the copy to *your* equity. Rejects counted out of **4,680** fails (overlap allowed): leverage too high **534** · margin near max/near liq **490** · 30d drawdown too deep **639** · near-perfect win rate that doesn't add up **18** ("win rate is usually the last number that tells you anything"). Tools: official leaderboard + own fill engine + `hyperank.io`.

**7. `@C_Predecessor`** — 2026-09-26 reply: "Drawdown first. How they behave when a trade goes wrong."

**8. `@hyperx_trade` + `@lucas_faster` — numeric copy screen** — see §6.2 for every number.

**9. `@MinaraCN` — full-board CSV then fills** — 2026-09-01. Steps: load full official dump (**43,618** rows) → keep equity ≥ $10k, all-time PnL and ROI > 0, all-time vol ≥ $1M, month vol ≥ $100k → compare PnL and ROI across 1d / 1w / 1m / all-time (not a hard all-positive filter) → score all-time PnL + all-time ROI + account value + cumulative volume + month volume + count of recent profitable windows (no weights published) → read public fills (assets, frequency, both sides?, concentration). Rejects: tiny-account ROI spikes, inactive books, single-trade profits.

**10. `@thesogle_` — vault allocator, not trader hero** — 2026-09-09. Stop optimizing own entries if someone else already has a book; ignore +1,000% screenshots; ask drawdown and leverage; survivorship (dead vaults leave the list). Reject APR-only vault marketing.

**11. `@reisnertobias` — specialist hunt on Hyperdash** — 2026-04-29. Find a single-market specialist (OIL, equities), not a multi-asset hero; read 30d DD/WR/Sharpe; alerts and chart overlays via `@lit_trade`. Published examples (not cutoffs): OIL book all-time PnL +$1.4M, 30d DD 1.0%, WR 80%, Sharpe 13.15; equities trader 30d DD 20.2%, WR 79%, Sharpe 10.58.

**12. `@13_niakris` — six-question copy checklist** (Coinpilot-adjacent; claims HL-tested) — 2026-04-06. Skip if max DD ≥ 22% (aim < 15%) · last trade ≥ 7 days = asleep · high vol + AI risk alerts → size × 0.5 · > 5 open positions = correlation · hold time must match style (holder ≥ 24h vs scalper < 1h) · Sharpe ≤ 1.5 = "lottery". Thresholds are the author's, not protocol.

**13. Buildathon method posts (not long track records)**

| Account | Date | Check first | Reject |
|---|---|---|---|
| `@kamalbuilds` Exit Window | 2026-09-27 | Time from smart-money first sell to −1% (example 67 s on NEAR, 2026-09-23) | Copying entries only |
| `@SofiiaBorozan` Bet or Book | 2026-09-27 | Is the position a bet, hedge or MM inventory? | Copying inventory |
| `@TheRealNajim` PerpPilot | 2026-09-27 | 30d WR, profit factor, equity, Copy Score; flock = 2+ same side in 15 min | Unscored weekly-PnL names |
| `@BazydloMis57623` Whale Street | 2026-09-25 | Six checks incl. human vs bot, linked hedges, concentration | 817 trades/day labelled MM |

**14. On-chain desks — the implicit workflow.** `@lookonchain`: address → HypurrScan / Arkham cluster → follow for weeks → publish blow-ups. `@OnchainLens`: card with 0x + lifetime vs 30d vs open book; tags Wintermute as MM-scale. `@EmberCN`: same wallet across weeks (entry, add, uPnL). Shared reject: one viral green card — they keep the address until it dies or withdraws.

**15. Cipher / LabelYX** `[WEB]` repeat the same two rules: skip $0-volume top-PnL rows; prefer 30d ∩ all-time; moderate leverage 2–5x on BTC/ETH; vaults — check age, skin, survivorship; 24h/7d = luck.

---

## 5. People and accounts

### 5.1 Top 40 ranked for trader-research signal
"Credible" = posts `0x` + metrics, revisits the same book, or ships a tool other researchers reuse. *Not* ranked by followers or HYPE bagholding. Ranking is the research agent's judgement `[SYNTH]`.

| # | Handle | Niche | Why credible (signal/noise) |
|---|---|---|---|
| 1 | `@lookonchain` | Multi-week whale tape | Same 0x across weeks; publishes wins **and** exits (Garrett Jin −$14.7M). Industry default cite |
| 2 | `@OnchainLens` | HL cards with address | Wintermute `0xecb6…`, cluster withdrawals, lifetime vs open book. High reuse, low narrative |
| 3 | `@EmberCN` | CN desk, multi-week follows | Same wallet add/reduce/uPnL; research cadence |
| 4 | `@hypedexer` | Indexed fills / MCP | Nov-2024 archive; HIP-3/TWAP/builder codes; Trust Wallet + `@Yaugourt` as users |
| 5 | `@Yaugourt` | Builder explaining the 2k-fill wall | Named the cap other tools work around |
| 6 | `@HyperTracker` / `@djkanzen` / `@coinmarketman` | Cohorts + live books | Style buckets, 1–6 h refresh, builder-code volume; used by `@thedefiedge` |
| 7 | `@hypurrdash` / `@cdottrading` | Terminal + trader pages | 30d DD/WR/Sharpe specialists (`@reisnertobias`); still shipping Sep 2026 |
| 8 | `@hyperx_trade` | Copy screens with numbers | Posted WR/DD/hold/lev vetoes others quote; product-biased but falsifiable |
| 9 | `@hypeRankio` | Fill-audit scoring | 46,867 → 2,720; 1,935 board≠account; min copy capital. Method > marketing |
| 10 | `@chase_mew_` | Persistence study | 935k wallets, R² 0.036 |
| 11 | `@koolkrypto223` | Discretionary PnL reality | Top-100 AT claim + veto of monthly-rank screens; no 0x |
| 12 | `@nansen_ai` | Labelled HL perps | Labels feed Exit Window/PerpPilot/Bet-or-Book; label bias applies |
| 13 | `@CryptHypoBuster` | 248-wallet whale registry (selection method not stated); 2026-09-30: two wallets reopened **$46.5M** of 40x BTC longs, whale BTC longs $138.6M → $210.5M; amber = liq within 5% of price | Size-weighted leverage, liq distances; sample not universe |
| 14 | `@MinaraCN` | Full-board CSV screen | Reproducible 43k-row filter |
| 15 | `@thedefiedge` | Tool-chain write-up | "Don't copy MMs"; practitioner |
| 16 | `@reisnertobias` | Specialist hunt | OIL/equities 0x + 30d DD/Sharpe; thin duration |
| 17 | `@HyperliquidX` | Protocol source | Required upstream; official host for announcements |
| 18 | `@HyperliquidR` / `@ponyo_fp` / `@FourPillarsFP` / `@GLC_Research` | Independent research hub | Annual report, hl.eco financials; protocol/token more than wallets |
| 19 | `@Hyperliquid_Hub` | Recap + gHypurr cards | Abraxas $859M book; aggregator, variable quality |
| 20 | `@DexterOnchain` | Copy-score vs MM | Showed "copy-fit 100" on an HFT/MM wallet — calibration gold |
| 21 | `@thesogle_` | Vault allocator | DD/leverage over APR; survivorship |
| 22 | `@totlsota` | Quant / multi-venue | Don't copy one leg of a delta-neutral book |
| 23 | `@C_Predecessor` | Risk-first reply | "Drawdown first" |
| 24 | `@lucas_faster` | HyperX power user | 30d WR/equity/trade-count band; product-adjacent |
| 25 | `@hydromancerxyz` | S3 / Reservoir | Official archive vs HIP-3-complete daily dump |
| 26 | `@doublezero` | Uncapped L4 incl. HIP-3 | Data-path fact |
| 27 | `@tradexyz` / `@sershokunin` | HIP-3 deployer | Where `xyz:` books live; so scorers don't drop HIP-3 volume |
| 28 | `@AiCoinzh` / `@AiCoincom` | Liq forensics | pension-usdt.eth $111M ETH short close with timestamp |
| 29 | `@Perps_AI` | Recap of Lookonchain | Garrett +$11.2M / +$8.38M / −$35.44M on one card |
| 30 | `@altcopytrade` | Vault API thread | "Public API is the raw layer"; vault-scoped |
| 31 | `@hlnames` | .hl identity | Makes tracker pages readable |
| 32 | `@mogie__` | HIP / fee mechanics | Named in community maps; verify each thread |
| 33 | `@ericonomic` | On-chain/fundamental | Wiki "notable contributor"; mixed token vs trader |
| 34 | `@shaundadevens` | HIP-3 KYC/allowlist | Protocol note, not wallet scoring |
| 35 | `@0xTraderSam` | Venue structure | TradeXYZ concentration; protocol risk |
| 36 | `@kamalbuilds` | Exit-lag tool | 67 s NEAR exit window; hackathon durability unknown |
| 37 | `@SofiiaBorozan` | Bet vs book vs MM | Classifier, not a feed |
| 38 | `@TheRealNajim` | PerpPilot | Profit factor + flock; vendor |
| 39 | `@GHYPURR` | On-chain cards | Source tag on Hub/Abraxas/Machi posts; thin analysis |
| 40 | `@whale_alert` | Size pings | $57M HYPE Core transfer; zero trader quality — wake-up only |

**Honourable (lower signal or off-scope):** `@arkham` (entity labels), non-English Lookonchain mirrors, `@senpi_ai`, `@CashBoardLive`.
**Other accounts that appear as evidence or supporters:** `@VietnamPenguin`, `@jodezXBT`, `@iamalijandro`, `@Coin_Scoop`, `@0xZecup`, `@pnlsdaily`, `@KaiVenn__`, `@Hyperbotai`, `@ItsBitcoinWorld`, `@rpahlmeyer`, `@lbexplorer`, `@KORypto_JUN`, `@shridlock`, `@Kosumi1989`, `@CryptoAddict31x`, `@cryppimagic`, `@harmonixfi`, `@joeblau`, `@Papurrrtrade`, `@iam4x`.

### 5.2 Who quotes whom (endorsement graph)
```
Lookonchain ──► OnchainLens, Perps_AI, AiCoin, Hub recaps
OnchainLens ──► same Wintermute/Abraxas 0x reused by news accounts
thedefiedge ──► HyperTracker, hypurrdash, trysuper_
reisner     ──► hypurrdash, lit_trade
Yaugourt    ──► hypedexer
kamalbuilds ──► nansen_ai labels
Hub         ──► gHypurr, hypedexer, doublezero, tradexyz
HRC/Seoul   ──► FourPillars, GLC, HypurrCo, HypurrCorea
hlnames     ──► HyperTracker
Official spine: HyperliquidX → public /info + leaderboard JSON → trackers → CT cards
```

### 5.3 Lists and communities
**X Lists:** none found as public `x.com/i/lists/…` URLs — do not invent list IDs. Working substitutes: `@HyperliquidX` (protocol + IRL events, Singapore 2026-10-05) · `@Hyperliquid_Hub` (48h recap + "OG Spotlight by views" — engagement, not skill) · `@HyperliquidR` (Four Pillars + GLC research collective, not affiliated) · `@hypurr_co` (HypurrCollective; Nansen × HypurrCo validator) · hyperliquid-co gitbook community map (`@kirbyongeo`, `@laurentzeimes`, `@fiege_max`, `@GuthixHL`, `@derteil00`, `@sershokunin`) · KR (`@hypurrcorea`, `@Hyperliquid_KR`, `@SKYGG_Official`, `@DeSpreadTeam`) · MY (`@Hyperliquid_MY`) · CN (`@hleco_cn`, cited by `@JimmyYu_HL`) · ES (`@Hyperliquid_ES`, `@VikingoDigital_`, unverified research quality) · `@GoodCryptoApp` "Mega Influencer List 2026" (**not a research list**).

### 5.4 Noise / shill patterns (labels by the research agent, **not** substantiated by links)
| Pattern | Examples | Why it fails a research graph |
|---|---|---|
| Affiliate copy terminals | XT Smart Money, Coinpilot/BitMEX HL copy threads, Bloom, Superior | ROI/WR UI, no fill audit, referral codes |
| Unaudited group PnL | `@Crypto_Retardio` / ALM | Claim without a 0x set |
| Engagement maxi lists | `@GoodCryptoApp` | Followers ≠ tape |
| Points / S3 farm talk | `@SageWhale`, `@Henrik_on_HL` | Activity ≠ skill |
| Joke-to-real shill | `@HYPEconomist` | Agent's label; the quoted "dump-on-outsiders" line was **not** in the post Grok opened (a NEAR meme call) — unverified |
| Headline MM shorts as "smart money view" | Downstream of OnchainLens Wintermute cards that drop the hedge caveat | Copy trap |
| Impossible win rates | `@GoHyperTrend` (114%) | Impossible WR |
| Generic "copy this vault" video | `@Khingbenz7` (Alphio-style) | Steps to click Copy, not to vet |
| Paid-collab bios | `@elenalin01` | Volume-share infographics, no wallets |

Most rows above have no tweet URL in the raw file. Grok C08 could not find `@zaika_hl`, `@Emmah_Jayy`, `@SageWhale`, `@Henrik_on_HL`, `@Khingbenz7`, `@elenalin01`, XT Smart Money, Coinpilot, Bloom or Superior, and the opened `@JoestarCrypto` post does **not** contain the "didn't farm Hyperliquid copy pastes" line — so these stay agent labels, not evidence.

**Signal / noise / anti-signal map**
```
SIGNAL      Lookonchain / OnchainLens / Ember / chase_mew_ / hypedexer / Hyperank method
            HyperTracker · Hyperdash · HyperX filters · Nansen labels (with bias)
NOISE       Hub OG-by-views · GoodCrypto maxi list · affiliate copy · S3 farm
ANTI-SIGNAL Wintermute/Abraxas shorts-as-calls · 30d board #1 · unaudited group WR
```

---

## 6. Metrics and screening criteria

### 6.1 Metric-by-metric guide

| Metric | How it is used by practitioners | Source |
|---|---|---|
| **Timeframe** | 24h/7d = hot streak/luck. **30d = first copy filter.** All-time = consistency; require overlap with 30d | LabelYX `[WEB]`, MinaraCN `[X]` |
| **ROI vs absolute PnL** | Official ROI = `PnL / max($100, starting_value + max_net_deposits)` (deposit-adjusted). Third-party ROI often is not. Use ROI to stop deposit inflation but keep an absolute-PnL floor. HyperX wants PnL > $20k and ROI in a 20–50% band (avoid 100x small-account lottery) | Cipher `[WEB]`, HyperX `[X]` |
| **Win rate** | HyperX floor 50% (Sep 2026) or lucas 70% (2025, 30d). Weak alone: Hyperdash showed a +$8.57M BTC book at 35% WR / 26 trades / $885M volume; Hyperank: "last number that tells you anything"; 18 near-perfect-WR rows cut | HyperX, lucas, Hyperdash, Hyperank `[X]` |
| **Profit factor** | PerpPilot computes it from 30d fills for Copy Score; **no numeric cutoff posted anywhere** | `@TheRealNajim` `[X]` |
| **Drawdown** | HyperX: drop max DD > 50%; Niakris: skip ≥ 22%, aim < 15%; Hyperank cut 639 for deep 30d DD; `@C_Predecessor`: "drawdown first"; thesogle: DD over APR. **Cutoffs conflict (15% / 22% / 50%) — treat as "read DD," not one number** | multiple `[X]` |
| **Sharpe / Sortino** | Hyperdash Explore exposes Sharpe; Niakris: Sharpe ≤ 1.5 = lottery; reisner published 30d Sharpe 13.15 / 10.58 (snapshots to recompute). HyperX uses Recovery Factor (drop if > 1000 as anomaly) and Calmar as helpers. **No community Sharpe/Sortino cutoff on X beyond Niakris** | `[X]` |
| **Leverage** | HyperX: reject > 25x (use *historical average*, not the current flat book), margin usage > 90%; Hyperank cut 534 high-leverage + 490 near-liq; Cipher: prefer 2–5x on BTC/ETH, reject 10x thin alts | `[X]`, Cipher `[WEB]` |
| **Holding time** | HyperX: median hold > 1h to be copyable; exclude avg hold < 3 min (HFT). Niakris: holder ≥ 24h vs scalper < 1h. Hyperank (Lighter RH data cited): hold < 15m profitable 32% vs 4–12h 45%. Copy the round trip, not every add/reduce on MM books | `[X]` |
| **Trade count** | HyperX: > 10 completed. lucas: 5–100 in 30d (< 5 undersampled; > 100 ≈ bot). Minara uses volume floors instead | `[X]` |
| **Account age / activity** | HyperX: active cycle > 2 months, exclude inactive 30d. Niakris: last trade ≥ 7d = asleep. Cipher (vaults): prefer age > 1 year. Minara: require recent windows still green | `[X]` |
| **PnL concentration** | Reject one-hit lottery: lucas "multiple high-profit trades"; Minara single-trade profits; Whale Street concentration check; CoinClass 100% WR / 12–20 trades flagged | `[X]` |
| **Liquidation history** | Risk flag, not auto-disqualify: `0x337afda…` has 7 lifetime liqs yet +$632k perps (OnchainLens 2026-09-08) | `[X]` |
| **Funding vs directional** | Dune `net_pnl_usd` applies funding. Dexter example: 90d funding −$155.9k vs fees $163.2k on a "top copy" book. Vault L/S grids can bleed funding (vaults can't hold spot) | `[DOCS]`, `[X]` |
| **Long/short bias** | Hyperdash/HyperTracker expose direction bias; do not treat 100%-long cohort weeks as skill; smaller/unprofitable wallets skew bullish (thedefiedge) | `[X]` |
| **Consistency across windows** | Liquary trend/momentum vs trailing week; Minara counts how many of 1d/7d/30d/all are profitable; HyperX wants rising equity, not a spike | `[WEB]`,`[X]` |
| **Gain-to-pain** | Claimed as a Senpi discovery rank input; no threshold | `[X][VENDOR]` |
| **Leaderboard vs account PnL** | If official 30d is profitable but account-derived 30d is not, exclude (1,935 wallets) | Hyperank `[X]` |
| **Minimum copy capital** | Smallest wallet that can replay the book given HL $10 min order; median $386 | Hyperank `[X][VENDOR]` |
| **Trades per day** | 817/day rejected as MM in Whale Street demo (treat as hint, not law) | `[X]` |
| **Exit window** | Seconds from smart-money first sell to −1% adverse; example 67 s | Exit Window `[X]` |
| **Flock** | 2+ watched smart wallets same side within 15 min | PerpPilot `[X]` |
| **Volume present in same window** | Drop $0-volume rows (holders). Minara: all-time vol ≥ $1M, 30d vol ≥ $100k | Cipher, Minara |
| **Copy-fee share** | HyperX veto when copy-fee share > 70% | HyperX `[X]` |

### 6.2 Every stated threshold, by source

**HyperX (`@hyperx_trade`, 2026-09-17 — "filter part 1")**

| Parameter | Value |
|---|---|
| Total score | > 40 |
| Profit component | > 60 |
| Stability component | > 50 |
| Risk-control component | > 50 |
| Win rate | > 50% |
| PnL | > $20,000 |
| Leverage (as written in the raw summary) | "> 1x" — ambiguous; confirm wording |
| Account value | > $20,000 |
| Fill-derived realized PnL | > $10,000 |
| Completed trades | > 10 |
| ROI band | 20%–50% (avoid 100x small-account lottery) |
| Median trade duration | > 1 h |

**HyperX (2026-09-24 — "filter part 2")**

| Parameter | Value |
|---|---|
| Equity curve | upward |
| Max drawdown | exclude > 50% |
| Recovery Factor | drop if > 1000 (anomaly filter) |
| Veto: inactive | no fills in 30d |
| Veto: equity | < $10k |
| Veto: average hold | < 3 minutes |
| Veto: leverage | > 25x (use historical average) |
| Veto: margin usage | > 90% |
| Veto: tags | big-loser / high-risk |
| Veto: copy-fee share | > 70% |
| Prefer | active cycle > 2 months; hold distribution > 1 h |
| Then | copy at *reduced* leverage/size |

**lucas_faster (30d window, 2025-05-05)**: win rate ≥ 70% · equity ≥ $10k · realized ≥ $10k · completed trades 5–100 (> 100 ≈ bot) · ROI ≥ 50% · kill jagged curves · prefer many good trades over one lottery hit.

**MinaraCN (2026-09-01, 43,618-row dump)**: account value ≥ $10,000 · all-time PnL > 0 · all-time ROI > 0 · all-time volume ≥ $1,000,000 · 30d volume ≥ $100,000 · compare PnL/ROI across 1d/1w/1m/all-time windows (count of profitable recent windows feeds the score).

**Hyperank (fill audit)**: official 30d green but account 30d flat/negative → drop · min copy capital vs HL $10 ticket · starter wallet $100–$500 → fixed $15/order, 3 positions, 20% wallet stop-loss; leaders who enter in 1–2 clips (not 10 scale-ins).

**Niakris (author's own, Coinpilot-adjacent)**: DD ≥ 22% skip (aim < 15%) · last trade ≥ 7d · > 5 open positions · hold-time/style match (≥ 24h vs < 1h) · Sharpe ≤ 1.5.

**Cipher `[WEB]`**: skip $0-volume top-PnL rows · prefer 30d ∩ all-time · leverage 2–5x BTC/ETH · vault age > 1 year.

**thedefiedge**: copy at most 3 wallets · replicate net exposure · swing/position holds.

**reisner (examples, not cutoffs)**: OIL 30d DD 1.0%, WR 80%, Sharpe 13.15; equities 30d DD 20.2%, WR 79%, Sharpe 10.58.

### 6.3 Copy-sizing guidance (Hyperank, not universal law)

| Wallet size | Rules |
|---|---|
| $100–$500 on HL | Fixed $15/order · 3 positions · 20% wallet stop-loss · leaders that enter in 1–2 clips |
| $1k–$5k | Proportional · hold hours not minutes · stop-loss 25% · daily loss limit 10% |
| Reference stats | Median min copy: $386 (across 2,278 ranked) · proportional median $481 · fixed median $185 · score ≥ 90 copyable under $500: 17 of 39 · cheapest high score: 92 at $46 |

### 6.4 The ten most repeated heuristics (ranked by independent accounts)

| Rank | Heuristic | Independent mentions | Typical threshold if stated |
|---|---|---|---|
| 1 | **Don't rank on raw / short-window PnL** | Chase; Hyperank; MinaraCN; LabelYX; thesogle; lucas (+ others) | Prefer 30d ∩ all-time; persistence R² 0.036 |
| 2 | **Inspect fills / equity curve, not the board row** | Hyperank; MinaraCN; lucas; HyperX; Lookonchain; OnchainLens | 1,935 board-vs-account disagreements |
| 3 | **Reject HFT / MM / too many positions / too-fast holds** | HyperX; lucas; Whale Street; totlsota; Bet-or-Book; thedefiedge | hold < 3 min or hist lev > 25x; 817 trades/day |
| 4 | **Drawdown / bad-period behaviour first** | C_Predecessor; Hyperank (639); HyperX; Niakris; thesogle; reisner | 15% vs 22% vs 50% — conflicting |
| 5 | **Volume and activity must exist in the same window** | Cipher; Minara; HyperX; Niakris | AT vol ≥ $1M, 30d vol ≥ $100k |
| 6 | **Deposit / ROI distortion** | Cipher official formula; HyperX ROI band; LabelYX outliers; Hyperank | `pnl / max(100, start + max net deposits)` |
| 7 | **Leverage and liquidation distance** | Hyperank (534 / 490); HyperX; Cipher; thesogle | Don't inherit whale leverage |
| 8 | **Copyability ≠ skill** (hold time, $10 ticket, exit lag) | Hyperank; HyperX; Exit Window; DexterOnchain | Small accounts: fixed $, not proportional |
| 9 | **Concentration / one-hit / linked books** | lucas; Minara; Whale Street; Lookonchain clusters; OnchainLens | "Multiple winning trades" + cluster check |
| 10 | **Win rate is weak alone** | Hyperank; Hyperdash 35% WR example; koolkrypto; HyperTrend anti-pattern | HyperX 50% / lucas 70% only after other filters |

Not in the top 10 because too few independent HL posts: Sharpe cutoff, profit-factor cutoff, Sortino, exact trade-count law.

### 6.5 Calibration study — persistence is near coin-flip
`@chase_mew_` (935k wallets, 1 year): top-10% → top-10% next month **19%**; random user profitable in a month **42.3%**; prior top trader profitable next month **45.5%**; R² **0.036** (the post also says "only half" are profitable — the author's rounding of the same 45.5%; Grok confirmed both lines, §14.1). Counter-view from `@koolkrypto223`: discretionary traders earn PnL in 3–5 large trades a year, so monthly rank is the wrong test for them. **Combined lesson:** filter uncopyable books first, then judge skill by risk behaviour across a losing stretch — not by last month's rank.

---

## 7. Agent architecture (schema, request graph, screen/vet rules)

> Everything in §7 is the research agent's **synthesis `[SYNTH]`** built from the thresholds in §6. Individual numeric floors are traced to a source; the *combination*, the 0.8 concentration cutoff and the 0–100 score are not posted by anyone on X. Read-only only: no agent wallets, no builder-fee approval, no MCP that takes a private key.

### 7.1 Canonical objects the agent should persist

```json
{
  "TraderCandidate": {
    "address": "0x…",
    "labels": ["string"],
    "sources": [{"tool": "string", "url": "string", "seen_at": "ISO8601"}],
    "board": {
      "account_value": "number|null",
      "pnl": {"1d": "n", "7d": "n", "30d": "n", "all": "n"},
      "roi": {"1d": "n", "7d": "n", "all": "n"},
      "volume": {"1d": "n", "7d": "n", "30d": "n", "all": "n"}
    },
    "style": {
      "vendor_style": "algo | scalp | intraday | swing | position | unknown",
      "direction_bias": "long | short | neutral | unknown",
      "median_hold": "seconds | null",
      "leverage_now": "n|null",
      "leverage_hist_avg": "n|null",
      "win_rate": "n|null",
      "sharpe": "n|null",
      "max_dd": "n|null",
      "trade_count_window": "n|null",
      "copy_score": "n|null",
      "hyperx_total_score": "n|null"
    },
    "book": {
      "is_vault": "bool",
      "is_protocol": "bool",
      "likely_mm_hft": "bool",
      "linked_cluster": ["0x…"],
      "open_positions": ["Position"],
      "liq_count": "n|null",
      "funding_pnl_30d": "n|null",
      "fee_usd_30d": "n|null",
      "realized_pnl_30d": "n|null",
      "net_pnl_30d": "n|null",
      "top_coin_pnl_share": "n|null"
    },
    "decision": {
      "stage": "discovered | screened_out | vet_fail | watch | promote",
      "reasons": ["string"],
      "score": "0-100|null"
    }
  },
  "Position": {"coin": "string", "side": "long|short", "notional": "n", "entry": "n", "liq_px": "n|null", "leverage": "n", "uPnl": "n"}
}
```
Enums to persist, not invent: `stage`, `vendor_style`, `direction_bias`. Add (from §8) a `dex` field to `Position` so HIP-3 coins like `xyz:XYZ100` are not lost, and a `borrowed_usd` field (manual borrows, §9).

### 7.2 Request graph (final, after the 90-day audit patch)

```
A discover_universe
   ├─ A1 official_leaderboard_json            (stats-data.hyperliquid.xyz/Mainnet/leaderboard)
   ├─ A2 hyperdash_explore_page               (hyperdash.com)
   ├─ A3 hyperx_discover_page                 (hyperx.trade/hyperliquid/wallet-discover)
   ├─ A4 hypertracker_leaderboard_api         (if token budget)
   ├─ A5 x_ingest_addresses                   (Lookonchain / OnchainLens / EmberCN / hypurrdash / HyperTracker)
   └─ A6 hypedexer /hip3/top-movers           (so HIP-3-only specialists are not dropped)
          │
          v
B screen_rules (+B2)      pure functions, no extra IO
          │
          v
C enrich_one(address)     bounded concurrency; run only on survivors of B
   ├─ C1 hypurrscan page                      (is_vault, TWAP slices)
   ├─ C2 info.allDexsClearinghouseState (+ clearinghouseState, spotClearinghouseState)
   ├─ C3 info.portfolio
   ├─ C4 fills: indexer (Hypedexer / Dune / Bitquery / Allium / Hydromancer) — NOT last-2k only; info.userFillsByTime only for the last ≤10k
   ├─ C5 info.userFunding + WS userNonFundingLedgerUpdates + info.subAccounts (+ per-child repeats)
   ├─ C6 arkham_cluster                       (only on Lookonchain-style multi-wallet suspicion)
   └─ C7 optional classifiers                 (Bet-or-Book, PerpPilot if Nansen key, Exit Window = monitor-only)
          │
          v
D vet_rules
          │
          v
E watchlist
   ├─ E1 ws.trades filtered to watched addresses   (≤ 10 user-specific subs / IP)
   ├─ E2 poll clearinghouseState / allDexsClearinghouseState (30–60 s)
   ├─ E3 HyperTracker / Proliquid / CoinGlass position-delta pages
   ├─ E4 weekly rescore via A1 + indexer
   └─ E5 cheap discovery feeds (t.me/perpyxyz, @MirrorlyLive) — parse 0x only; ignore nicknames until resolved
```
Fan-out cap: C is expensive — run it only on addresses that survive B.

### 7.3 Node notes

| Node | Notes |
|---|---|
| **A1** | `GET https://stats-data.hyperliquid.xyz/Mainnet/leaderboard` · UI twin `app.hyperliquid.xyz/leaderboard` · fields: address, account value, PnL/ROI/volume × 1D/7D/30D/all · tens of MB — snapshot, not stream · official ROI = `pnl / max(100, start + max_net_deposits)` |
| **A2** | Profile `https://hyperdash.com/address/{addr}` · filters and result columns in §3.3 · public page only; parse HTML/XHR if exposed; no public bulk API found |
| **A3** | `https://hyperx.trade/hyperliquid/wallet-discover`; profile `…/trader?address={addr}` · thresholds in §6.2 are from HyperX's Sep-2026 posts |
| **A4** | `https://docs.coinmarketman.com/endpoints/leaderboards` · adds wallet age, leverage, open exposure, directional bias, cohorts · 100 tokens/day free then paid · enrichment, not the universe |
| **A5** | Parse `0x[a-fA-F0-9]{40}` and `hypurrscan.io/address/0x…` from the five desks; store `source_post_id` + date; **do not treat a viral card as a pass** |
| **C1** | `https://hypurrscan.io/address/{addr}#perps` · vault/TWAP/spot tabs; sets `is_vault`; shows TWAP slices the fill cap may hide |
| **C2–C5** | Official endpoints; see §8 for exact weights/caps |
| **C6** | Only when deposits/withdrawals or "N new wallets" appear; merge scores at cluster level or one book is double-counted |

### 7.4 Screen function B — drop before any IO

Apply in order. Every numeric floor below comes from a found source (noted); the *composition* is `[SYNTH]`.

```
DROP if volume_30d == 0 AND volume_7d == 0           # holders, not traders (Cipher; 8/10 top 30d PnL had $0 vol on 2026-09-30)
DROP if account_value < 10_000                       # MinaraCN 2026-09-01
DROP if pnl_all <= 0 OR roi_all <= 0                 # MinaraCN
DROP if volume_all < 1_000_000                       # MinaraCN
DROP if volume_30d < 100_000                         # MinaraCN
KEEP_HINT if pnl_30d > 0 AND pnl_all > 0             # recent + lifetime overlap (Minara + LabelYX)
```

Optional **copy sleeve** — only if the goal is *followable* traders (HyperX 2026-09-17/24 + lucas 2025-05-05):

```
REQUIRE hyperx_total_score > 40                      # skip block if score missing
REQUIRE profit_component > 60 AND stability > 50 AND risk_ctrl > 50
REQUIRE win_rate >= 0.50                             # HyperX floor; lucas used 0.70 (30d)
REQUIRE pnl_all >= 20_000                            # HyperX
REQUIRE account_value >= 20_000                      # HyperX second pass
REQUIRE completed_trades >= 10                       # HyperX
REQUIRE completed_trades_30d <= 100                  # lucas: > ~100 ≈ bot
REQUIRE median_hold >= 1 hour                        # HyperX
DROP if max_dd > 0.50
DROP if leverage_hist_avg > 25
DROP if margin_usage > 0.90
DROP if no fills in 30d
DROP if account_active_span < 60 days
DROP if roi_all is extreme small-account lottery     # HyperX ROI band 20–50% = hint, not physics
```
Do **not** use win rate ≥ 70% as a hard global rule (Hyperdash: +$8.57M BTC book at 35% WR / 26 trades / $885M volume; high WR + low trade count is often concentration).

**B2 extra screen (second pass)**
```
DROP if official_30d_pnl > 0 AND account_30d_pnl <= 0      # Hyperank (1,935 wallets)
FLAG if trades_per_day >= 817                               # Whale Street demo; hint, not law
FLAG if min_copy_capital > your_sleeve                      # Hyperank $10-ticket math
```

### 7.5 Vet function D

```
VETO vault unless researching vault leaders on purpose
    # official vaults only: app.hyperliquid.xyz/vaults; no spot, no HIP-3; leader 5% skin / 10% profit share

VETO likely_mm_hft if median_hold < 3 min
    OR vendor tag HFT/MM
    OR add/reduce fill count >> completed round trips

VETO if top_coin_pnl_share > ~0.8 AND trade_count_window < 15
    # one-hit; 0.8 is [SYNTH]; if you need a posted rule use "multiple high-profit trades"

VETO if |funding_pnl| ≈ or > directional realized AND book is two-sided / inventory-like
    # Dexter: 90d funding −$155.9k vs fees $163.2k

FLAG (not auto-veto)  liq_count >= 1                   # 0x337afda… 7 liqs, still +$632k
FLAG                  linked_cluster size >= 3         # Lookonchain 11-wallet BTC→ETH rotation 2026-09-18
FLAG                  address in calibration set (§10)  # do not promote as "skilled discretionary"
EXCLUDE               0x4000… + dex_index              # HIP-3 backstop liquidator, not a trader
EXCLUDE               agent-wallet addresses           # queries return empty; resolve to master
SUBTRACT              borrowed USDC/USDT (manual borrows, 2026-09-18) from "trading equity"
```

**Score `[SYNTH]`** (weights sum to 100; **60 cutoff is pipeline synthesis, not a CT post**):

```
score =  25 * 1[pnl_30d>0 and pnl_all>0]
       + 15 * 1[volume_30d >= 100k]
       + 15 * clip(stability_or_smooth_equity, 0, 1)
       + 15 * 1[max_dd <= 0.5]
       + 10 * 1[2 <= lev_hist <= 10]          # Cipher prefers 2–5x; mid allowed
       + 10 * 1[median_hold >= 1h]
       + 10 * 1[not one_coin_dominated]
cap 100 · promote to watch if score >= 60 and no VETO
```

### 7.6 Worked request sequence (one address — an example from CT, not a recommendation)
Example address `0xbf732ea04197942783e34730ed6e0f6099575d58` (Hyperdash said #1 month realized +$12.3M on 2026-09-21).

```
1. A1: row has volume_30d > 0
2. GET  https://hyperdash.com/address/0xbf73…
3. GET  https://hypurrscan.io/address/0xbf73…#perps
4. POST https://api.hyperliquid.xyz/info   {"type":"clearinghouseState","user":"0xbf73…"}
5. POST …/info                              {"type":"portfolio","user":"0xbf73…"}
6. POST …/info                              {"type":"userFillsByTime","user":"0xbf73…","startTime":<30d_ms>,"endTime":<now>}
        # stop at 10k fills; if truncated → indexer (Hypedexer / Dune / Bitquery)
7. SQL  SELECT block_date, realized_pnl_usd, net_pnl_usd, fee_usd, funding_paid_usd, funding_received_usd, volume_usd
        FROM hyperliquid.perp_accounts_daily WHERE trader = '0xbf73…' AND block_date >= current_date - 30
8. Decide stage = watch | vet_fail
9. If watch: WS trades filtered to the address + poll clearinghouseState every 30–60 s + weekly A1 rescore
```
Rate-limit envelope: ~600 `clearinghouseState` calls/min/IP (1200 weight ÷ 2); fills are much heavier — serialize C4; never subscribe `userFills` WS for more than ~10 addresses per IP.

### 7.7 Watchlist event schema and re-vet triggers

```json
{
  "address": "0x…",
  "event": "open | add | reduce | close | liq | deposit | withdraw | cluster_transfer",
  "coin": "BTC",
  "notional": 0,
  "ts": "ISO8601",
  "source": "ws.trades | clearinghouseState | hypurrscan | hypertracker | proliquid | coinglass"
}
```
Recompute vet D on: a new liquidation · drawdown breach vs stored peak · 7d PnL flip while 30d still green (Liquary "crashed vs accelerating") · a cluster deposit that inflates account value. Auto-drop after a new liq cluster or DD breach.

### 7.8 Tool roles — what each is, and what it must *not* be used as

| Step | Use | Do not use as |
|---|---|---|
| Official JSON + `/info` + WS | Source of truth | A skill score by itself |
| HypurrScan | Vault/TWAP/human QA | A ranked screener |
| Hyperdash | Style, Sharpe, DD, copy score | An unvetted "top trader" list |
| HyperX | Followability thresholds | Proof of edge |
| HyperTracker API | Age, bias, alerts | "Money Printer" cohort as skill (>$1M realized+unrealized) |
| CoinGlass / Proliquid | Live size / liq pockets | Skill |
| Dune / Bitquery / Allium / Hydromancer / Hypedexer | History past 10k fills; funding vs directional | A finished leaderboard (none found) |
| Lookonchain et al. | Discovery + blow-up calibration | A copy list |
| Copy UIs (Dexly, HyperX copy, Hyperdash copy, Copin, vault deposit) | — | Out of scope for the research agent |

### 7.9 Still missing for a fully automated graph
No public Hyperdash/HyperX bulk API (A2/A3 may need page/XHR capture) · no posted profit-factor or Sortino cutoff · no Dune "% wallets in profit" dashboard URL · WS cannot monitor the whole universe — poll A1 daily and stream only the watchlist.

---

## 8. Data mechanics and API gotchas

### 8.1 Rate and history limits `[DOCS]` (re-read official page at run time)

| Item | Limit |
|---|---|
| REST budget (info + exchange, shared) | **1,200 weight / min / IP** |
| `clearinghouseState`, `allMids`, `l2Book`, `spotClearinghouseState` | weight **2** (≈ 600/min) |
| Most other info calls incl. `openOrders`, `userFills*` | weight **20**, **+1 per 20 rows returned** (≈ 60 calls/min before row surcharge) |
| `userRole` | weight 60 |
| Explorer calls | weight 40; old blocks heavier — use S3 for bulk |
| `userFills` | ≤ **2,000** most recent fills per response |
| `userFillsByTime` | ≤ 2,000 per call; only the **~10,000 most recent** fills exist on the public node API |
| TWAP history (`userTwapSliceFills`, `userTwapHistory`) | cap 2,000 |
| `candleSnapshot` | most recent **5,000** candles only |
| WS per IP | 10 connections · 30 new connections/min · 1,000 subscriptions · **10 unique users** on user-specific subs · 2,000 msgs/min · 100 in-flight posts · idle close after 60 s without ping |
| Public WS `l2Book` | 20 levels per side (full L4 incl. HIP-3 is a commercial feed: DoubleZero Edge, or S3 book diffs) |
| Builder fee cap | 0.1% (per raw file) |

WS unique-user cap: official = **10**. The nktkas/Bloxwap transport notes a live probe where the 15th user was refused and guards at **14** — treat 10 as documented-safe, 14 as observed-unverified.

### 8.2 Seventeen developer gotchas (G1–G17)

| ID | Topic | Gotcha → fix |
|---|---|---|
| G1 | Fill-history cap | `/info` is not an archive (2k/call, 10k total). Paginate `userFillsByTime` by last timestamp for the last 10k only; older → Hypedexer (fills since Nov 2024) or requester-pays S3. Hit by `@Yaugourt` (09-16), `@CryptoAddict31x` (09-15), `@0xArchiveIO` (07-04) |
| G2 | Three fill schemas in S3 | `node_trades` (side_info array) → `node_fills` (user + fill object) → `node_fills_by_block` (block envelope + builder attribution, from 2025-07-27). Branch the parser on the S3 prefix or fields silently drop. Buckets: `s3://hyperliquid-archive/`, `s3://hl-mainnet-node-data/` (requester-pays, LZ4) |
| G3 | REST weight budget | See §8.1; prefer WS snapshots for live books; don't scrape the explorer for history |
| G4 | WS caps are per IP | One multiplexed socket; send pings; first `userFills`/`userFundings` frame is `isSnapshot:true` |
| G5 | `closedPnl` ≠ account PnL | `Fill.closedPnl` is PnL closed by that fill only — misses funding, deposits/withdrawals, liquidations, vault equity, builder/deployer fee split, HIP-3 collateral units. Recipe in §8.3 |
| G6 | Agent wallet vs user address | Querying an API/agent wallet returns **empty**. Use the master or sub-account that owns the book; nonces are per signer |
| G7 | Subaccounts and vaults are separate addresses | Subaccounts are separate users for rate limits and state. Vault PnL is not in the master `clearinghouseState`. Call `subAccounts(user)`, then repeat per child; vaults: `vaultDetails(vaultAddress)` + `userVaultEquities(user)`; never mix vault follower equity with trader fills |
| G8 | HIP-3 default-dex blind spot | Empty `dex` = first perp dex only. HIP-3 coins are prefixed (`xyz:XYZ100`); `openOrders`/`clearinghouseState`/`allMids` without `dex` miss xyz/io books; spot open orders only on the first perp dex. Use `allDexsClearinghouseState` + `allDexsAssetCtxs`; prefix coins everywhere (candles too). `@shridlock` 2026-09-23: HL API OI $16.70B = $12.71B main + $3.91B xyz |
| G9 | HIP-3 backstop liquidator | Address `0x4000…0000 + dex_index` (first HIP-3 dex `…0001`) — fills against it are venue backstop, not a trader. Node flag `--write-user-account-summaries <dex>` writes hourly `a`=accountValue, `b`=balance=accountValue−unrealizedPnl |
| G10 | HIP-4 markets vanish | Purged from the node API shortly after settle (coin, candles, book, votes) — `@liquary_xyz` 2026-09-09. Index while live; Liquary Data keeps an archive |
| G11 | Builder fees double-count | `fee` is the **total, inclusive of `builderFee`** — don't add it again. `feeToken` may not be USDC. `builderFills` / `builderFillsByTime` (2k cap) exist on GoldRush/Dwellir/Hypedexer, not official `/info` |
| G12 | TWAP is a separate tape | Parent TWAP ≠ slice fills. Pull `userTwapSliceFillsByTime` + `twapStates`; Hypedexer `GET /twaps/stats`. 24h snapshot (`@Yaugourt`): 3,101 TWAPs, 52.9% finished, 29.4% terminated |
| G13 | `aggregateByTime` changes trade counts | `userFills.aggregateByTime=true` merges partials; win-rate/trade-count screens flip if paths differ. Pick one and persist it; keep raw (`false`) for copy-fitness so scale-in clip count is visible |
| G14 | Liquidation vs fill | Liqs appear both as fills (`dir` contains "Liquidate") and as ledger updates; backstop/ADL are distinct. Join `fills.dir ~ [Ll]iquidat` with `userNonFundingLedgerUpdates`; drop `0x4000…` |
| G15 | Public L4 vs uncapped feed | Public WS L2 is 20 levels/side; full L4 incl. HIP-3 is not the default public path (`@doublezero` 2026-09-24). Public `l2Book` + trades is enough for trader research; MM reconstruction needs Edge or S3 book diffs (`node_raw_book_diffs_by_block` from 2026-01-22) |
| G16 | Candle cap | Only the most recent 5,000 candles (`@Kosumi1989`); build your own store or use Hydromancer Reservoir / 0xArchive |
| G17 | Unified account balance | Under unified/portfolio margin, `spotClearinghouseState` is the source of truth for trading-account balance across spot + perps — not perp clearinghouse USDC alone |

### 8.3 PnL recipe the agent should use

| Component | Source |
|---|---|
| Realized from fills | `sum(fill.closedPnl)` over the **complete** fill set (not last 2k) |
| Fees | `sum(fill.fee)` — already includes `builderFee`; don't add it again |
| Funding | `userFunding` / WS `userFundings` (hourly); not in fills |
| Transfers & liquidations | WS `userNonFundingLedgerUpdates` (deposits, withdrawals, transfers, liquidations) |
| Mark-to-market | `clearinghouseState.assetPositions[].unrealizedPnl` + `marginSummary.accountValue` |
| Official board ROI | `pnl / max(100, start + max_net_deposits)` (Cipher writeup; no 2026 X developer thread restates it) |

`net_trading_pnl = Σ closedPnl − Σ fee + Σ funding ± ledger liquidation residues`
Dune equivalent: `net_pnl_usd = realized_pnl_usd − fee_usd + funding_received − funding_paid` (open uPnL **not** included).
**Inputs:** `info.portfolio`, `clearinghouseState` + `allDexsClearinghouseState`, `spotClearinghouseState`, `userFillsByTime` (paged) or indexer fills, `userFunding`, `subAccounts` + per-child repeats, `userVaultEquities` + `vaultDetails`, WS `userNonFundingLedgerUpdates`.
**Do not:** use the official 30d leaderboard PnL as account PnL (Hyperank: 1,935 mismatches) · add `builderFee` on top of `fee` · treat HIP-3-prefixed coins as missing · query the agent wallet.

### 8.4 Known request payloads (as given in the raw file)

```
POST https://api.hyperliquid.xyz/info
{"type":"clearinghouseState","user":"0x…"}                         # positions, uPnL, liqPx, leverage, margin — weight 2
{"type":"portfolio","user":"0x…"}                                   # accountValueHistory / pnlHistory / vlm by day/week/month/all
{"type":"userFillsByTime","user":"0x…","startTime":…,"endTime":…}   # ≤2,000/call; ~10k most recent only; weight 20 + 1/20 rows
```
Other info `type` names seen (parameters: see official docs, not given in the raw file): `allDexsClearinghouseState`, `allDexsAssetCtxs`, `spotClearinghouseState`, `userFunding`, `subAccounts`, `vaultDetails`, `userVaultEquities`, `userTwapSliceFillsByTime`, `twapStates`, `openOrders`, `userRole`, `allMids`, `l2Book`, `candleSnapshot`.

### 8.5 Other data-quality traps

- **Official ROI already deposit-adjusts**; third-party ROI often does not (hence LabelYX's +2,641,203% rows).
- **Leaderboard PnL includes holders** whose equity rose with spot/HYPE — filter volume > 0 in the same window.
- **Vault PnL is pooled**; leader needs only 5% skin and takes 10% of profits; vaults: no spot, no HIP-3; closed/failed vaults vanish (survivorship). Only vaults on `app.hyperliquid.xyz/vaults` are official; 94.4% of 9,466 vaults hold < $1k (`@harmonixfi` quoting zooted_max, 2026-09-17).
- **Linked wallets:** Lookonchain routinely clusters 3–11 "new" wallets as one whale; single-address scores understate books.
- **Realized vs unrealized** definitions differ across tools (HyperTracker Money Printer = both; HyperPulse realized excludes open positions).
- **Win-rate definitions differ** (round trips vs fills vs days); ignore any vendor WR you cannot recompute from fills (HyperTrend printed 114%).
- **Position notional sometimes marked at entry** (PerpFinder) not mark.
- **Copy latency + builder fee (cap 0.1%)** kills sub-1h / ~0.1%-edge scalps even if the leader is skilled.
- **Leaderboard JSON** is tens of MB — batch snapshot, not a streaming API.
- **Nansen "Smart HL Perps Trader"** is a labelled subset; PerpPilot, Exit Window and Bet-or-Book inherit that label bias.
- **HL $10 minimum order** makes proportional copy on small accounts systematically incomplete.
- **Hackathon repos** (PerpPilot, Bet or Book, Exit Window, Whale Street) may not stay hosted — prefer clone-and-run over SaaS URLs.
- **Mirrorly Live names** are product nicknames; resolve to `0x` before scoring.
- **Fake non-official vaults:** anything not on `app.hyperliquid.xyz/vaults` is a third-party contract.

---

## 9. What changed in the last 90 days (2026-07-01 → 2026-10-01)

### 9.1 Protocol changes that break older methods
| Date | Change | Why old methods break |
|---|---|---|
| 2026-09-18 | **Manual borrows live** (`@HyperliquidX`): $269M borrowed day one, HYPE/BTC collateral for USDC/USDT (the 65% / 50% LTVs the raw file cites are **not** in the official post or image — unverified) | Account value ≠ trading equity; borrowed USDC/USDT inflates buying power. Deposit-adjusted ROI and "skin in the game" screens must subtract borrow. CoreWriter/precompiles let HyperEVM apps tap the same pool |
| 2026-09-24 | **HIP-3 mark on-chain (testnet)** (`@HansonBirringer`, `x.com/HansonBirringer/status/2103099378840088842`): mark from three inputs incl. the HL main market; deployer no longer sets mark directly; allowlists, reduce-only, forced close, halts, OI caps, per-market backstop | HIP-3 books can't be scored as the same DEX as BTC-PERP; need `dex` / `allDexsClearinghouseState`; backstop `0x4000…+dex_index` is not a trader |
| mid-Sep | **HIP-3 funding clamps configurable** by deployer (`@HypeStatsx` 2026-09-18: "on the next network upgrade"; earlier jeff_hl attribution not found) | Funding income on xyz books is a deployer parameter, not a global HL constant |
| 2026-09-09 → | **HIP-4 markets purged after settle** (`@liquary_xyz`) | Node API history vanishes; missing HIP-4 fills ≠ a trader going quiet |
| 2026-09-24 | **DoubleZero Edge** uncapped L4 incl. HIP-3 | Public `l2Book` (20 levels) is no longer "the book" |
| 2026-09-16/17 | **Hypedexer V2 + MCP** (no explicit V2 launch post found; MCP shown in use 09-17) | The 2k/10k fill cap is now an acknowledged product gap |
| Jul–Sep | HIP-3 share of OI/volume is large (`xyz` ~$3.9B of $16.7B in one split) | Leaderboard + `clearinghouseState` with empty `dex` **undercounts** specialists on xyz/io |

No X post in the window announced a **leaderboard schema change**; Cipher 2026-09-30 still reads the board as 46,904 accounts with windows 1d/7d/30d/all-time. The invalidation is **coverage** (HIP-3, borrows, HIP-4 purge), not a new JSON shape.

### 9.2 New or changed tools
Hypedexer MCP/REST/WS (live Sep 15–29; Trust Wallet + hl.eco partner) · Hyperank public beta (Sep 20–27) · Hyperdash domain now `hyperdash.com` (handle unchanged; copy + analytics still shipping, Seoul week Sep 30) · HyperTracker Sep 30 builder-code volume post and `.hl` names integration (`@hlnames`) · HyperX still posting 90d screens Sep 30 · Exit Window / Bet-or-Book / PerpPilot (Meridian hackathon, durability unproven) · **`@2oolkit/hyperliquid-cli` 0.2.2 flagged MAL-2026-3679 (2026-09-30)**.

### 9.3 Phishing / impersonation (also in §11)
| Campaign | Evidence | Agent rule |
|---|---|---|
| Fake X orgs / "claim" posts | `@Hyperliquid_Hub` 2026-09-29: report `@Hyperliquid_Eco` impersonator | Official handle is `@HyperliquidX` only |
| "Fake Hyperliquid tweet scammers" | `@1049XBT` 2026-09-28 | Ignore claim/airdrop tweets |
| Google-ads Inferno Drainer `[WEB]` (not found on X) | Deep Guard: ~2026-08-13, **550,019 USDC** via fake HL UI; protocol not hacked | Never open HL from search ads |
| Lookalike domains `[WEB]` (not found on X) | OneKey (May, still cited): `hyperiiquid.xyz`, `.net/.io/.vip`; official support cites `hyperliguid.xyz` | Hard-code official hosts |
| Automated URL scanners `[WEB]` (not found on X) | emailveritas scored `hyperliquid.xyz` "phishing" 2026-09-25 — **scanner false positive** | Don't let generic scanners override known official hosts |
| npm MCP/CLI `[WEB]` (not found on X) | `@2oolkit/hyperliquid-cli` silent builder fee | Ban unsigned "HL MCP" packages |

Official hosts: app `https://app.hyperliquid.xyz` · API `https://api.hyperliquid.xyz` · WS `wss://api.hyperliquid.xyz/ws` · leaderboard snapshot `https://stats-data.hyperliquid.xyz/Mainnet/leaderboard`.

---

## 10. Calibration set — public addresses (every row is a **[CLAIM]**: verify on-chain)

Rule from the raw file: include an address only if posted by its owner or an established on-chain analyst; never de-anonymize beyond the post. Attributions (Wintermute / Abraxas / Machi / Garrett Jin / pension-usdt) are **the analyst's label, not a finding**. Public 12+-month *discretionary* winners with a posted `0x` and independent vouchers are scarce; most CT "winners" are 30-day cards. The only long-lived, repeatedly posted profitable books here are institutional/MM or mixed-hedge funds — useful as calibration, **not as copy targets**.

### 10.1 "Positives" (durable or notable — none is a certified 12-month discretionary edge)

| ID | Address | Posted by | Claim (as posted) | Duration evidence | Role / caveat |
|---|---|---|---|---|---|
| **P1** | `0xecb63caa47c7c4e77f60f1ce858cf28dc2b82b00` | `@OnchainLens` 2026-09-28 (140 likes; supporting `@iamalijandro`, `@Coin_Scoop`) | Labelled Wintermute. Lifetime PnL **+$197.22M**; snapshot shorts $126.25M (ETH $46.92M, SOL $11.30M, HYPE $10.03M); uPnL ≈ +$963.6K. Separate Aug-2026 snapshot: lifetime +$203.55M, both-side book | HypurrScan/hl.eco first-seen ≈ 550 days before 2026-10-01 (~18 months); Arkham entity page spans 2024-01-20 → 2026-09-27; Jan snapshot cited ~$101.7M bids / $97.2M asks | **Durable book, NOT a directional copy** — MM/hedge/two-sided inventory. Wintermute has not confirmed the wallet in retrieved posts |
| **P2** | `0x5b5d51203a0f9079f8aeb098a6523a13f298c060` (cluster also `0xb83de012dba672c76a7dbbbf3e459cb59d7d6e36`) | `@Hyperliquid_Hub` (citing gHypurr) 2026-09-28; `@pnlsdaily` 2026-09-21; `@0xZecup` 2026-09-30 | Labelled Abraxas Capital. ~$859M perp exposure vs ~$172M equity (~5x); 30d perp PnL **−$53M**; funding collected ~+$17.3M (~$7.6M from HYPE); all-time portfolio PnL **+$92.8M**; later a $56.4M ZEC short. On 2026-09-21: ~$1.2B shorts, **>$100M uPnL loss** while accumulating spot ETH | "All-time" implies multi-month; **12+ month start date not stated** | **Carry + hedge, not a retail directional template** — copying the visible short without the spot/options leg is the classic trap |
| **P3** | `0xbf732ea04197942783e34730ed6e0f6099575d58` | `@lookonchain` 2026-07-20 (307 likes); `@VietnamPenguin`; Hyperdash later; `@jodezXBT` 2026-09-30 | Jul: 10x long 764.14M PUMP; VietnamPenguin: ~$9.6M all-time PnL, "consistently profitable". Sep: Hyperdash #1 month realized ≈ +$12.3M; still top-25 by 30d PnL on 2026-09-30 opening an $8.54M 40x BTC short. `@Hyperbotai` 2026-09-30 posts it as "Boomer-linked" (Boomer = `@solanadoomer1`; 2.32B PUMP long ≈ $13.64M, equity ≈ $1.28M); Hyperdash 09-21 names `@solanadoomer1` #1 by 30D net realized PnL **+$12,270,577.85** with a $35M ETH long (**Grok-verified**; the nickname link is Hyperbot's, not the owner's) | Public tape ≈ 2026-07-14 → 2026-09-30 (~2.5 months); **12+ months not posted** | **Watch-only candidate.** High-leverage clips (10x PUMP, 40x BTC); "consistently profitable" is a practitioner's gloss, not a 12-month Sharpe |
| **P4** | `0x469e9a7f624b04c24f0e64edf8d8a277e6bf58a5` | `@VietnamPenguin` citing the Lookonchain PUMP tape (2026-07-20) | Longed ~1B PUMP (~$2M) near $0.002 alongside 0xbf73; stated all-time PnL ~$12.5M, "consistently profitable" | Single July 2026 mention | Thin file; **do not promote without a fresh official portfolio pull** |
| **P5** | `0x3b11267dfc4b9ebe8427e8f557056b4b6ce98112` | `@reisnertobias` 2026-04-29 (59 likes) | Best OIL trader on HL; all-time PnL **+$1.4M**, volume ≈ $62.3M; 30d DD 1.0%, WR 80%, Sharpe 13.15; found on Hyperdash; alerts via `@lit_trade` | All-time posted; calendar span **not** posted | Point-in-time snapshot; Sharpe 13 is extreme — recompute |
| **P6** | `0xe6503009ee1a648c3775b6b8444afdddb786f1a9` | `@reisnertobias` 2026-04-29 (42 likes) | Equities trader; 30d DD 20.2%, WR 79%, Sharpe 10.58 | 30d only | Outcome unknown after 2026-04-29 |

### 10.2 "Negatives" (blow-ups, MM/hedge books mistaken for skill, and copy traps)

| ID | Class | Address | Claim / outcome | Copy trap |
|---|---|---|---|---|
| **N1** | Hyped, then net-loss exit | `0x92ea19ECeB7a8dE0f50978A1583A5D8b018050e9` (labelled Garrett Jin, `@GarrettBullish`) | Lookonchain timeline: 2026-06-17 sold 184,102 HYPE +$2.83M; 09-19 largest ZEC short uPnL **−$33.66M** (BTC long +$4.5M); 09-21 closed BTC long +$8.38M, flipped 500 BTC short; 09-24 withdrew 147M USDC to Binance, **lost $14.7M on HL over ~4 months** despite +$11.20M ZEC short and +$8.38M BTC long — one ZEC short (**−$35.44M**, `@Perps_AI` recap) erased both | Any single winning screenshot was copy-bait; full window is red |
| **N2** | Hyped whale, then liquidated | `0x0ddf9bae2af4b874b96d287a5ad42eb47138a902` (pension-usdt.eth, display name only) | Pre-liq lifetime PnL ≈ +$17.76M, lifetime volume > $12B; ETH short ~50k ETH / > $100M on a ~$16M account; liquidated ≈ 2026-08-20 04:51 CST at ≈ $2,235.36, ≈ $111.34M notional; realized loss ≈ **$16M (AiCoin)** to **$26.66M (BitcoinWorld/OnchainLens)** — figures disagree (§13) | Copying a green-lifetime whale into a max-leverage ETH short; nickname "pension" ≠ risk process |
| **N3** | High-variance public whale | `0x020ca66c30bec2c4fe3861a94e4db4a498a35872` ("Machi Big Brother") | Still opening 40x BTC (275 BTC clips mid-Sep); lifetime ≈ **−$29.22M** (OnchainLens 2026-09-28); live tracker address 2026-09-30 (`@Hyperbotai`) | Size + fame ≠ edge; fade-Machi products exist because the book is a spectacle |
| **N4** | MM mistaken for directional | `0xecb63caa47c7c4e77f60f1ce858cf28dc2b82b00` (same as P1) | Headlines "$126M shorts"; analysts in-thread: two-sided quotes, spot/options hedge, funding, client flow | Mirroring the short without the other venue legs |
| **N5** | Fund hedge mistaken for directional | `0xb83de012dba672c76a7dbbbf3e459cb59d7d6e36` (cluster with `0x5b5d5120…` as Abraxas) | $1.2B short book, > $100M uPnL loss while accumulating spot ETH — hedge/basis per `@KaiVenn__`; still on late Sep; funding collected on sister wallet | Copying HL shorts and missing the spot long |
| **N6** | Class: leaderboard "farmer" pattern | none | 1,935 wallets green on official 30d, flat/negative at account level (`@hypeRankio`) | Sorting official 30d PnL and copying row 1 |
| **N7** | Class: persistence failure | none | Chase: 935k wallets; top-10% → top-10% 19%; R² 0.036 | Monthly hero boards |
| **N8** | Class: zero-volume leaderboard row | none | 8 of the top 10 by 30d PnL had $0 30d volume (Cipher recap 2026-09-30) | Copying a 30d PnL sort |
| **N9** | Class: sybil / rotation cluster | none (list not recoverable) | Lookonchain 2026-09-18 (`x.com/lookonchain/status/2100835870219923791`): 11 newly created wallets, over **3 days**, sold 602 BTC (**$45.83M**) and bought 18,780 ETH ($45.83M), "likely the same whale"; 5-day follow-up (09-21): 1,107 BTC ($86.76M) → 34,422 ETH, staked. Only prefixes 0x082, 0xa05, 0x6Ba, 0xAB9 are visible in the images (**Grok-verified; earlier "same day, ~$20M" was wrong**) | Scoring 11 "traders" that are one book — the full 0x list is not in the post |
| **N10** | Copy-product fit but HFT/MM | `0xb7e0b9fbc9479330d70bcc82a7d4325a20e8d1aa` (full hex confirmed in the post) | `@DexterOnchain` 2026-09-18: HyperX 90d score 84.3, copy-fit **100.0** AND tagged HFT/MM + Direction Neutral + Large Capital; marketed as copy #1 of 511; 90d realized $6.84M over 98 round trips; 90d funding −$155.9k vs fees $163.2k. Grok B11 full article: **first trade 2026-05-10 (<5 months old)**, all-time realized only $6.48M over 170 round trips (below the 90d figure), open positions all short at 25.0x average leverage with −$756.8k unrealized, HyperX's own caveat "reconsider if median hold <10 min, copy-fit <15 or quiet 7 days" | Vendor copy score without fill/funding split; short history; leverage ignored by copy-fit |
| **N11** | Class: high WR, low trade count | none | CoinClass rows with 100% WR / 12–20 trades | Concentration, not process; re-pull before freezing any 0x |

**Other single-address calibration rows (from first pass)**

| Address | Claim | Lesson |
|---|---|---|
| `0xdd53C5297309130ab5fe5623DC905752E3342b13` | $124.59M shorts, 30d PnL −$30.04M (OnchainLens 2026-09-18) | Size ≠ skill |
| `0x337afda118de433f5a8c8ad6d6ef48b76d027a06` | 7 lifetime liquidations yet +$632.0k lifetime perps, but 30d +$630.1k (i.e. nearly all of it is recent); net realized +$421.6k; largest loss −$207.2k (OnchainLens 2026-09-08, Grok-completed) | Liquidation count is a flag, not an auto-veto; a lifetime figure that is ~100% last-30d is a short history |
| `0x9c6a5b4662c722d2c47f43d6c9813cb080ffa4ed` | 550,000 SOL long from $80.8, +$22.43M uPnL on 2026-09-27; TWAP plan 500,000 SOL, 186,000 filled at avg $76 (quoted 08-09 post) (`@EmberCN`, Grok-completed) | Example of a multi-week follow; one position, not a method |
| `0x77375a8c9d13bf79afb2a87f1b0ac1dfd5f5bf66` (`@mk4_lul`) | Lifetime +$57.04M (spot+perp), 30d +$14.17M, open $43.63M (NEAR long $28.48M 10x), **25 liquidations**; Minara classes it a directional day trader (OnchainLens 2026-09-26) | Huge PnL with a high liquidation count — watch-only |
| `0xf5629393e446a103a4be1c49a956255e7c87c1d3` | Sold 25,001 **spot** ZEC ($37.84M) bought at ~$425, >$27M profit (Lookonchain 2026-09-29) | Spot trade, not a perp-skill sample |

### 10.3 Calibration use
- **Must not be promoted as skilled discretionary:** `0xecb63caa…2b00`, `0xb83de012…6e36`, `0x5b5d5120…c060`, `0x020ca66c…5872`, `0x92ea19EC…50e9`, `0x0ddf9bae…a902`.
- **Watch-only candidates:** `0xbf732ea0…5d58`, `0x469e9a7f…58a5`, `0x3b11267d…8112`, `0xe6503009…f1a9`.
- **Tests a scorer should pass:** (1) label P1 as MM/hedge despite +$197M lifetime; (2) label N1 as fail despite multiple million-dollar winning clips; (3) label N2 as fail despite +$17.76M lifetime pre-liq; (4) do not emit P3/P5 as 12-month certified edges; (5) drop official-board 30d greens that fail account 30d (N6).

> **Reading guide from the raw file:** *"Read this set as labels, not a hall of fame."* The only address that clearly clears "12+ months + public + repeatedly vouched + still green" is the Wintermute-labelled book — and every serious desk in the thread says that book is the wrong thing to copy.

---

## 11. Security and scope guardrails (hard rules for the agent)

1. **Read-only.** Never hold or request a private key, agent wallet, API wallet, or builder-fee approval. Never run an MCP/CLI that takes `HYPERLIQUID_PRIVATE_KEY`.
2. **Query the master/sub-account address**, never the agent wallet (returns empty) — resolve agent → master first.
3. **Hard-code official hosts:** `app.hyperliquid.xyz`, `api.hyperliquid.xyz`, `wss://api.hyperliquid.xyz/ws`, `stats-data.hyperliquid.xyz`. The only official X handle for announcements is `@HyperliquidX`. Never open HL from search ads. Don't let generic URL scanners override known official hosts (emailveritas false positive, 2026-09-25).
4. **Ban unsigned npm/GitHub "HL MCP/CLI" packages** that ask for keys; `@2oolkit/hyperliquid-cli` 0.2.2 is flagged malicious (MAL-2026-3679). Exclude: edkdev, Dakkshin, patricleehua, 0xikalgo MCPs; `@liquidbots` MCP; Scarlett.ai; Senpi 45-tool execution suite; all copy UIs.
5. **Ignore** claim/airdrop tweets and impersonators (`@Hyperliquid_Eco`).
6. **Only vaults on `app.hyperliquid.xyz/vaults` are official.**
7. **Grok C06 could not find on X** the Inferno Drainer / 550,019 USDC, `hyperiiquid.*`, emailveritas or MAL-2026-3679 items (they are [WEB]-sourced); the only X-confirmed items are the `@Hyperliquid_Eco` impersonator and a scammer complaint. **No named HL drainer domain was independently confirmed** in the retrieved posts — do not invent names. Cited incidents: Inferno Drainer via Google ads (~2026-08-13, 550,019 USDC; protocol not hacked); lookalike domains `hyperiiquid.xyz`, `.net/.io/.vip`, `hyperliguid.xyz`.
8. **Treat every address attribution as a claim** (Wintermute/Abraxas/Machi/Garrett Jin/pension-usdt) and every vendor score as a hint.
9. **Hackathon tools may disappear** — prefer clone-and-run or the official API over SaaS URLs.

---

## 12. Audit of the "first-pass top 15" (liveness and trust)

The raw agent *reconstructed* the original top 15 from its must-use set, so treat this as an audit of the stack, not of a literally recorded list.

| # | Item | Live? | Last-90d activity | Complaints / trust | Verdict |
|---|---|---|---|---|---|
| 1 | Official info API + WS | Yes (`@shridlock` split 09-23) | Borrows, HIP-3, HIP-4 | 2k/10k fill cap; WS 10 users/IP; default-dex blind | **KEEP** — required, incomplete alone |
| 2 | Official leaderboard JSON / board | Yes (Cipher 09-30: 46,904 rows) | Still 1d/7d/30d/AT | $0-vol tops; board≠account (1,935) | **KEEP as discover only** — don't score from it |
| 3 | Official docs (gitbook) | Yes | Rate limits, HIP-3 deployer, nonces | Fast-moving; fetch `.md` | **KEEP** |
| 4 | `app.hyperliquid.xyz` | Cited live Sep 30 | Manual-borrow UI | Phishing clones | **KEEP as venue**; not a research API; never from ads |
| 5 | HypurrScan | Yes (CT pastes `#perps` links Sep 17–24) | Default 0x printer | Labelled "Beta" in older pulls | **KEEP** (read-only) |
| 6 | Hyperdash | Yes (`hyperdash.com`; Seoul 09-30; trader cards 09-23) | Copy product + US/HIP-3 article | Copy path = execution (out of scope); host renamed from hypurrdash.app | **KEEP analytics; flag copy module; update URL** |
| 7 | CoinGlass HL whale tracker | Cipher 09-30 still lists it | Not loaded independently this pass | Alerts behind account | **KEEP scan layer** (not a skill filter) |
| 8 | Nansen HL perps | Product live | "Smart HL Perps Trader" label | Label bias; paid | **KEEP as optional classifier** |
| 9 | Arkham | Quiet this 90d on HL method posts | Entity tags (Wintermute) | Paywall; sparse HL CT | **DOWNGRADE to entity-resolve only** |
| 10 | Lookonchain | Live (Garrett 09-17/24, 328k views) | Gold-standard tape | Headlines omit hedge context unless you read replies | **KEEP** |
| 11 | HyperTracker | Live (Sep 30 builder-code post; hlnames 09-29) | Cohorts + alerts | Free dashboard per Cipher | **KEEP (upgrade vs first pass)** |
| 12 | HyperX | Live screens 09-30 | Numeric filters | Copy-fit can tag HFT/MM | **KEEP filters; distrust copy-score = 100** |
| 13 | Dune / Flipside HL trader boards | **Not found as X-verified live trader dashboards** | — | First-pass "maybe Dune" stays a gap | **DEAD-FOR-PIPELINE as a leaderboard** (Dune *tables* remain valid as a warehouse) |
| 14 | ASXN / HyperStats | Wiki still lists ASXN + Hyperliquid Stats | Weak X footprint | Already weak in first pass | **DOWNGRADE (unverified-for-agent)**; don't block on them |
| 15 | Official Python SDK + Cipher/LabelYX guides | SDK used Jul (v0.24.0 test); Cipher 09-20/30 current | Guides match current board size | SDK signs — info-only wrap; guides are blogs, not APIs | **KEEP docs; SDK = info module only** |

**Must-add since the first pass:** Hypedexer (archive/MCP) · Hyperank method (board vs account) · `allDexs*` calls.
**Dead / renamed / paywalled / distrusted:** Hyperdash host renamed to `hyperdash.com` · Dune trader scoring not found · ASXN/HyperStats unverified for automation · Nansen/Arkham paywalled for depth · `@2oolkit/hyperliquid-cli` malicious · fake `@Hyperliquid_Eco` and ad-clone apps hostile.
**Bottom line:** nothing in the official trio (API, board, HypurrScan) is dead. What aged out is treating that trio as *sufficient* — borrows, HIP-3 books, HIP-4 purge and the 10k fill wall all landed inside the last 90 days.

### 12.1 Final pipeline after the audit
```
discover   official board JSON + CoinGlass large-OI scan (+ Hypedexer /hip3/top-movers)
hydrate    HypurrScan + official allDexs state + Hypedexer/indexer fills (not last 2k)
screen     HyperTracker style + HyperX/Hyperank numeric vetoes
vet        Lookonchain/OnchainLens tape; subtract borrows; drop HIP-3 backstop
monitor    WS ≤10 users/IP; never agent-wallet address
never      search-ad HL URLs, claim tweets, unsigned npm MCPs
```

---

## 13. Discrepancies, ambiguities and corrections found while compiling

These are inconsistencies *inside the raw file* (or between the file and its own sources). None are silently resolved; the consuming agent should prefer live data over any number here.

| # | Topic | What the raw file says | Handling |
|---|---|---|---|
| 1 | **Leaderboard row count** | "~47k", 46,904 (Cipher 09-30), 46,867 (Hyperank), 46,657 (LabelYX whale page), 43,618 (MinaraCN 09-01 dump), ~46.9k (Cipher 09-30 inclusion note) | Snapshot-dependent; never hard-code a count. Hyperank's 46,867 is "leaderboard right now"; its 1,935 is "wallets in our pool" (Grok) |
| 2 | **WS unique-user cap** | Summary says "~10–14"; official docs say 10; Bloxwap/nktkas guard at 14 after a probe | Use 10 |
| 3 | **Chase persistence stats** | "top-10% still profitable next month ~50%" vs "prior top trader profitable next month 45.5%" | **Resolved (Grok B06):** both lines are in the post — "only half" is the author's rounding of 45.5% (vs 42.3% random); "top 10%" and "profitable" are undefined |
| 4 | **Hyperank median min copy $386** | "across 2,278 ranked" while the audited pool kept is 2,720 | Grok confirmed they are two separate posts (2,278 ranked traders for the $386 median; 2,720 survivors of the 7,400-wallet audit); no post reconciles them — keep separate |
| 5 | **pension-usdt realized loss** | ≈ $16M (AiCoin) vs $26.66M (BitcoinWorld/OnchainLens) | Different accounting suspected; unresolved |
| 6 | **Dexter `0xb7e0…` address** | First pass gives the full 42-char `0xb7e0b9fbc9479330d70bcc82a7d4325a20e8d1aa`; the calibration pass says "TRUNCATED IN SOURCE — do not guess" | **Resolved (Grok B11):** the full address is in the DexterOnchain post; tags are HFT/MM + Direction Neutral + Large Capital |
| 7 | **Hyperank app URL** | Pass 2: "not in retrieved tweets"; Pass 3 cites `hyperank.io` and `hyperank.io/how-scoring-works` | Domain found; the 2026-09-06 post is a long tweet (guide: hyperank.io/guide); the X article body is still unretrieved (Grok A04 failed) |
| 8 | **Dune status** | Pass 1 lists Dune tables as an analytics source; the audit says "Dune/Flipside trader boards not found" | Both true: tables exist `[DOCS]`; no ready-made skilled-trader dashboard exists |
| 9 | **Win-rate floor** | HyperX 50% (2026) vs lucas 70% (2025, 30d) | Era/window differ; use 50% soft floor |
| 10 | **Drawdown cutoff** | HyperX > 50% · Niakris ≥ 22% skip / < 15% aim | Treat as "read DD" |
| 11 | **HyperX "leverage > 1x"** | Appears in the hard-score list of the practitioner section only; not in the first-pass threshold block | **Resolved (Grok B10):** "Leverage > 1x, confirms the account really trades" is in the hard-score list |
| 12 | **Abraxas numbers** | $1.2B shorts, > $100M uPnL loss (09-21) vs $859M exposure, 30d −$53M (09-28) | Different dates; both reported |
| 13 | **Wintermute-book duration** | HypurrScan/hl.eco first seen ≈ 550 days (~18 months) vs Arkham entity span 2024-01-20 → 2026-09-27 (~32 months) | Entity-level vs address-level; unresolved |
| 14 | **Hypedexer pricing/coverage** | First pass: "cost unverified"; later pass: hosted free tier 5,000 credits/month, 78 read-only MCP tools, fills since Nov 2024 | Free tier 5,000 credits/mo and "fills since Nov 2024" confirmed on X (09-29 and 09-28 posts); "78 MCP tools" is **not** in the 09-29 thread — treat as vendor/docs claim |
| 15 | **Hyperdash domain** | Earlier citations hypurrdash.app; now hyperdash.com; legacy.hyperdash.com | Use hyperdash.com |
| 16 | **Garrett Jin arithmetic** | +$11.20M ZEC +$8.38M BTC −$35.44M ZEC short ≠ −$14.7M net | Other trades unlisted; "−$14.7M over 4 months" is Lookonchain's figure |
| 17 | **Top-15 provenance** | Audit says the first-pass top 15 was "reconstructed" | Treat as stack audit |
| 18 | **Shill labels** | Pattern labels "from posts + prior inventory" but almost none has a linked post | Grok C08: no supporting posts found for most labels; two quoted lines absent from the opened posts — labels remain agent opinion |
| 19 | **Raw-file formatting artifacts** | `<…>` autolinks inside JSON strings; a broken `GET …leaderboard`>` line; "*HIP-3\ mark on-chain**" asterisk/backslash noise; leading "I'll search…" agent narration | Cleaned in this file |
| 20 | **Non-X sources under an X-only brief** | Cipher, LabelYX, TrueHold, official docs, GitHub pages are web sources | Tagged `[WEB]`/`[DOCS]` |
| 21 | **HIP-3 post attribution** | Registry linked `HansonBirringer/…2102894931258011901` as the HIP-3 mark post | Grok A02: that post is a revenue brag; the HIP-3 post is `…/2103099378840088842` (2026-09-24) → registry corrected; §9 content unaffected |
| 22 | **Lookonchain rotation** | "11 wallets, same day, ~$20M" | Grok A07/C01: 3 days, $45.83M each side; 5-day follow-up $86.76M → N9 corrected |
| 23 | **CryptHypoBuster size** | ≈ $109M of 40x longs added | Grok A14: $46.5M of 40x BTC by two wallets; whale BTC longs $138.6M → $210.5M → corrected |
| 24 | **Minara recent-window rule** | "require recent profit across 1d/7d/30d" | Grok B09: windows are compared and their count feeds the score; not a hard all-positive filter; no weights → §6 reworded |
| 25 | **Manual-borrow LTVs** | HYPE 65%, BTC 50% | Grok C07: not in the official post or its image → unverified |
| 26 | **HIP-3 funding-clamp source** | jeff_hl / deployer-actions docs | Grok C07: sentence is from `@HypeStatsx` 2026-09-18 ("on the next network upgrade") → attribution fixed |
| 27 | **Hypedexer V2 launch** | "V2 + MCP live 2026-09-16" | Grok C07: no V2 launch sentence; MCP use shown 2026-09-17 → reworded |
| 28 | **Web-only security incidents** | Inferno Drainer, lookalike domains, emailveritas, npm MAL-2026-3679 | Grok C06: none found on X → tagged [WEB]-only |
| 29 | **Hyperank "half under $500"** | 50% | Grok B12 image: 56% (1,275 of 2,278) → use image table |
| 30 | **Dexter wallet age** | marketed as #1 copy | Grok B11: <5 months old; all-time realized below the 90d figure → N10 expanded |
---

## 14. Grok follow-up results (verification of vague and rule-bearing posts)

The raw file *dumped or thinly summarized* many X posts. All 101 X URLs were classified (55 captured / 30 partial / 16 bare — [Appendix A](#appendix-a--x-source-registry-101-links)) and the 46 partial/bare ones (**Batch A**), 18 rule-bearing captured ones (**Batch B**) and 12 link-less open questions (**Batch C**) were sent to Grok, which can read X directly. Fifteen Grok replies came back (all three batches are complete); this section is the merged, de-duplicated result. Every number below is quoted from Grok's post transcription; Grok did not open every linked page, so [WEB] sources are still the agent's.

### 14.0 Coverage and verdict

| Batch | Sent | Fetched | Result |
|---|---|---|---|
| A — vague tweets | 46 | 44 | 27 confirmed · 15 partly confirmed · 1 contradicted · 1 claim not in post · 2 unavailable (A04 Hyperank article, A35 0xikalgo) |
| B — rule-bearing posts | 18 | 18 | 15 confirmed verbatim · 3 partly (details in ledger) |
| C — open questions | 12 | 12 | 10 partly answered (incl. C02 with no Dune query IDs) · 2 not found (C03 X Lists, C11 owner-posted 12-month books) — see §14.6 |

**Bottom line:** every numeric screening rule that came from an X post now has a verbatim source (§14.2). What remains open (§14.7) is low-impact for the pipeline: the Hyperank article body, 0xikalgo, discovery gaps (no public X Lists, no owner-posted 12-month book, no Dune query IDs), several web-sourced security incidents Grok could not find on X, and a handful of truncated addresses.

### 14.1 Corrections to the raw file / earlier sections

| # | Item | Earlier statement | What the post actually says | Action |
|---|---|---|---|---|
| 1 | **A02** — HIP-3 mark-on-chain source | Registry pointed at `HansonBirringer/…2102894931258011901` | That post is a Hyperdash volume/revenue brag. The HIP-3 post is `…/2103099378840088842` (2026-09-24 12:29 UTC); its content matches §9. | Registry fixed; §9 content unchanged |
| 2 | **A07 / C01** — N9 sybil cluster | 11 new wallets, same day, ~$20M | Window is **3 days**; **$45.83M** each side (602 BTC → 18,780 ETH); 5-day follow-up $86.76M; 'likely the same whale', not confirmed; full 11 addresses not in post. | N9 rewritten; address list stays unobtainable |
| 3 | **A14** — CryptHypoBuster whale registry | Added longs ≈ $109M of 40x | Two wallets reopened **$46.5M** of 40x BTC longs; image says whale BTC longs $138.6M → $210.5M. 248-wallet selection method not stated. | Row corrected |
| 4 | **A11** — Hypedexer '78 read-only MCP tools' | Stated as confirmed | Not in the 2026-09-29 thread (free tier 5,000 credits/mo and endpoint list *are*). 'Fills since Nov 2024' is in the 2026-09-28 Trust Wallet post (A19). | Keep 78 as an unverified vendor claim |
| 5 | **A05** — Hyperank 2026-09-06 'article' | Treated as the x.com/i/article post | It is a long tweet. The real article `…/2096610433134120960` was **not** retrievable (A04). | Method still from hyperank.io pages; article body open |
| 6 | **A01** — HyperTracker/Hyperdash direction-bias post | Implied advice not to treat 100%-long weeks as skill | It is a HyperTracker post; says only that every cohort except Full Rekt (down >$100k) is bullish on HYPE. The 'not skill' advice is the agent's synthesis. | Marked [SYNTH] |
| 7 | **A16** — HIP-3 `dex` API advice attributed to cryppimagic | Implied tweet names the API parameters | Tweet only notes a Paragon-deployed $DRV HIP-3 perp. No call/parameter named. | Advice stays [DOCS], not [X] |
| 8 | **A24** — 'Abraxas' on the 0xZecup post | Listed as Abraxas-address supporting post | Post gives only address `0x5b5d…c060`, 3x $56.4M ZEC short, +$2.8M. The label appears in other posts (HypurrScan Infos field on A39). | Label stays [CLAIM] from A39 |
| 9 | **B06** — Chase '~50%' vs '45.5%' | Flagged as inconsistent | Both are in the post: 'only half … profitable next month' and 45.5% (vs 42.3% random). Neither 'top 10%' nor 'profitable' is defined. | §13 #3 resolved as author's rounding |
| 10 | **B12 / B15** — Hyperank 2,278 vs 2,720 | Unreconciled | Different posts: 2,278 ranked traders (median min copy $386) vs 2,720 survivors of a 7,400-wallet fill audit. Grok found no post reconciling them. | Stay separate; do not merge |
| 11 | **B15 / B17** — Hyperank counts | Treated as official-board counts | Wording is 'leaderboard right now' (46,867) and 'wallets **in our pool**' (1,935) — the 1,935 is a subset of Hyperank's pool, not of the whole board. | Wording tightened |
| 12 | **B09** — Minara 'positive PnL across 1D/7D/30D/all-time' | Stated as a hard all-positive rule | Windows are *compared*; all-time PnL **and** ROI must be positive. Scoring inputs named, **no weights**, no CSV link. | §6 rule reworded |
| 13 | **B11** — Dexter wallet tags | HFT/MM + Direction Neutral | Also **Large Capital**. Full address is in the post (not truncated). | N10 updated; §13 #6 closed |
| 14 | **B10** — HyperX filter labels | Paraphrased | Exact labels: Total Score, Profit, Stability, **Risk Ctrl**, Win Rate, **All PnL / Total PnL**, Leverage; **Account Value**, **Fill Realized**, ROI, Median Trade Duration. | §6 labels aligned |
| 15 | **B14** — HyperX part-2 vetoes | Paraphrased | Confirmed; tags are big loser / losing trader / high risk; also prefers hold-time distribution above 1h and active period >2 months. | None |
| 16 | **A27** — pension-usdt loss $16M vs $26.66M | Unresolved | AiCoin says 1600万U and never mentions $26.66M. 'Penision Fund' is a self-filled nickname that proves no institution. | §13 #5 stays open |
| 17 | **A20** — Wintermute HYPE short | $10.03M | Wintermute post garbles the HYPE line ('963,600', same digits as the uPnL line). $10.03M came from another source. | Keep, flag source |
| 18 | **B13** — Hyperdash BTC trader (+$8.57M, 35% WR) | Address needed | Numbers confirmed (26 trades, $885M volume) but only the truncated chip `0xaeaa…2416` exists. | Stay unresolved |
| 19 | **C07** — Manual-borrow LTVs | §9: HYPE 65% LTV, BTC 50% | The official @HyperliquidX post (2026-09-18) says $269M borrowed and HYPE/BTC collateral for USDC/USDT; the **LTV percentages are not in the post or its image**. | Marked unverified in §9 |
| 20 | **C07** — HIP-3 funding clamps | Cited as jeff_hl / deployer-actions docs | The clamp sentence is from **@HypeStatsx** (2026-09-18): configurable by HIP-3 deployers on the next network upgrade. | §9 attribution fixed |
| 21 | **C07** — Hypedexer 'V2 + MCP live 2026-09-16' | Stated as a dated launch | No V2 launch sentence found. @hypedexer 2026-09-17 shows the MCP in use (seven calls, §14.6). | §9 reworded |
| 22 | **C06** — Web-sourced incidents in §11 | Inferno Drainer 550,019 USDC; lookalike domains; emailveritas false positive; npm MAL-2026-3679 | None of these four was found on X. Only the @Hyperliquid_Eco impersonator report (@Hyperliquid_Hub 2026-09-29) and a scammer complaint are confirmed. | Tagged [WEB]-only in §11; absence is not a clean bill |
| 23 | **C08** — Shill-label quotes (§5) | @HYPEconomist 'dump on outsiders'; @JoestarCrypto 'did not farm copy pastes' | The opened posts say neither (a NEAR meme call; a HIP-3/Variational remark). | Quotes demoted to unverified agent labels |
| 24 | **B12** — Hyperank 'half sit under $500' | Read as 50% | The post's own image says $500 covers **1,275 of 2,278 traders (56%)**; $100 covers 446 (20%); $1,000 covers 1,618 (71%); $5,000 covers 2,104 (92%). | Use the image table |
| 25 | **B11** — Dexter / HyperX wallet | Good copy candidate per HyperX | Account is <5 months old (first trade 2026-05-10); all-time realized $6.48M is *below* its 90d $6.84M; all open positions are shorts at 25.0x average leverage with −$756.8K unrealized; HyperX's 'reconsider' rules are median hold <10 min, copy-fit <15 or 7 days quiet. | N10 expanded |
| 26 | **B09** — Minara 12-wallet study | Positive closed PnL across the profitable set | In the fill samples **all three day/scalp wallets had negative closed net PnL** (despite $61.43M leaderboard all-time profit) and only 6 of 8 high-turnover wallets were positive. | Calibration note in §14.3 |
| 27 | **B03** — Niakris Sharpe rule | 'Sharpe ≤1.5 = lottery' | Post says 'Sharpe Ratio >1.5? No = pure lottery ticket' — i.e. skip if not above 1.5. | Same meaning |

### 14.2 Screening numbers now verified verbatim

Tier: **[X-verified]** = quoted from the post itself. All are other people's heuristics, not proof of skill.

| Source (post) | Window / scope | Verified rule |
|---|---|---|
| lucas_faster 2025-05-05 (B01) | HyperX, 30d | win rate ≥70% · equity ≥$10k · realized ≥$10k · 5–100 completed trades (>100 ≈ bot) · ROI ≥50% (ROI = PnL / max(100, start + max net deposits)) → 99 wallets; then curve veto, weekly cull, copy deposit ≥15 USDC |
| hyperx_trade 2026-09-17 (B10) | HyperX wallet-discover | Total Score >40 · Profit >60 · Stability >50 · Risk Ctrl >50 · Win Rate >50% · All PnL / Total PnL >$20K · Leverage >1x · Account Value >$20K · ROI 20–50% · Median Trade Duration >1h |
| hyperx_trade 2026-09-24 (B14) | HyperX list + detail | drop max DD >50% · Recovery Factor <1000 · active >2 months · kill: no live state / no trade 30d · equity <$10K · avg hold <3 min · leverage >25x (also historical avg) · margin use >90% · 30d tag big loser / losing trader / high risk · copy-fee share >70% |
| 13_niakris 2026-04-06 (B03) | Coinpilot checklist | max DD ≥22% skip (aim <15%) · last trade ≥7 days = asleep · AI risk alerts + high vol → size ×0.5 · >5 open positions · hold 24h+ holder / <1h scalper · Sharpe >1.5 |
| MinaraCN 2026-09-01 (B09) | 43,618-row dump, all-time + 1 month | equity ≥$10k · all-time PnL and ROI >0 · all-time volume ≥$1M · month volume ≥$100k · compare 1D/1W/1M/all windows · check public fills → 1,681 pass; top-12 style split 8 high-turnover two-way : 3 day/scalp : 1 concentrated directional |
| thedefiedge 2026-01-27 (B02) | Hyperdash copy | mirror at most 3 wallets · filter swing/position traders · avoid wallets with many open positions (qualitative) |
| reisnertobias 2026-04-29 (B04, B05) | Hyperdash 30d | OIL: DD 1.0%, WR 80%, Sharpe 13.15 (all-time +$1.4M, vol $62,339,743.85) · Equities: DD 20.2%, WR 79%, Sharpe 10.58 |
| chase_mew_ 2026-07-20 (B06) | 935k wallets, 1 year | top-10% → top-10% next month 19% · prior top trader profitable 45.5% vs random 42.3% · R² 0.036 |
| koolkrypto223 / djkanzen 2026-07-20 (B08, B07) | reply thread | discretionary PnL comes from 3–5 big trades/year (flat months normal) · HyperTracker runs 5 live segments re-queried every 1–6h on single-coin performance |
| hypeRankio 2026-09-20…27 (B12, B15–B18) | Hyperank pool | min order $10 · median min copy $386 over 2,278 ranked (half <$500; 1 in 5 <$100; 17 of 39 score≥90 <$500) · 46,867 board → top 7,400 → 2,720 · of 4,680 failures: 534 leverage, 490 margin/near-liq, 639 30d DD, 18 impossible win rate · 1,935 board-green/account-flat dropped · starter $100–500: Fixed $15/order, 3 positions, 20% wallet stop |
| kamalbuilds 2026-09-27 (A33) | Exit Window / Nansen | 1% adverse-move exit timer (one NEAR exit left 1 min 7 s) · alarms: any cut, ≥2 within an hour, largest holder only, price near holder's liq · cut 25/50/100% · 242 labelled wallets, 30 s polling |
| QuantumVaultLab 2026-07-14 (C04) | bot paper-test gate | 30 days minimum · ≥10 trades · profit factor >1.1 · drawdown <30% — a *bot's* promotion gate, usable only as a loose reference |
| hypeRankio 2026-09-27 thread (B18) | Hyperank setups | Mirror ($1K–$5K): proportional, 1–2 traders, stop 25%, daily loss limit 10%, prefer holds of hours (on Lighter Robinhood 32% of accounts holding <15 min are profitable vs 45% at 4–12 h) · Basket ($5K+): 3–4 traders, stop on whole-account open PnL · Amplifier: manual ratio + per-trade cap · run paper mode first |
| DexterOnchain 2026-09-18 (B11) | HyperX 90d | rank 1 of 511 copyable · score 84.3 · copy-fit 100.0 (components: profit 92.0, stability 83.8, win-rate 77.6, risk 88.4, efficiency 56.5, experience 54.5) · HFT/MM + Direction Neutral + Large Capital · funding −$155.9K vs own fees $163.2K · 'reconsider' if median hold <10 min, copy-fit <15, or quiet 7 days |
| HyperTracker / Proliquid (A01, A17) | cohorts | 'Full Rekt' = wallets down >$100k · closed-trade stats unlock at $10k Proliquid volume (own-account only) |
| BazydloMis57623 2026-09-25 (A09) | Whale Street | six listing checks: track record, size, human-or-bot, hidden hedges via linked wallets, concentration, uniqueness; 817 trades/day was a single demo reject, not a cutoff |

### 14.3 Addresses completed or newly attributed

All are **[CLAIM]**s from the cited post; tracker nicknames (Mirrorly, Hyperbot) are not identities. Verify on-chain before use.

| Address | Label (as posted) | Source | Numbers in the post | Role |
|---|---|---|---|---|
| `0x337afda118de433f5a8c8ad6d6ef48b76d027a06` | unlabelled trader | OnchainLens 2026-09-08 (A06) | 7 lifetime liquidations; lifetime +$632.0K, 30d +$630.1K; net realized +$421.6K; largest loss −$207.2K | Calibration: green after 7 liqs, but nearly all profit in the last 30d |
| `0x9c6a5b4662c722d2c47f43d6c9813cb080ffa4ed` | SOL long whale | EmberCN 2026-09-27 (A10) | 550,000 SOL from $80.8, +$22.43M uPnL; TWAP plan 500,000 SOL, 186,000 filled at avg $76 | Multi-week follow; one TWAP long, not a method |
| `0x77375a8c9d13bf79afb2a87f1b0ac1dfd5f5bf66` | @mk4_lul | OnchainLens 2026-09-26 (A18); Minara (B09) as 'directional day trader' | lifetime +$57.04M (spot+perp), 30d +$14.17M, open $43.63M, NEAR long $28.48M 10x, 25 liquidations (OnchainLens 09-26). Minara fill sample (09-01): ETH/SOL/PUMP/BTC, 94.7% buys, $14.09M volume, closed net −$142,648, leaderboard all-time $47.06M | Watch-only; high liquidation count; recent sample negative |
| `0xf5629393e446a103a4be1c49a956255e7c87c1d3` | 'Whale 0xf562' | Lookonchain 2026-09-29 (A21) | sold 25,001 ZEC ($37.84M), bought at avg $425, profit >$27M | Spot ZEC, not a perp book; not a perp-skill example |
| `0xbf732ea04197942783e34730ed6e0f6099575d58` | @solanadoomer1 / 'Boomer' | Hyperdash 09-21 (A08); Hyperbotai 09-30 (A13); jodezXBT 09-30 (A23) | 30D net +$12,270,577.85 (#1); $35M ETH long; $8.54M BTC short 40x; 2.32B PUMP long; board-source: cryptotraders 'top-25 by 30d' | P3 — watch only; nickname link is Hyperbot's, not the owner's |
| `0x020ca66c30bec2c4fe3861a94e4db4a498a35872` | Machi (Hyperbot label) | Hyperbotai 2026-09-30 (A13) | equity $7.77M, 19.24x, 1W WR 81.82%, 1W max DD 12.32%, 3,290 trades, 1M perp +$2.22M | N3 — high WR does not offset leverage |
| `0xb7e0b9fbc9479330d70bcc82a7d4325a20e8d1aa` | rank 1 of 511 copyable | DexterOnchain 2026-09-18 (B11) | score 84.3, copy-fit 100.0, HFT/MM, Direction Neutral, Large Capital; 90d realized $6.84M / 98 round trips; first trade 2026-05-10; all-time realized $6.48M; open shorts at 25.0x, uPnL −$756.8K | N10 — vendor copy score ≠ copyable; <5 months old |
| `0xecb63caa47c7c4e77f60f1ce858cf28dc2b82b00` | Wintermute (OnchainLens label) | OnchainLens 2026-09-28 (C09) | $126.25M shorts, ETH $46.92M, lifetime +$197.22M | P1 / N4 — MM book; address now confirmed printed in full by the poster |
| `0x7491180d3e43719bd8a53cdfbef27a1527a1d90f` | HyperX 90d screen, low-leverage alt long | hyperx_trade 2026-09-30 (C07) | equity $1.36M, 90d perp net PnL $875K, win rate 69%, historical avg leverage ~2x, max DD ~11% | Vendor screen example — vendor-computed |
| `0xb7658d7c63b6c1fc7254fe9402a95d044db70dbc` | HyperX September screen, alt trend long | hyperx_trade (post 2105152675855933631) (C07) | numbers not captured | Vendor screen example |
| `0xb83de012dba672c76a7dbbbf3e459cb59d7d6e36` / `0x5b5d51203a0f9079f8aeb098a6523a13f298c060` | Abraxas Capital (HypurrScan Infos field) | pnlsdaily 2026-09-21 (A39); 0xZecup 09-30 (A24) | $1.2B shorts, >$100M uPnL loss; 0x5b5d $56.4M ZEC short 3x entry 1,501.3 | N5 / P2 — fund hedge |
| `0x0ddf9bae2af4b874b96d287a5ad42eb47138a902` | 'Penision Fund' | rpahlmeyer (A15); AiCoin (A27) | liquidated 2026-08-20 04:51 Beijing, avg $2,235.36, ~49,800 ETH, $111.34M; loss headline 1600万U | N2 |
| `0xe4c6ae25959d7fc66cf2dd5965fb78c5e09c4048` | high-turnover example | Minara 2026-09-01 (B09) | 2,000 fills = $24.92M volume, closed net +$113,079 (0.454%), BTC 69.2% of volume, buys 56.7% | Two-way execution book (MM-like); not a directional copy |
| `0x523852be2db1a76a0e088ecbff32e849544054e5` | 'perpfumbler' | Minara (B09) | BTC, xyz:SP500, HYPE, xyz:XYZ100, xyz:TSLA; $12.27M notional, closed net +$28,864 (0.235%), buys 43.4% | Same method spread over several markets |
| `0x399965e15d4e61ec3529cc98b7f7ebb93b733336` | fastest high-turnover | Minara (B09) | 2,000 fills in ~20 min, median gap 0.21 s, buys 49.85%, $1.44M volume, closed net +$2,187 (0.152%) | Bot-speed book — uncopyable |
| `0x8c625ff57d8a4374784c7eff585dfdc42ccec974` | DOGE day trader | Minara (B09) | DOGE 93.0% of volume; 1,071 fills over 23.35 days, buys 30.1% / sells 69.9%; closed net negative in sample | Directional day trader |
| `0xc926ddba8b7617dbc65712f20cf8e1b58b8598d3` | small-size scalper | Minara (B09) | avg ~$161 per fill, 2,000 fills, 67.1% buys, closed net −$14,572 | Tiny-ticket scalper; negative in sample |
| `0x862dd8e68f30693e3d3c9daa42a440bc6d2a1f0c` | concentrated directional | Minara (B09) | 14 fills over 12.05 days, all buys of @107, $18,504 volume, no realized PnL; leaderboard all-time profit $6.45M cannot be tied to those fills | Low-frequency single-market book |
| `0xcb7b6dd3b61c438746d998a4237d7c4cb4eb1efe` | HyperX 'rejected' example | lucas_faster (B01) | example the 30d screen removes | Negative-screen test case |
| `0x9e8b1e51c642f4C8b87c6BA11c53D516a218Afc4` | 'Venom Gibbon' (Mirrorly nickname) | MirrorlyLive 2026-09-30 (A45) | $2,297,810 NEAR short at $5.295 | Whale-alert feed example |
| `0x9B864dDE6ED1c21608b1665a0ac0fAA4F7E36e6E` | 'Citadel' (Mirrorly nickname) | MirrorlyLive 2026-09-30 (A46) | +$70,122 on UNI | Nickname only — not the firm |

**Not traders (do not ingest):** `0x07f5b6823751c2e2cd4560f28af75ff887102241` is a token contract (A32); `4WVg5C2p61Fn2VHvZmiVmPq26dyytr4ooF1DyAd6pump` is a Solana token (A41).

**Still truncated:** `0xace0a4…03fd` (B01 kept example), `0xaeaa…2416` (B13 BTC trader), `0xa5b0…1d41` (Hyperdash 30D rank 2, A08), `0x880a…311c` (ZEC short rank 3, A24), IndiciaDesk rows `0xec4a…cf62`, `0xe77c…15db`, `0x0c4a…1b19`, `0x61ce…a62b`, `0x9546…181c` (A14), and the 11 rotation wallets (A07; prefixes 0x082, 0xa05, 0x6Ba, 0xAB9 only).

### 14.4 New facts by topic (all from the fetched posts)

**Data and indexers**
- **Hypedexer** — free tier 5,000 credits/month; 24h snapshot 15.05M fills / $10.5B / 84,006 addresses; TWAPs 46.1% finished, 35.3% terminated; HIP-3 $3.09B on 10 dexes (xyz = 97.8%); "every Hyperliquid fill since November 2024", round trips reconstructed, HIP-3 + HIP-4, REST + WS on one key; Trust Wallet is a customer.
- **Hydromancer Reservoir** — free, no API key; AWS S3 requester-pays; fills incl. liquidations, ADLs, builder and TWAP fills; HIP-3 deployer data; candles, snapshots, orderbook; coverage "from launch" (no date).
- **0xArchive** — 30 days of 1-minute history loaded in 3 hours by a trader whose native-API calls competed with his bot's rate limit; free API key at 0xarchive.io/signup (later post); pricing tiers not stated.
- **CashBoard** — public API, no key; HL widgets are market-level (movers, OI, funding vs Binance/Bybit, HIP-3 listings, tape ≥$10K), not trader-level.

**Trackers and screeners**
- **HyperTracker** — .hl name search live (2026-09-29); 5 live segments (top scalpers, counter scalpers, top day traders, counter day traders, top swing traders) re-queried every 1–6 hours on single-coin performance; cohort names visible in the image include Smart Money, Grinder, Semi-Rekt, Giga-Rekt, Full Rekt plus three truncated ("Money Prin…", "Humble Ear…", "Exit Liqui…"); Proliquid integration gives own-account stats.
- **Hyperank** — copy score = *copyability*, not skill; simulator window 30 days; 0.02% builder fee on copied volume (execution product — keep it read-only); guides at hyperank.io/guide; Starter profile rules in §14.2.
- **Hyperbot / Hyperdash / HypurrScan / Cryptotraders / Mirrorly / Perpy** — each posts address cards or feeds; Cryptotraders' "top-25 by 30d PnL" is its own board, not the official leaderboard. Perpy has a free Telegram feed (wallet + PnL context per post).
- **Minara study** — 43,618 → 1,681 profitable → 12 deep-dived; most common profitable style is two-way high turnover (8 of 12), not early directional bets.

**Copy/exit tooling (Nansen buildathon)**
- **Exit Window** (kamalbuilds) uses Nansen `tgm/perp-positions` (find Smart Money holders on the same side) and `profiler/perp-trades` (every fill); measures time from a wallet's first sale to a 1% adverse move; 242 labelled wallets, 30 s polling; alarms on any cut / ≥2 within an hour / largest holder / nearing holder liquidation; response = Telegram or a cut of 25/50/100%. Useful as a *concept* (exit lag); its execution half is out of scope.
- **Whale Street** (BazydloMis57623) — listing committee with six checks; app/repo links were not recoverable.

**Added by batch C**
- **Canonical URLs:** hyperank.io (+ /how-scoring-works, /guide); Exit Window exit-window.fly.dev/waitlist; ASXN dashboards hyperscreener.asxn.xyz (handle @asxn_r; free per an independent user); Hypervisor hypervisor.gg (2025 post only); Hydromancer hydromancer.xyz/hyperliquid-historical-data; Isobath (@Isobathalerts) posts whale-collateral alert cards. Prices: Hypedexer free tier 5,000 credits/mo (owner post 2026-10-01); Hydromancer Reservoir "free and open-source … free, forever"; Hyperank price and 0xArchive paid tier not posted.
- **Hypedexer MCP in use (2026-09-17):** a seven-call read-only workflow on one address — `hd_user_profile`, `hd_fills_search` (perp, then spot), `hd_twaps_search`, `hd_liquidations_search`, `hl_public_candles` (HYPE and @107, 1m), `hl_public_clearinghouse_state`, `hl_public_predicted_fundings`.
- **kitsune-de `hyperliquid-mcp`** (@kitsunedevs 2026-07-18): open source, 2 source files, zero API keys, positions/PnL/liquidation price of any address, read-only by design (no wallet, no signing).
- **HyperTracker builder-code card (2026-09-30):** last 30d top 5 builder codes — $9.03B volume, 82,835 users, $6.13M revenue (MetaMask, Trust Wallet, Phantom, FOMO + one unclaimed code).
- **Dune lead:** @nftclients (2026-06-27) says to search "hyperliquid" on dune.com and that the "x3research dashboard is the best one" — no URL; treat as an unverified lead.
- **Attribution context:** @KaiVenn__ frames Abraxas as hedge/basis; @Hyperliquid_Hub puts Abraxas at ~$859M perp exposure vs ~$172M equity (ZEC $54M, all-time +$92.8M); @Perps_AI ties the Garrett Jin address to Lookonchain's 2026-09-24 report (ZEC short +$11.20M, BTC long +$8.38M, second ZEC short −$35.44M). No labelled party confirmed or denied any attribution.
- **Official announcements:** manual borrows live 2026-09-18 ($269M borrowed, HYPE/BTC collateral → USDC/USDT); HIP-3 testnet on-chain mark 2026-09-24; Hyperliquid community event 2026-10-05 Singapore (RSVP required).
- **Security:** @Hyperliquid_Hub 2026-09-29 flags the @Hyperliquid_Eco impersonator ("do not click any links, do not connect your wallet"). Other §11 incidents are [WEB]-only.
- **Vault, not wallet:** Altcopy "Vault spotlight PF1 — 53% annualized, Calmar 7.36, recomputed from its public PnL curve" — vault metric; not a trader screen.

**Excluded after verification (execution or noise)** — LiquidBots MCP (creates/edits bots, tops up margin), Scarlett API/MCP (live HL trading "next"), 0xikalgo hyperliquid-mcp (unfetchable, execution per raw file), Papurrr paper trading, OpenCatz AI (generic scouts), Copin (not HL), Hypervisor (no evidence), Hyperfolio Pulse (coin tape only), Senpi (own-wallet reports; no API stated).

### 14.5 What the verified posts do **not** contain

- No numeric Copy Score cutoff from Hyperank (A05); no weights for Minara's score (B09).
- No definition of "top 10%" or "profitable" in the Chase study (B06).
- No definition of the 5 HyperTracker segments beyond their names (B07).
- No HL margin/liquidation formula in the PapurrrTrade post (A30); no measured WS user cap in the Bloxwap post (A26).
- No win rate or drawdown for 0xbf73 in the Hyperdash post (A08); no selection rule for the 248 whales (A14).
- No pricing tier for 0xArchive or Hypedexer beyond the free tiers (A11, A25).
- No public list/community URL for HL trader research (C03) and no Dune query ID for % of wallets in profit (C02).
- No wallet-selection profit-factor, Sortino, Calmar or expectancy cutoff anywhere (C04); the only profit-factor number (>1.1) is a bot's paper-test gate.
- No dune.com query or dashboard URL for % of wallets in profit (C02); no public X List with owner and member count (C03).
- No LTV percentages in the official manual-borrow post (C07); no explicit Hypedexer V2 launch sentence (C07).
- No owner-posted 12-month discretionary track record with address + equity curve (C11); no public Sheet/Notion scorer, TradingView wallet script, browser extension or leaderboard-to-skill repo (C12).
- No confirmation or denial of the Wintermute / Abraxas / Garrett Jin / Boomer / Machi labels by the labelled parties (C09).

### 14.6 Batch C — open questions

| ID | Topic | Status | Result |
|---|---|---|---|
| C01 | Lookonchain 11-wallet BTC->ETH rotation (2026-09-18) | partially answered | Post found: x.com/lookonchain/status/2100835870219923791. Over 3 days 11 new wallets (likely one whale) sold 602 BTC ($45.83M) and bought 18,780 ETH. Follow-up 2026-09-21: 5 days, 1,107 BTC ($86.76M) -> 34,422 ETH ($86.5M), staked. Images show only 4 truncated prefixes; Arkham entity page returned 403; all 11 full addresses not found. |
| C02 | Dune dashboards / % of wallets in profit | partially answered | Request is real (@KORypto_JUN 2026-09-28). Replies: 'Dune has community dashboards' (@JoeWeb3z), 'hyperdash or mlm' (@liquidated_hl); no dune.com URL. One lead: @nftclients 2026-06-27 says to search 'hyperliquid' on Dune and that the 'x3research dashboard is the best one' (no URL). Dune IDs 6994144 / 6994277 / 7667431 were not found on X. |
| C03 | Public X Lists / Communities for HL trader research | not found | No usable list URL. Two claims exist (@skell 'Hyperliquid Power Players', 2025-09-18; @AlbertBlocks HL ecosystem list, 2025-06-10) but the links did not expand and both are ecosystem/hype mixes, not trader-research lists. Excluded. |
| C04 | Numeric cutoffs for profit factor / Sortino / Sharpe | partially answered | No wallet-selection cutoff for profit factor, Sortino, Calmar or expectancy. Only: QuantumVaultLab's *bot* paper-test gate (30 days, >=10 trades, profit factor >1.1, drawdown <30%); HyperX (Recovery Factor <1000 suggested, max DD >50% drop); Niakris (Sharpe >1.5). Slash Trade spotlights print Sharpe/DD but state no rule. |
| C05 | Canonical URLs, pricing, X adoption for tools the raw file could not pin | partially answered | Found: hyperank.io (+/how-scoring-works, /guide; no price posted); Exit Window exit-window.fly.dev/waitlist (no repo); ASXN = @asxn_r, hyperscreener.asxn.xyz (free per @0xkayser 2026-08-14); Hypervisor = hypervisor.gg (2025 post only); Hypedexer free tier 5,000 credits/mo (owner, 2026-10-01); Hydromancer Reservoir 'free and open-source ... free, forever' (2026-08-19) + hydromancer.xyz/hyperliquid-historical-data; Isobath (@Isobathalerts) posts whale-collateral alert cards. Not found: LabelYX, CoinClass, PerpFinder, HyperStats, HyperPulse, Dexly, Hyperank price, 0xArchive paid tier, Copin HL app URL, Whale Street expanded URL/code, Exit Window repo. |
| C06 | Security / phishing items cited without links | partially answered | Confirmed on X: @Hyperliquid_Hub 2026-09-29 reports @Hyperliquid_Eco impersonating Hyperliquid ('Do not click any links / connect your wallet'); @1049XBT 09-28 complains of fake-tweet scammers. NOT found on X: Inferno Drainer / 550,019 USDC, hyperiiquid.xyz/.net/.io/.vip, emailveritas scoring hyperliquid.xyz, npm @2oolkit/hyperliquid-cli MAL-2026-3679. Absence is not a clean bill. |
| C07 | Protocol and product announcements cited without links | partially answered | Confirmed: manual borrows live (@HyperliquidX 2026-09-18, $269M borrowed, HYPE/BTC collateral -> USDC/USDT) but the 65%/50% LTVs are NOT in the post or image; HIP-3 on-chain mark (@HansonBirringer 09-24); funding clamps configurable by HIP-3 deployers on the next upgrade (author is @HypeStatsx 09-18, not jeff_hl); Singapore event Oct 5; Hypedexer MCP used on a live address (09-17: hd_user_profile, hd_fills_search, hd_twaps_search, hd_liquidations_search, hl_public_candles, hl_public_clearinghouse_state, hl_public_predicted_fundings); HyperTracker builder-code card 09-30 (top 5: $9.03B volume, 82,835 users, $6.13M revenue). Explicit 'Hypedexer V2' launch wording not found. |
| C08 | Evidence for the agent's 'shill / noise' labels | partially answered | Found: @Crypto_Retardio (ALM) own claim '$1M+ profits for members via copy trading so far - 40%+ win rate on day trades' (unaudited); GoodCryptoApp 'Hyperliquid Mega Influencer List 2026 - Part 7'. The opened @HYPEconomist post is a NEAR meme call, not the quoted 0.1% rule; the opened @JoestarCrypto post does not say he skipped HL copy-pastes. Not found: zaika_hl, Emmah_Jayy, SageWhale, Henrik_on_HL, Khingbenz7, elenalin01, XT Smart Money, Coinpilot, Bloom, Superior. |
| C09 | Address attributions and calibration claims cited without links | partially answered | Found: OnchainLens 2026-09-28 prints the full Wintermute address 0xecb63caa47c7c4e77f60f1ce858cf28dc2b82b00 ($126.25M short, ETH $46.92M, lifetime +$197.22M); @KaiVenn__ 09-21 frames Abraxas ($1.2B shorts, >$100M unrealized loss) as hedge/basis; @Hyperliquid_Hub 09-28: Abraxas ~$859M perp exposure vs ~$172M equity, ZEC $54M, all-time +$92.8M; @Perps_AI 09-25 attributes Lookonchain's Garrett Jin identification (ZEC short +$11.20M, BTC long +$8.38M, another ZEC short -$35.44M); Hyperbotai prints the Boomer-linked and Machi addresses. No confirmation or denial of any label by the labelled parties. |
| C10 | Evidence for accounts ranked 12-40 in the agent's Top-40 | partially answered | Opened posts do not show these accounts vetting discretionary perp traders: Nansen post is about its own non-custodial trading agent; Altcopy posts a vault spotlight (PF1, 53% annualized, Calmar 7.36 recomputed from the public PnL curve); hlnames launched .hl.hn with ENS (identity infrastructure). Nothing relevant found for CryptHypoBuster, HyperliquidR, ponyo_fp, FourPillarsFP, GLC_Research, mogie__, ericonomic, shaundadevens, 0xTraderSam, tradexyz, sershokunin, AiCoincom, GHYPURR, whale_alert. |
| C11 | Discovery: owner-posted discretionary HL wallets with >=12 months track record | not found | No trader published their own address together with a 12-month equity curve, fills or PnL calendar. Hits were referral PnL conversions. |
| C12 | Discovery: community-built artifacts for HL trader scoring | partially answered | Found: @kitsunedevs hyperliquid-mcp (2026-07-18): open source, 2 source files, zero API keys, positions/PnL/liquidation price of ANY address, 'read-only by design: no wallet, no signing' (repo t.co not expanded). Not found: public Google Sheet/Notion scorer, TradingView wallet script, browser extension, leaderboard-to-skill repo with a visible commit, Flipside skill dashboard. |

### 14.7 Still open and impact

| Item | Why it matters | Impact |
|---|---|---|
| A04 Hyperank article body | Would give the full scoring method | Low — hyperank.io pages and 7 posts already give inputs and the $10 / pool logic |
| A35 0xikalgo | Another HL MCP | Low — already excluded as execution |
| C11 owner-posted 12-month books | Would give true long-horizon positives | **Medium** — positives stay limited to institutional/MM books and short-history cards; build positives from the pipeline itself |
| C02 / C03 / C12 discovery gaps | No Dune query IDs, no public X Lists, no community scorer repo | Low — rebuild from official data |
| C06 web-only security incidents | Inferno Drainer, lookalike domains, scanner false positive, npm MAL-2026-3679 not seen on X | Low — keep the hard-coded-host rule regardless |
| C08 shill labels | Two quotes not in the opened posts | Low — labels stay agent opinions |
| Truncated addresses (§14.3) | Cannot be queried | Low — none is needed to run the pipeline |
| 11 rotation wallets (A07) | Sybil-cluster test case | Low — class is already documented (N9) |
| Hyperank 2,278 vs 2,720 | Two pools; no post reconciles | Low — keep separate |
| pension-usdt $16M vs $26.66M | Different accounting suspected | Low |

### 14.8 Item ledger (A01–A46, B01–B18)

Status: **OK** confirmed · **PARTLY** partly confirmed · **WRONG** contradicted · **NOT IN POST** · **UNAVAILABLE**. Dates are Grok's `posted_at_utc` (UTC).

| ID | Post | Date | Status | Verified finding |
|---|---|---|---|---|
| A01 | `@HyperTracker` `2102762090943652027` | 2026-09-23 | PARTLY | HyperTracker HYPE cohort-bias card: all cohorts Bullish/Very Bullish except Full Rekt (wallets down >$100k). Cohort rows e.g. Smart Money 85 pos / $26.3M, Money Prin… 25 / $23.5M, Full Rekt 55 / $3.32M. It is a HyperTracker post (not Hyperdash) and says nothing about discounting 100%-long weeks. |
| A02 | `@HansonBirringer` `2102894931258011901` | 2026-09-23 | WRONG | CONTRADICTED. This post is a Hyperdash volume/revenue brag with no HIP-3 content. The HIP-3 mark-on-chain post is a different tweet: x.com/HansonBirringer/status/2103099378840088842 (2026-09-24). |
| A03 | `@hydromancerxyz` `2067990625224425636` | 2026-06-19 | PARTLY | Hydromancer Reservoir: free, no API key (tweet). Linked docs: AWS S3 requester-pays; fills incl. liquidations, ADLs, builder and TWAP fills; HIP-3 deployer data; candles/snapshots/orderbook; coverage 'from launch', no date. |
| A04 | `i/article/2096610433134120960` | — | UNAVAILABLE | UNAVAILABLE. Grok could not fetch the Hyperank x.com/i/article body (x_thread_fetch error). Method details still unseen. |
| A05 | `@hypeRankio` `2096629457981235203` | 2026-09-06 | PARTLY | Not the article: a long tweet. Profit is not copyability; Copy Score 'describes how copyable the wallet has been', not a prediction; 0.02% builder fee on copied volume, no subscription/performance fee/token; simulator window 30 days; no numeric score cutoffs. Guide: hyperank.io/guide. |
| A06 | `@OnchainLens` `2097320422526374392` | 2026-09-08 | OK | Address completed: 0x337afda118de433f5a8c8ad6d6ef48b76d027a06. Liquidated on $1.15M BTC+SOL (~-$42K). Lifetime +$632.0K, 30d +$630.1K (almost all profit is recent), 7 liquidations, net realized +$421.6K, largest loss -$207.2K, fees $40.6K. |
| A07 | `@lookonchain` `2100835870219923791` | 2026-09-18 | PARTLY | Lookonchain card: over 3 days, 11 new wallets (likely one whale) sold 602 BTC ($45.83M) and bought 18,780 ETH ($45.83M). Follow-up 2026-09-21: 5 days, 1,107 BTC ($86.76M) -> 34,422 ETH, staked. Only 4 address prefixes visible; the 11 full addresses are NOT recoverable. Arkham entity link in post. |
| A08 | `@hypurrdash` `2102120819111453066` | 2026-09-21 | OK | Hyperdash: @solanadoomer1 = 0xbf73…5d58, #1 by 30D net realized PnL +$12,270,577.85 (account value $6.59M), $35M ETH long +$2.2M. Rank 2 0xa5b0…1d41 +$10.13M; rank 3 'MP05' +$9.95M. No win rate or drawdown shown. |
| A09 | `@BazydloMis57623` `2103548912900694418` | 2026-09-25 | OK | Whale Street (Nansen buildathon): six-check listing committee (track record, size, human-or-bot, hidden hedges via linked wallets, concentration, uniqueness). '817 trades/day' is one demo rejection, not a cutoff. No app/repo URL in post. |
| A10 | `@EmberCN` `2104038318551994481` | 2026-09-27 | PARTLY | Address completed: 0x9c6a5b4662c722d2c47f43d6c9813cb080ffa4ed. 550,000 SOL long from $80.8, floating +$22.43M, still held. Quoted 2026-08-09 post: TWAP plan 500,000 SOL, 186,000 filled at avg $76. |
| A11 | `@hypedexer` `2104878996232323421` | 2026-09-29 | PARTLY | Hypedexer 24h stats: 15.05M fills, $10.5B, 84,006 addresses; TWAPs 46.1% finished / 35.3% terminated; HIP-3 $3.09B on 10 dexes (xyz 97.8%). Free tier 5,000 credits/month confirmed. '78 MCP tools' and 'fills since Nov 2024' are NOT in this thread (the latter is in A19). |
| A12 | `@HyperTracker` `2104914845074403408` | 2026-09-29 | OK | HyperTracker: wallet search by .hl name (hlnames) is live. No API or leaderboard change. |
| A13 | `@Hyperbotai` `2105247944295518213` | 2026-09-30 | OK | Hyperbot card for 0x020ca66c…5872 (labelled Machi): equity $7.77M, position value $149.57M, 19.24x, 1W win rate 81.82%, 1W max DD 12.32%, 3,290 trades, 1M perp PnL +$2.22M; BTC 40x cross. Separate Hyperbotai post 2105245286281183312 links 0xbf73…5d58 to Boomer (@solanadoomer1): 2.32B PUMP long ~$13.64M, equity ~$1.28M. |
| A14 | `@CryptHypoBuster` `2105387702149582875` | 2026-09-30 | PARTLY | CryptHypoBuster (IndiciaDesk): tracks 248 whale wallets; two wallets reopened $46.5M of 40x BTC longs (NOT $109M). Image: whale BTC longs $138.6M -> $210.5M; amber = liq within 5% of price. Addresses truncated; selection method of the 248 not stated. |
| A15 | `@rpahlmeyer` `2090227288658886856` | 2026-08-19 | OK | Only says the wallet was liquidated and gives 0x0ddf9bae…a902. The 5.5%-from-liquidation figure is in the quoted post. No dollar loss. |
| A16 | `@cryppimagic` `2102686206811058545` | 2026-09-23 | NOT IN POST | NOT IN POST: it only notes a $DRV HIP-3 perp deployed by Paragon. No API call or `dex` parameter is named (that advice is from docs/agent, not this tweet). |
| A17 | `@iam4x` `2103414101372547182` | 2026-09-25 | OK | Proliquid x HyperTracker: own-account analytics free for linked wallets; closed-trade stats / full-panel unlock at $10k Proliquid volume (quoted release note). Not a public-trader screener. |
| A18 | `@OnchainLens` `2103770418196984248` | 2026-09-26 | OK | Address completed: 0x77375a8c9d13bf79afb2a87f1b0ac1dfd5f5bf66 = @mk4_lul. Lifetime +$57.04M (spot+perp), 30d +$14.17M, open $43.63M, NEAR long $28.48M 10x (+$14.74M), 8 open positions, 25 liquidations (image). |
| A19 | `@hypedexer` `2104553095455973485` | 2026-09-28 | OK | Hypedexer x Trust Wallet: 'every Hyperliquid fill since November 2024', round trips reconstructed, HIP-3 and HIP-4, REST + WebSocket on one key. |
| A20 | `@iamalijandro` `2104594759637508543` | 2026-09-28 | OK | Wintermute short book $126.25M (ETH $46.92M, SOL $11.30M), lifetime +$197.22M. Hedge/two-sided framing is the author's (Jan snapshot ~$101.7M bids / $97.2M asks). No address in post. HYPE-short line is garbled ('963,600'). |
| A21 | `@lookonchain` `2104774617328140372` | 2026-09-29 | OK | Lookonchain: 0xf5629393…7c1d3 sold 25,001 ZEC ($37.84M), bought ~2 months earlier at avg $425, profit >$27M. Spot ZEC via Hyperunit, not an open perp. |
| A22 | `@proliquid_xyz` `2105214047364743629` | 2026-09-30 | OK | Proliquid weekly recap: HyperTracker integration shipped (own-account metrics). No whale-data/API change. |
| A23 | `@jodezXBT` `2105285639482826864` | 2026-09-30 | OK | Cryptotraders card: 0xbf73…5d58 'TOP-25 BY 30D PNL' opened $8.54M BTC short at $85,175.10, 40x cross, liq $139,438.56, against a book ~85% long. Source board is cryptotraders.com, not the official leaderboard. |
| A24 | `@0xZecup` `2105429342667067427` | 2026-09-30 | PARTLY | 0x5b5d…c060: largest ZEC short on HL, 3x, $56.4M, entry 1,501.3, +$2.8M. Rank 2 0xb83d…6e36 ($38.0M short, -$2.5M); rank 3 0x880a…311c (10x, $19.1M). The word 'Abraxas' is NOT in this post. |
| A25 | `@0xArchiveIO` `2073437680571174934` | 2026-07-04 | PARTLY | 0xArchive: trader moved an arbitrage screener over live; native API caps history and shares rate limits with the bot; 30 days of 1-minute history loaded. Free API key only in a later post (2026-09-04, 0xarchive.io/signup); pricing tiers not stated. |
| A26 | `@joeblau` `2081376062177693836` | 2026-07-26 | PARTLY | Only: benchmarked nktkas/hyperliquid and refactored (Bloxwap repo). No WS user-cap finding. |
| A27 | `@AiCoinzh` `2090348112913063948` | 2026-08-20 | OK | AiCoin: loss headline 16 million U (1600万U); liquidation 2026-08-20 04:51 Beijing, avg $2,235.36, ~49,800 ETH, $111.34M notional. 'Penision Fund' is a self-filled nickname, not proof of an institution. Does not mention the $26.66M figure. |
| A28 | `@senpi_ai` `2103499006621925885` | 2026-09-25 | PARTLY | Senpi: paste wallet for a free read-only 'leak' report (hold losers longer, sizing, fees, funding). 3.2x / $4,120 is a marketing example. No URL or API in post. |
| A29 | `@liquidbots` `2104581219262529860` | 2026-09-28 | OK | LiquidBots MCP: create bots, change settings, top up margin. Execution tool; no read-only any-address tool. Exclude. |
| A30 | `@Papurrrtrade` `2104624033891528719` | 2026-09-28 | OK | PapurrrTrade paper trading claims 'Hyperliquid's own margin formula' but writes no equation. |
| A31 | `@Copin_io` `2056952349848154452` | 2026-05-20 | OK | Copin_io post is a Vietnam event announcement, not Hyperliquid. No Copin HL posts since 2026-04-01. |
| A32 | `@lbexplorer` `2094365077734580385` | 2026-08-31 | PARTLY | No trader address posted: the 0x in the text is the token contract. Trader PnL -$1.6M; $350K short from $0.333, liq $0.788. |
| A33 | `@kamalbuilds` `2104343781172744416` | 2026-09-27 | OK | Reply is only the Exit Window waitlist URL; rules are in the parent thread (see §14.4). 242 Nansen-labelled wallets, 30s polling, 1% adverse-move exit timer. |
| A34 | `@Hypervisor_hl` `2105388466813177969` | 2026-09-30 | OK | One-line question; no product or trader-analytics evidence for Hypervisor. |
| A35 | `0xikalgo/status/2026445955151839372` | — | UNAVAILABLE | UNAVAILABLE. Fetch failed and keyword search returned nothing. Stays classed as an execution MCP (excluded). |
| A36 | `@thefofoshow` `2080053994194346233` | 2026-07-22 | OK | Install note: official hyperliquid-python-sdk 0.24.0, testnet default, 2,283 markets returned. No trader research. |
| A37 | `@0xAiraa` `2095274179436184060` | 2026-09-02 | PARTLY | OpenCatz AI: generic 15-scout bot (repo github.com/dizcorvus/opencatz-ai). No HL whale output or ranking logic. |
| A38 | `@BrendanPlayford` `2100661425723326470` | 2026-09-17 | OK | Scarlett API/MCP: free for limited time, 12B fine-tuned model, 'live trading on Hyperliquid next'. No read-only mode stated; exclude. |
| A39 | `@pnlsdaily` `2101969403524858192` | 2026-09-21 | PARTLY | pnlsdaily: Abraxas-labelled addresses come from the HypurrScan Infos field on the images: 0xb83de012…6e36 (overview $151.6M) and 0x5b5d5120…c060 (overview $180.5M); 5x/10x shorts all red. Shorts $1.2B, >$100M uPnL loss. Hedge/basis claim is not in the post. |
| A40 | `@perpyxyz` `2102035360561643890` | 2026-09-21 | OK | Perpy mobile app: follow whales, alerts on open/close, iOS+Android. No pricing or API. |
| A41 | `@Story91_` `2103997497743995144` | 2026-09-26 | OK | Cashboard: 40+ widgets (HL: funding, liquidations, whale bets, wallets), desktop $29 once. No trader scoring. |
| A42 | `@CashBoardLive` `2104461199295529081` | 2026-09-28 | OK | CashBoard HL widget: movers, OI, funding vs Binance/Bybit, HIP-3 listings, live marks over HL websocket, tape from $10K; public API, no key. No trader-level data. |
| A43 | `@perpyxyz` `2105063133433811317` | 2026-09-29 | OK | Perpy free Telegram feed: large long/short moves, profitable closes, daily recap, wallet + PnL context per post (t.me/perpyxyz, t.me/perpy_hyperliquid). |
| A44 | `@Hyperfoliofun` `2105363987680432599` | 2026-09-30 | OK | Hyperfolio Pulse: coin shock tape (1/5/15-minute windows). No trader data. |
| A45 | `@MirrorlyLive` `2105413119061176529` | 2026-09-30 | OK | Mirrorly: nickname 'Venom Gibbon' = 0x9e8b1e51c642f4C8b87c6BA11c53D516a218Afc4, $2,297,810 NEAR short at $5.295. Address only in reply URL (portal.mirrorly.xyz). |
| A46 | `@MirrorlyLive` `2105417547185082775` | 2026-09-30 | PARTLY | Mirrorly: nickname 'Citadel' = 0x9B864dDE6ED1c21608b1665a0ac0fAA4F7E36e6E, +$70,122 on UNI. A tracker nickname, not the firm. |
| B01 | `@lucas_faster` `1919348617154101588` | 2025-05-05 | OK | CONFIRMED. HyperX 30d screen: win rate >=70%, equity >=$10k, realized >=$10k, 5-100 completed trades, ROI >=50% (ROI = PnL / max(100, start + max net deposits)) -> 99 wallets. Body also: equity-curve veto, weekly cull, copy deposit >=15 USDC. Rejected example 0xcb7b6dd3…1efe; kept example 0xace0a4…03fd still truncated. |
| B02 | `@thedefiedge` `2016118571483447674` | 2026-01-27 | OK | CONFIRMED. thedefiedge: Hyperdash lets you mirror up to 3 wallets at once (replicates net exposure); filter for swing/position traders; avoid wallets with tons of open positions (qualitative). |
| B03 | `@13_niakris` `2041157827692032048` | 2026-04-06 | OK | CONFIRMED all six: max DD 22%+ skip (aim <15%); last trade 7+ days = asleep; AI risk alerts + high vol -> size x0.5; >5 open positions; hold 24h+ for holders / <1h for scalpers; Sharpe >1.5 or lottery. |
| B04 | `@reisnertobias` `2049410876109697529` | 2026-04-29 | OK | CONFIRMED. 0x3b11…8112 'best OIL trader': all-time +$1.4M, volume $62,339,743.85; 30d DD 1.0%, WR 80%, Sharpe 13.15; found on Hyperdash, alerts via @lit_trade. |
| B05 | `@reisnertobias` `2049522367680938043` | 2026-04-29 | OK | CONFIRMED. 0xe650…f1a9 equities trader: 30d DD 20.2%, WR 79%, Sharpe 10.58. No all-time PnL or tool named. |
| B06 | `@chase_mew_` `2079212386532139461` | 2026-07-20 | OK | CONFIRMED. 935,000 wallets, 1 year: top-10% -> top-10% next month 19%; 'only half' profitable next month AND 45.5% for prior top trader vs 42.3% random; R2 0.036. 'Top 10%' and 'profitable' are not defined. |
| B07 | `@djkanzen` `2079221726991491284` | 2026-07-20 | OK | CONFIRMED. HyperTracker builder reply: 5 segments (top scalpers, counter scalpers, top day traders, counter day traders, top swing traders); re-queried every 1-6h on single-coin performance; streaking wallets drop out. No segment definitions. |
| B08 | `@koolkrypto223` `2079224409043423245` | 2026-07-20 | PARTLY | PARTLY. Reply: discretionary traders earn most of the year's PnL in 3-5 big trades; flat months are normal. 'Top-100 all-time / runs a fund' is bio, not reply text. |
| B09 | `@MinaraCN` `2094646483396284853` | 2026-09-01 | PARTLY | PARTLY (filters and counts confirmed). MinaraCN 2026-09-01: 43,618 addresses -> 1,681 pass (equity >=$10k; all-time PnL and ROI >0; all-time volume >=$1M; month volume >=$100k; compare 1D/1W/1M/all-time; score; check public fills). Top 12 split 8:3:1 (two-way high turnover : day/scalp : concentrated directional). Windows are 1D/1W/1M/all-time (the raw file's '7d' is a paraphrase); score inputs listed but no weights, no CSV link. Seven full example addresses with per-address fill stats (§14.3). Caveat from the authors: a snapshot CSV cannot prove 365-day consistency. |
| B10 | `@hyperx_trade` `2100489602935210165` | 2026-09-17 | OK | CONFIRMED. HyperX filters (part 1): Total Score >40, Profit >60, Stability >50, Risk Ctrl >50, Win Rate >50%, All PnL / Total PnL >$20K, Leverage >1x; Account Value >$20K, ROI 20-50%, Median Trade Duration >1h; plus Fill Realized and trade-count filters. |
| B11 | `@DexterOnchain` `2101051112149352715` | 2026-09-18 | OK | CONFIRMED. DexterOnchain (HyperX founder) 2026-09-18: 0xb7e0…d1aa is rank 1 of 511 copyable; 90d total score 84.3, copy-fit 100.0; HyperX tags HFT/MM + Direction Neutral + Large Capital; 98 round trips, 77.5% win, realized $6.84M on $557.29M volume; funding -$155.9K, own fees $163.2K. First trade 2026-05-10 (account <5 months old); all-time realized only $6.48M over 170 round trips; open positions all short at 25.0x avg leverage, unrealized -$756.8K. Address complete in post. |
| B12 | `@hypeRankio` `2101640190049550478` | 2026-09-20 | OK | CONFIRMED. Hyperank: every HL order must be >=$10; across 2,278 ranked traders median minimum copy capital $386 (proportional median $481, fixed $185); image cumulative: $100 -> 446 traders (20%), $500 -> 1,275 (56%), $1,000 -> 1,618 (71%), $5,000 -> 2,104 (92%) — so 'half under $500' is really 56%; 17 of 39 wallets with score >=90 copyable under $500; cheapest score-92 needs $46. The 2,720 figure is not in this post. |
| B13 | `@hypurrdash` `2102793170169848172` | 2026-09-23 | OK | CONFIRMED text numbers: 1,235 BTC ($103M) sold in 23 min, +$2.4M; all-time +$8.57M since June; BTC win rate 35% over 26 trades and $885M volume. Address only a truncated image chip (0xaeaa…2416). |
| B14 | `@hyperx_trade` `2102973181183332444` | 2026-09-24 | OK | CONFIRMED all numbers (part 2): equity curve must trend up; drop max DD >50%; Recovery Factor <1000 (Calmar auxiliary); active >2 months; kill on: no live state or no trade 30d, equity <$10K, avg hold <3 min, leverage >25x (check historical average), margin use >90%, 30d tag big loser / losing trader / high risk, copy-fee share >70%. |
| B15 | `@hypeRankio` `2103800999164960955` | 2026-09-26 | OK | CONFIRMED. 46,867 wallets on the leaderboard 'right now' -> top 7,400 fill-audited (they hold $5.76B combined, image) -> 2,720 still standing. Method URL in the reply: hyperank.io/how-scoring-works. |
| B16 | `@hypeRankio` `2103806591732531551` | 2026-09-26 | OK | CONFIRMED. Of 4,680 failures (overlap allowed): 534 leverage too high, 490 margin near max / near liquidation, 639 30d drawdown too deep, 18 near-perfect win rate that does not add up. No numeric cutoffs. 'Win rate is usually the last number that tells you anything.' |
| B17 | `@hypeRankio` `2103902033635852518` | 2026-09-26 | OK | CONFIRMED. 1,935 wallets in Hyperank's pool are green on the official 30d board but flat/negative on the account's own 30d PnL; disagreeing wallets are dropped. (Pool, not the full board.) |
| B18 | `@hypeRankio` `2104257085567324282` | 2026-09-27 | PARTLY | PARTLY (starter numbers confirmed). Part 3 of a 7-post setup thread: The Starter $100-$500 (Fixed $15/order, min order $10, 3 open positions, stop 20% of wallet, pick traders who enter in 1-2 orders); The Mirror $1K-$5K (Proportional, 1-2 traders, stop 25%, daily loss limit 10%); The Basket $5K+ (3-4 traders, stop watches whole-account open PnL); The Amplifier (manual ratio e.g. 0.05, per-trade cap). Run paper mode first. The board-vs-account drop rule is in B17, not here. |


---

## 15. Gaps — searched and not found (or too weak)

Consolidated from the raw file's gap lists. "Not found" means the research agent searched and did not find it **on X**, not that it does not exist.

| Area | Gap |
|---|---|
| Dune / Flipside | No X-canonical Dune dashboard URL for "% of HL wallets in profit" or trader skill (asked 2026-09-28 by `@KORypto_JUN`; Grok C02: replies only say "hyperdash or mlm" / "Dune has community dashboards", no query ID; one unverified lead — `@nftclients` 2026-06-27 calls the "x3research dashboard" on Dune the best HL one); Flipside HL trader-skill dashboard not found. Web-only Dune queries 6994144 / 6994277 / 7667431 exist but were not found via X, so not inventoried |
| Numeric rules | No community profit-factor or Sortino cutoff; Sharpe cutoff only from Niakris (skip unless Sharpe > 1.5); Grok C04 found nothing new |
| Labelled-wallet products | Nansen / Arkham HL trader leaderboards as first-class CT products — Arkham is used for clustering only; Nansen perp-screener is market-level |
| Tool threads | HyperStats, CoinLobster, Buildix, Hyperbot HL-specific X threads in the last 6 months were thin; listed from the Sep-2026 comparison article rather than high-engagement CT posts |
| Open-source scoring | No official or popular public scraper repo dedicated to leaderboard → skill scoring; people wrap the public JSON + `/info`. No Google Sheet / Notion template; no TradingView script scoring wallets (only aggregated OI incl. HL from `@Yuriy_Biko`); no browser extension for HL trader research |
| Telegram bots | OSS Telegram bots exist on GitHub (`walqed/…`, `cobecheng/hypertracker-bot`, `shelteredcorgi/hypescanner-tg`, `rokitgg/hyperliquid-trades-feed`, `Mperomishael/smart-trader-bot`) but were not linked from any retrieved X post — excluded |
| Web-found, not X | Parse.bot (wrapped leaderboard API), Hyperbot.network (live tape) |
| MCPs | No MCP both popular on CT **and** confirmed read-only for arbitrary addresses besides Hypedexer and kitsune-de; CT posts found were execution MCPs (`@liquidbots` — Grok-verified create/edit/top-up only; `@0xikalgo` — Grok could not fetch; Scarlett — live trading "next") |
| Security | No named phishing/drainer domain targeting HL copy-traders independently confirmed in retrieved posts — do not invent names |
| Handles | ASXN X handle: user search returned empty (tool is real via official docs) |
| Intent-only | `@0xDecodex` liq/OI tracker — announced intent only, no product |
| Canonical URLs | Whale Street app/repo URL still unrecoverable (Grok A09: unexpanded t.co, blank Code line); Hyperank resolved to `hyperank.io` (+ `/guide`); Exit Window = `exit-window.fly.dev/waitlist`; Minara = `minara.ai`, `strategy.minara.ai` |
| Track records | Grok C11: still none — no owner-self-posted 12-month discretionary `0x` with a fill-level audit (`@koolkrypto223` claims top-100 AT PnL, posted no address); official HLP/community vaults omitted (vault ≠ wallet trader); the Lookonchain 11-wallet list is not in the post (Grok A07: only 4 prefixes); Dexter `0xb7e0…` is now confirmed complete |
| X Lists | No public `x.com/i/lists/…` URL surfaced (Grok C03: two claimed lists by `@skell` and `@AlbertBlocks`, links not expandable, ecosystem not trader research) — do not invent list IDs |
| Developer | No official one-line "account PnL =" formula in a 2026 X developer thread (board ROI formula only in Cipher); no OSS trader-scoring repo whose X post shows a last-commit hash; no confirmed info-only MCP posted on X in the window besides Hypedexer |
| Distributional negatives | Chase and Hyperank negatives are class-level calibration (strongest evidence), not address lists |

---

## Appendix A — X source registry (101 links)

All URLs appear in the raw file. **Date** is decoded from the tweet ID and matches the dates the raw file states next to links (66 of 66 checks). **Status:** C = captured, P = partial, B = bare. **R** = numbers in the post feed screening rules. **Grok** = result of the Grok verification pass (batch ID + status; "—" = not sent because the raw file already had full content). Details: §14.8.

| # | Handle | Post | Date | Status | R | Grok | Raw-file content (paraphrase) |
|---|---|---|---|---|---|---|---|
| 1 | (x.com/i/article) | `x.com/i/article/2096610433134120960` | 2026-09-06 | P |  | A04 UNAVAILABLE | Article 'discover / compare / simulate / copy'. Only a one-line takeaway recorded. |
| 2 | 0xAiraa | `x.com/0xAiraa/status/2095274179436184060` | 2026-09-02 | P |  | A37 PARTLY | Amplifies OpenCatz AI: OSS bot with 15 scouts across chains incl. Hyperliquid (new pools, whale wallets, breakouts); NFT-gated marketing; 3 likes. |
| 3 | 0xArchiveIO | `x.com/0xArchiveIO/status/2073437680571174934` | 2026-07-04 | P |  | A25 PARTLY | Says native HL API history + rate limits collide with a live bot; promotes 0xArchive (paid/free-key historical API). |
| 4 | 0xDecodex | `x.com/0xDecodex/status/2087609720206958846` | 2026-08-12 | C |  | — | 'Thinking of shipping' a liquidation/OI tracker; no product link (classed as vapor). |
| 5 | 0xikalgo | `x.com/0xikalgo/status/2026445955151839372` | 2026-02-24 | P |  | A35 UNAVAILABLE | Promotes github.com/0xikalgo/hyperliquid-mcp; raw file says it places orders (execution tool, excluded). |
| 6 | 0xZecup | `x.com/0xZecup/status/2105429342667067427` | 2026-09-30 | B |  | A24 PARTLY | Listed only as a supporting post for address 0x5b5d…c060 (Abraxas-labelled) on 2026-09-30. Content not stated. |
| 7 | 13_niakris | `x.com/13_niakris/status/2041157827692032048` | 2026-04-06 | C | ● | B03 OK | Skip max DD >=22% (aim <15%); last trade >=7d = asleep; high vol + AI risk alerts -> size x0.5; >5 open positions = correlation; hold time must match style (holder >=24h vs scalper <1h); Sharpe <=1.5 = lottery. |
| 8 | AiCoinzh | `x.com/AiCoinzh/status/2090348112913063948` | 2026-08-20 | P |  | A27 OK | Liquidation of 0x0ddf9b… ETH short; ~$111M notional close; realized loss ~ $16M; 'nickname pension != risk process'. |
| 9 | BazydloMis57623 | `x.com/BazydloMis57623/status/2103548912900694418` | 2026-09-25 | P |  | A09 OK | Each listed 'company' is a real HL trader; NAV from positions; liq = bankruptcy; six listing checks (track record, size, human vs bot, linked-wallet hedges, concentration, uniqueness); demo rejected a trader with 817 trades/day as MM. 'Code:' promised but URL blank in retrieved text. |
| 10 | betashop | `x.com/betashop/status/2026375093295919221` | 2026-02-24 | C |  | — | 2026-02-24 article: 45 MCP tools incl. 5 trader-discovery tools ranking all HL perp traders by ROI/PnL/win rate/drawdown/gain-to-pain across d/w/m/all; hosted + self-host claimed. |
| 11 | BrendanPlayford | `x.com/BrendanPlayford/status/2100661425723326470` | 2026-09-17 | P |  | A38 OK | Scarlett.ai API keys + MCP; live trading on HL advertised as next step (not research-safe). |
| 12 | C_Predecessor | `x.com/C_Predecessor/status/2103804221556433253` | 2026-09-26 | C |  | — | Reply to Hyperank: 'Drawdown first. How they behave when a trade goes wrong.' |
| 13 | CashBoardLive | `x.com/CashBoardLive/status/2104461199295529081` | 2026-09-28 | P |  | A42 OK | Says public API, no key; HIP-3 listings + HL WS marks. |
| 14 | chase_mew_ | `x.com/chase_mew_/status/2079212386532139461` | 2026-07-20 | C | ● | B06 OK | 2026-07-20: ~935,000 wallets, 1 year. Top-10% month t -> top-10% t+1: 19%; top-10% still profitable next month ~50%; random user profitable in a month 42.3%; prior top trader profitable next month 45.5%; R² = 0.036. ~500 likes. |
| 15 | Copin_io | `x.com/Copin_io/status/2056952349848154452` | 2026-05-20 | B |  | A31 OK | Cited only as an @Copin_io post dated 2026-05-20; raw file says it is not HL-specific. |
| 16 | cryppimagic | `x.com/cryppimagic/status/2102686206811058545` | 2026-09-23 | B |  | A16 NOT IN POST | Cited only as a source for 'empty dex = first perp dex only; HIP-3 coins prefixed'. |
| 17 | CryptHypoBuster | `x.com/CryptHypoBuster/status/2105387702149582875` | 2026-09-30 | P |  | A14 PARTLY | Tracks a 248-wallet HL whale book; size-weighted leverage, who added $109M BTC longs, liq distances; uses public positions for liq-pocket mapping. |
| 18 | CryptoAddict31x | `x.com/CryptoAddict31x/status/2099829364892250556` | 2026-09-15 | C |  | — | 2026-09-15: ~10k fills available for heavy traders on the public API. |
| 19 | DexterOnchain | `x.com/DexterOnchain/status/2101051112149352715` | 2026-09-18 | C | ● | B11 OK | 0xb7e0b9fbc9479330d70bcc82a7d4325a20e8d1aa tagged HFT/MM + Direction Neutral by HyperX yet marketed as copy #1 of 511; 90d funding -$155.9k vs fees $163.2k. (Later part of the raw file says the address was truncated; the full 42-char address does appear in the first pass.) |
| 20 | djkanzen | `x.com/djkanzen/status/2079221726991491284` | 2026-07-20 | C | ● | B07 OK | 2026-07-20 (builder of HyperTracker): 5 live segments (top scalpers, counter scalpers, top day traders, counter day traders, top swing traders); re-query every 1-6h on single-coin performance; wallets can enter a segment in the morning and be removed by evening. |
| 21 | doublezero | `x.com/doublezero/status/2103122298253492244` | 2026-09-24 | C |  | — | 2026-09-24: Edge carries uncapped every-market L4 including HIP-3. |
| 22 | EmberCN | `x.com/EmberCN/status/2104038318551994481` | 2026-09-27 | P |  | A10 PARTLY | 0x9c6a… SOL TWAP long from August into +$22M uPnL in September (address truncated in raw file). |
| 23 | GoHyperTrend | `x.com/GoHyperTrend/status/2058760160903102691` | 2026-05-25 | C |  | — | 2026-05-25: prints an impossible 114% win rate (treated as marketing garbage). |
| 24 | HansonBirringer | `x.com/HansonBirringer/status/2102894931258011901` | 2026-09-23 | B |  | A02 WRONG | Described as 'product + ecosystem research (US/HIP-3)'. The audit also attributes a 2026-09-24 HIP-3 on-chain-mark post to him, with no link. |
| 25 | harmonixfi | `x.com/harmonixfi/status/2100585435198374011` | 2026-09-17 | C |  | — | 2026-09-17: only vaults on app.hyperliquid.xyz/vaults are official; 94.4% of 9,466 vaults hold <$1k (zooted_max quoted); vault L/S grids can bleed funding because vaults cannot hold spot. |
| 26 | hydromancerxyz | `x.com/hydromancerxyz/status/2067990625224425636` | 2026-06-19 | P |  | A03 PARTLY | 2026-06-19: Reservoir = daily requester-pays parquet/S3 of fills with liq/ADL/builder/TWAP splits, HIP-3 included. |
| 27 | hypedexer | `x.com/hypedexer/status/2104553095455973485` | 2026-09-28 | B |  | A19 OK | Cited only as 'Trust Wallet' integration evidence (2026-09-28). |
| 28 | hypedexer | `x.com/hypedexer/status/2104878996232323421` | 2026-09-29 | P |  | A11 PARTLY | Hosted free tier 5,000 credits/month; example endpoints GET /analytics/fills/stats, /twaps/stats, /hip3/overview, /hip3/top-movers, /hip3/auctions/history; 78 read-only MCP tools; fills since Nov 2024. |
| 29 | hypeRankio | `x.com/hypeRankio/status/2096629457981235203` | 2026-09-06 | P |  | A05 PARTLY | Points to article 'discover/compare/simulate/copy'; takeaway 'Profit != copyable; min capital and venue ticket size'. Article body was not opened. |
| 30 | hypeRankio | `x.com/hypeRankio/status/2101640190049550478` | 2026-09-20 | C | ● | B12 OK | 2026-09-20: median minimum copy capital $386 (across 2,278 ranked); proportional median $481; fixed median $185; 17 of 39 wallets with score>=90 copyable under $500; cheapest high score 92 needs $46. |
| 31 | hypeRankio | `x.com/hypeRankio/status/2103800999164960955` | 2026-09-26 | C | ● | B15 OK | 2026-09-26: official board 46,867 rows -> fills inspected on top 7,400 -> 2,720 kept. |
| 32 | hypeRankio | `x.com/hypeRankio/status/2103806591732531551` | 2026-09-26 | C | ● | B16 OK | Fail reasons (overlap allowed): leverage too high 534; margin near max/near liq 490; 30d drawdown too deep 639; near-perfect win rate that doesn't add up 18. Comment: win rate is usually the last number that tells you anything. |
| 33 | hypeRankio | `x.com/hypeRankio/status/2103902033635852518` | 2026-09-26 | C | ● | B17 OK | 2026-09-26: 1,935 wallets with profitable official 30d but flat/negative account-level 30d; vendor drops them. 7 likes. |
| 34 | hypeRankio | `x.com/hypeRankio/status/2104257079913697458` | 2026-09-27 | C |  | — | 2026-09-27: sizing guidance by wallet size (see Section 6.3). |
| 35 | hypeRankio | `x.com/hypeRankio/status/2104257085567324282` | 2026-09-27 | C | ● | B18 PARTLY | 2026-09-27: $100-$500 wallet: fixed $15/order, 3 positions, 20% wallet stop; drop if board 30d green but account 30d flat/red; HL min order $10. |
| 36 | Hyperbotai | `x.com/Hyperbotai/status/2105247944295518213` | 2026-09-30 | P |  | A13 OK | Live tracker address 0x020ca6… 'Machi Big Brother's tracked wallet' used 2026-09-30. Raw file also says a Hyperbotai post of the same date calls 0xbf73… 'Boomer-linked' (unverified nickname). |
| 37 | Hyperfoliofun | `x.com/Hyperfoliofun/status/2105363987680432599` | 2026-09-30 | P |  | A44 OK | Pulse: 1m/5m/15m coin shock tape (not trader skill); 0 likes. |
| 38 | Hyperliquid_Hub | `x.com/Hyperliquid_Hub/status/2104410898605781140` | 2026-09-28 | C |  | — | 2026-09-28: ~$859M perp exposure vs ~$172M equity (~5x), 30d perp PnL -$53M, funding collected ~+$17.3M (~$7.6M from HYPE), all-time portfolio PnL +$92.8M. |
| 39 | HyperTracker | `x.com/HyperTracker/status/2084934622551666917` | 2026-08-05 | C |  | — | 2026-08-05: cohort definitions (Money Printer = all-time realized+unrealized > $1M) and market-wide liquidation stats. |
| 40 | HyperTracker | `x.com/HyperTracker/status/2102762090943652027` | 2026-09-23 | B |  | A01 PARTLY | Cited as source for 'hyperdash/hypertracker expose direction bias; do not treat 100%-long cohort weeks as skill'. Content not stated. |
| 41 | HyperTracker | `x.com/HyperTracker/status/2104914845074403408` | 2026-09-29 | P |  | A12 OK | Raw file ties it to '.hl name search shipped 2026-09-29' (hlnames integration). |
| 42 | Hypervisor_hl | `x.com/Hypervisor_hl/status/2105388466813177969` | 2026-09-30 | B |  | A34 OK | Account replied on 2026-09-30; last feature post the raw file found was 2025-01-11. Content not stated. |
| 43 | hyperx_trade | `x.com/hyperx_trade/status/2100489602935210165` | 2026-09-17 | C | ● | B10 OK | Total score >40, Profit >60, Stability >50, Risk >50, win rate >50%, PnL >$20k, leverage >1x; equity >$20k, realized >$10k, completed trades >10, ROI band 20-50%, median hold >1h. |
| 44 | hyperx_trade | `x.com/hyperx_trade/status/2102973181183332444` | 2026-09-24 | C | ● | B14 OK | Upward equity; drop max DD >50%; Recovery Factor <1000 as anomaly filter; detail veto: inactive 30d, equity <$10k, avg hold <3 min, leverage >25x (historical avg), margin >90%, big-loser/high-risk tags, copy-fee share >70%; prefer active >2 months; hold distribution >1h. |
| 45 | hypurrdash | `x.com/hypurrdash/status/2102120819111453066` | 2026-09-21 | P |  | A08 OK | Raw file says Hyperdash posted 0xbf732e… as #1 month realized +$12.3M (2026-09-21); link not explicitly tied to this tweet. |
| 46 | hypurrdash | `x.com/hypurrdash/status/2102732685839839418` | 2026-09-23 | C |  | — | 2026-09-23: Explore filters (time 1d/7d/30d/all, account value, PnL, style, copy score 0-100); result columns PnL, equity, trades, win rate, Sharpe, max DD, leverage, margin utilization, assets. |
| 47 | hypurrdash | `x.com/hypurrdash/status/2102793170169848172` | 2026-09-23 | C | ● | B13 OK | 2026-09-23: BTC book +$8.57M at 35% win rate, 26 trades, $885M volume. |
| 48 | iam4x | `x.com/iam4x/status/2103414101372547182` | 2026-09-25 | B |  | A17 OK | Cited only as a Proliquid-related post dated 2026-09-25. |
| 49 | iamalijandro | `x.com/iamalijandro/status/2104594759637508543` | 2026-09-28 | B |  | A20 OK | Listed only as supporting the OnchainLens Wintermute post: 'MM / hedge / two-sided inventory'. |
| 50 | ItsBitcoinWorld | `x.com/ItsBitcoinWorld/status/2090309830468837872` | 2026-08-20 | C |  | — | 2026-08-20: lifetime ~+$17.76M, ETH short ~50k ETH/>$100M on ~$16M account; liquidated ~2026-08-20 04:51 CST at ~$2235.36, ~$111.34M notional; realized loss ~$26.66M. |
| 51 | jodezXBT | `x.com/jodezXBT/status/2105285639482826864` | 2026-09-30 | B |  | A23 OK | Listed only as supporting 0xbf732e… (still top-25 by 30d PnL on 2026-09-30, opening an $8.54M 40x BTC short). |
| 52 | joeblau | `x.com/joeblau/status/2081376062177693836` | 2026-07-26 | P |  | A26 PARTLY | 2026-07-26: Bloxwap benchmarked then refactored the nktkas TypeScript SDK; JSR listing 0.33.3. |
| 53 | kamalbuilds | `x.com/kamalbuilds/status/2104342660500918637` | 2026-09-27 | C |  | — | 2026-09-27: finds Nansen Smart Money on same side; measures time from first sale to price -1%; NEAR exit on 2026-09-23 left 1m07s; Sentinel: 242 labelled wallets, poll 30s; waitlist; 18 likes / 482 views. |
| 54 | kamalbuilds | `x.com/kamalbuilds/status/2104343781172744416` | 2026-09-27 | B |  | A33 OK | Listed only as a second Exit Window post (4 likes). Content not stated. |
| 55 | kitsunedevs | `x.com/kitsunedevs/status/2078289569821167805` | 2026-07-18 | C |  | — | 2026-07-18: read-only MCP (markets, funding, OI, books, candles; positions/PnL/liqPx/fills/funding of ANY address); public info API only; 2 source files; zero keys; npx @kitsune-de/hyperliquid-mcp; 3 likes / 24.8k views. |
| 56 | koolkrypto223 | `x.com/koolkrypto223/status/2079224409043423245` | 2026-07-20 | C | ● | B08 PARTLY | 2026-07-20: do not score discretionary books on 'green every month'; expect PnL from 3-5 large trades/year; monthly not-top-10% != unskilled. Self-described top-100 all-time HL PnL; runs a fund; no address posted. |
| 57 | KORypto_JUN | `x.com/KORypto_JUN/status/2104370349593043233` | 2026-09-28 | C |  | — | 2026-09-28: asks for a Dune dashboard of HL wallet win rate; unanswered in retrieved thread. |
| 58 | Kosumi1989 | `x.com/Kosumi1989/status/2083366219940532523` | 2026-08-01 | C |  | — | 2026-08-01: requester-pays S3 L1 archive; candleSnapshot keeps only the most recent 5000 candles. |
| 59 | lbexplorer | `x.com/lbexplorer/status/2094365077734580385` | 2026-08-31 | B |  | A32 PARTLY | Cited only as 'occasional HL trader cards; lower volume than Lookonchain' (2026-08-31). |
| 60 | liquary_xyz | `x.com/liquary_xyz/status/2097696676265791543` | 2026-09-09 | C |  | — | 2026-09-09: HIP-4 prediction markets are purged from the node API shortly after settlement (coin, candles, book, votes); Liquary Data keeps an archive. |
| 61 | liquidbots | `x.com/liquidbots/status/2104581219262529860` | 2026-09-28 | P |  | A29 OK | 2026-09-28: MCP is for their own grid product, not a public trader-research toolkit. |
| 62 | lookonchain | `x.com/lookonchain/status/2067044312979042694` | 2026-06-17 | C |  | — | 2026-06-17: sold 184,102 HYPE for +$2.83M; longs BTC/ZEC/UNI. |
| 63 | lookonchain | `x.com/lookonchain/status/2079045243618705475` | 2026-07-20 | C |  | — | 2026-07-20: 10x long 764.14M PUMP by 0xbf73…; 307 likes. |
| 64 | lookonchain | `x.com/lookonchain/status/2100835870219923791` | 2026-09-18 | P |  | A07 PARTLY | Cited as example of HL flows posted with Arkham entity URLs. The raw file also mentions a 2026-09-18 Lookonchain card on 11 new wallets doing a same-day BTC->ETH rotation (~$20M), with no link or address list. |
| 65 | lookonchain | `x.com/lookonchain/status/2101146737905991689` | 2026-09-19 | C |  | — | 2026-09-19: largest ZEC short, uPnL -$33.66M; BTC long +$4.5M. |
| 66 | lookonchain | `x.com/lookonchain/status/2101962267642511789` | 2026-09-21 | C |  | — | 2026-09-21: Abraxas-labelled 0xb83d… and 0x5b5d…: $1.2B shorts, >$100M uPnL loss. HypurrScan links used. |
| 67 | lookonchain | `x.com/lookonchain/status/2102180844152762532` | 2026-09-21 | C |  | — | 2026-09-21: closed BTC long +$8.38M, flipped to 500 BTC short. |
| 68 | lookonchain | `x.com/lookonchain/status/2103056829211361535` | 2026-09-24 | C |  | — | 2026-09-24: withdrew 147M USDC to Binance; lost $14.7M on HL over 4 months. 328k views cited. |
| 69 | lookonchain | `x.com/lookonchain/status/2104774617328140372` | 2026-09-29 | B |  | A21 OK | Cited only as using a hypurrscan.io link (2026-09-29). |
| 70 | LouMercatali | `x.com/LouMercatali/status/2104311246451335259` | 2026-09-27 | C |  | — | 2026-09-27 reply: homemade MCP over public API for OI/candles/volume; no repo URL (anecdote). |
| 71 | lucas_faster | `x.com/lucas_faster/status/1919348617154101588` | 2025-05-05 | C | ● | B01 OK | 30d window: win rate >=70%, equity >=$10k, realized >=$10k, completed trades 5-100 (>100 ~ bot), ROI >=50%; kill jagged equity curves; prefer many good trades over one lottery hit. |
| 72 | MinaraCN | `x.com/MinaraCN/article/2094646483396284853` | 2026-09-01 | C | ● | B09 PARTLY | 2026-09-01 article. Load full official dump (43,618 rows); keep equity>=$10k, all-time PnL & ROI >0, all-time vol >=$1M, month vol >=$100k; require recent profit across 1d/7d/30d; score PnL+ROI+size+vol+green windows; read fills (assets, frequency, both sides, concentration). |
| 73 | MirrorlyLive | `x.com/MirrorlyLive/status/2105413119061176529` | 2026-09-30 | P |  | A45 OK | High-cadence cards of named Mirrorly traders opening/closing on HL (size, coin, streak); nicknames not always 0x; 0 likes. |
| 74 | MirrorlyLive | `x.com/MirrorlyLive/status/2105417547185082775` | 2026-09-30 | P |  | A46 PARTLY | Same feed; 2026-09-30; 1 like. |
| 75 | OnchainLens | `x.com/OnchainLens/status/2090194368431026576` | 2026-08-19 | C |  | — | 0x0ddf9bae… liquidated on ETH short, realized -$26.66M; lifetime still +$17.76M. |
| 76 | OnchainLens | `x.com/OnchainLens/status/2097320422526374392` | 2026-09-08 | P |  | A06 OK | 0x337afda… (truncated): 7 lifetime liqs, still +$632k perps (2026-09-08). |
| 77 | OnchainLens | `x.com/OnchainLens/status/2100774613898916187` | 2026-09-18 | C |  | — | 2026-09-18: 0xdd53C5297309130ab5fe5623DC905752E3342b13 with $124.59M shorts, 30d PnL -$30.04M. |
| 78 | OnchainLens | `x.com/OnchainLens/status/2103770418196984248` | 2026-09-26 | B |  | A18 OK | Listed only as evidence that @OnchainLens posts daily HL position/PnL cards (2026-09-26). Content not stated. |
| 79 | OnchainLens | `x.com/OnchainLens/status/2104521982863901005` | 2026-09-28 | C |  | — | 2026-09-28: 0xecb63caa47c7c4e77f60f1ce858cf28dc2b82b00, lifetime +$197.22M; shorts $126.25M (ETH $46.92M, SOL $11.30M, HYPE $10.03M); uPnL ~+$963.6K. 140 likes. |
| 80 | OnchainLens | `x.com/OnchainLens/status/2104548751713181882` | 2026-09-28 | C |  | — | 2026-09-28: 0x020ca66c30bec2c4fe3861a94e4db4a498a35872 still opening 40x BTC; lifetime -$29.22M; includes a HypurrScan link. |
| 81 | Papurrrtrade | `x.com/Papurrrtrade/status/2104624033891528719` | 2026-09-28 | P |  | A30 OK | Paper-mode tool claims it uses HL's own margin formula (raw file: 'still not a spec'). |
| 82 | perpyxyz | `x.com/perpyxyz/status/2102035360561643890` | 2026-09-21 | P |  | A40 OK | 2026-09-21 Perpy post (1 like): small-team whale radar app. |
| 83 | perpyxyz | `x.com/perpyxyz/status/2105063133433811317` | 2026-09-29 | P |  | A43 OK | 2026-09-29 (1 like / 38 views): free public TG feed of large longs/shorts, profitable closes, daily recap. |
| 84 | pnlsdaily | `x.com/pnlsdaily/status/2101969403524858192` | 2026-09-21 | P |  | A39 PARTLY | 2026-09-21: HypurrScan links for the Abraxas addresses; used as a source for the 'hedge/basis' framing. |
| 85 | proliquid_xyz | `x.com/proliquid_xyz/status/2105214047364743629` | 2026-09-30 | B |  | A22 OK | Cited only as a Proliquid product post dated 2026-09-30. |
| 86 | reisnertobias | `x.com/reisnertobias/status/2049410876109697529` | 2026-04-29 | C | ● | B04 OK | 2026-04-29: best OIL trader; all-time PnL +$1.4M, volume ~$62.3M; last 30d DD 1.0%, WR 80%, Sharpe 13.15; found on Hyperdash; alerts via @lit_trade. 59 likes. |
| 87 | reisnertobias | `x.com/reisnertobias/status/2049522367680938043` | 2026-04-29 | C | ● | B05 OK | 2026-04-29: equities trader; 30d DD 20.2%, WR 79%, Sharpe 10.58. 42 likes. |
| 88 | rpahlmeyer | `x.com/rpahlmeyer/status/2090227288658886856` | 2026-08-19 | B |  | A15 OK | Listed only as supporting the liquidation story (2026-08-19). |
| 89 | senpi_ai | `x.com/senpi_ai/status/2103499006621925885` | 2026-09-25 | P |  | A28 PARTLY | 2026-09-25: paste address -> read-only hold-time/fee/funding 'leaks'. |
| 90 | shridlock | `x.com/shridlock/status/2102795548784767388` | 2026-09-23 | C |  | — | 2026-09-23: HL API OI $16.70B = $12.71B main + $3.91B xyz HIP-3. |
| 91 | SofiiaBorozan | `x.com/SofiiaBorozan/status/2104233781192528289` | 2026-09-27 | C |  | — | 2026-09-27: classifies an HL whale position as directional bet vs hedge vs MM inventory with evidence and blind spots (Nansen Meridian). 1 like / 55 views. |
| 92 | Story91_ | `x.com/Story91_/status/2103997497743995144` | 2026-09-26 | P |  | A41 OK | Cashboard: infinite canvas, 40+ widgets incl. HL funding/liquidations/whale bets; web free, desktop $29 one-time; Solana token ticker in post. 12 likes. |
| 93 | thedefiedge | `x.com/thedefiedge/status/2016118571483447674` | 2026-01-27 | C | ● | B02 OK | 2026-01-27: HyperTracker watchlist; smaller/unprofitable wallets skew bullish; Hyperdash copy at most 3 wallets, replicate net exposure; filter swing/position; Super (long-only/short-only, token allow/deny, backtester); reject wallets with tons of open positions. |
| 94 | thefofoshow | `x.com/thefofoshow/status/2080053994194346233` | 2026-07-22 | P |  | A36 OK | 2026-07-22: official Python SDK v0.24.0, testnet, 2,283 markets, no secrets stored. |
| 95 | TheRealNajim | `x.com/TheRealNajim/status/2104279935443665174` | 2026-09-27 | C |  | — | 2026-09-27: Discover = Nansen Smart HL Perps Trader cohort; track wallet -> 30d WR, profit factor, equity curve, 0-100 Copy Score; alerts; flock signal. 6 likes / 135 views. |
| 96 | TheRealNajim | `x.com/TheRealNajim/status/2104279942234099811` | 2026-09-27 | C |  | — | Profit factor computed from 30d fills for Copy Score; no numeric cutoff posted. 3 likes. |
| 97 | TheRealNajim | `x.com/TheRealNajim/status/2104279945593630954` | 2026-09-27 | C |  | — | Flock = 2+ tracked traders same side within 15 minutes. |
| 98 | thesogle_ | `x.com/thesogle_/status/2097614408440488189` | 2026-09-09 | C |  | — | 2026-09-09: ignore +1,000% screenshots; ask drawdown and leverage; survivorship (dead vaults leave the list). |
| 99 | totlsota | `x.com/totlsota/status/2079241100544348570` | 2026-07-20 | C |  | — | 2026-07-20: reject any 'top wallet by volume and wildly profitable' that is one leg of a delta-neutral multi-venue book. |
| 100 | VietnamPenguin | `x.com/VietnamPenguin/status/2079091216868835552` | 2026-07-20 | C |  | — | 2026-07-20: said 0xbf73… had ~$9.6M all-time PnL; 0x469e9a… longed ~1B PUMP (~$2M) near $0.002 with ~$12.5M all-time PnL; both 'consistently profitable'. |
| 101 | Yaugourt | `x.com/Yaugourt/status/2100167855765364826` | 2026-09-16 | C |  | — | 2026-09-16 developer thread: 2,000-fill wall; HIP-3 prefix coins; builderFee included in fee; TWAP stats (3,101 TWAPs in 24h, 52.9% finished, 29.4% terminated); Hypedexer MCP with builder codes. |

---

## Appendix B — Non-X link index

Every non-X URL in the raw file (placeholders like `{addr}` and un-expanded `t.co` links removed).

```
https://api.hyperliquid.xyz/info
https://app.coinmarketman.com/hypertracker
https://app.hyperfolio.fun/en/pulse
https://app.hyperliquid.xyz
https://app.hyperliquid.xyz/explorer
https://app.hyperliquid.xyz/leaderboard
https://arkm.com
https://beacontrade.io/leaderboard
https://bet-or-book.trade
https://bitquery.io/datastore/datasets/hyperliquid-trades
https://bloxwap.gitbook.io/hyperliquid/docs/transports
https://cipher-intelligence.io/blog/hyperliquid-copy-trading
https://cipher-intelligence.io/blog/hyperliquid-whale-tracker
https://coinclass.com/hyperliquid/whales
https://dexly.trade/hyperliquid/leaderboard
https://docs.allium.so/historical-chains/supported-blockchains/hyperliquid
https://docs.ccxt.com/#/exchanges/hyperliquid
https://docs.coinmarketman.com/endpoints/leaderboards
https://docs.dune.com/data-catalog/curated/perpetuals/hyperliquid/overview
https://docs.dune.com/data-catalog/curated/perpetuals/hyperliquid/perp-accounts-daily
https://docs.hydromancer.xyz/
https://docs.hydromancer.xyz/reservoir
https://docs.hypedexer.com/quickstart
https://docs.hyperdash.com/wallet-explore
https://docs.liquary.xyz/explore/leaderboard
https://docs.liquary.xyz/explore/whales
https://docs.nansen.ai/api/hyperliquid/perp-screener
https://docs.uniblock.dev/guides/hyperliquid/overview
https://exit-window.fly.dev/waitlist
https://github.com/0xikalgo/hyperliquid-mcp
https://github.com/Aurracloud/hyperliquid-mcp
https://github.com/Dakkshin/hyperliquid-mcp
https://github.com/Sofiia7/bet-or-book
https://github.com/TheRealNajim/PerpPilot
https://github.com/dizcorvus/opencatz-ai
https://github.com/edkdev/hyperliquid-mcp
https://github.com/galleonlabs/hypergrok-trading-desk/blob/main/skills/hyperliquid-api-reference/SKILL.md
https://github.com/hyperliquid-dex/hyperliquid-python-sdk
https://github.com/infinitefield/hypersdk
https://github.com/kitsune-de/hyperliquid-mcp
https://github.com/nktkas/hyperliquid
https://github.com/nomeida/hyperliquid
https://github.com/patricleehua/hyperliquid-trader-mcp
https://goldrush.dev/docs/api-reference/hyperliquid-info/builder-fills
https://higher.money/hyperliquid/leaderboard
https://hypedexer.com
https://hyperank.io/how-scoring-works
https://hyperdash.com
https://hyperdash.com/address/0xbf732ea04197942783e34730ed6e0f6099575d58
https://hyperliquid.gitbook.io/Hyperliquid-docs/for-developers/api/rate-limits-and-user-limits
https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api
https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/hip-3-deployer-actions
https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint
https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/spot.md
https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/nonces-and-api-wallets.md
https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/subscriptions
https://hyperscreener.asxn.xyz/home
https://hyperstats.org
https://hypertracker.io/
https://hyperx.trade/hyperliquid/wallet-discover
https://hypurrscan.io
https://hypurrscan.io/address/0x020ca66c30bec2c4fe3861a94e4db4a498a35872
https://hypurrscan.io/address/0x0ddf9bae2af4b874b96d287a5ad42eb47138a902
https://hypurrscan.io/address/0x3b11267dfc4b9ebe8427e8f557056b4b6ce98112
https://hypurrscan.io/address/0x469e9a7f624b04c24f0e64edf8d8a277e6bf58a5
https://hypurrscan.io/address/0x5b5d51203a0f9079f8aeb098a6523a13f298c060
https://hypurrscan.io/address/0x92ea19ECeB7a8dE0f50978A1583A5D8b018050e9#perps
https://hypurrscan.io/address/0xb83de012dba672c76a7dbbbf3e459cb59d7d6e36
https://hypurrscan.io/address/0xbf732ea04197942783e34730ed6e0f6099575d58#perps
https://hypurrscan.io/address/0xe6503009ee1a648c3775b6b8444afdddb786f1a9
https://hypurrscan.io/address/0xecb63caa47c7c4e77f60f1ce858cf28dc2b82b00
https://isobath.io/
https://jsr.io/@nktkas/hyperliquid
https://legacy.hyperdash.com/
https://mirrorly.xyz/
https://perpfinder.com/tools/whales
https://scarlett.ai/account
https://stats-data.hyperliquid.xyz/Mainnet/leaderboard
https://stats.hyperliquid.xyz/
https://t.me/perpy_hyperliquid
https://t.me/perpyxyz
https://www.coinglass.com/hyperliquid
https://www.hypedexer.com/
https://www.hypermonitor.org/
https://www.hyperpulse.fyi/traders
https://www.perpy.xyz/
https://www.proliquid.xyz/whales
https://www.truehold.xyz/blog/best-hyperliquid-tools
https://www.youtube.com/watch?v=72KUgKEwDrU
```

---

## Appendix C — Address index

| Address | Label (analyst's) | Where used |
|---|---|---|
| `0xecb63caa47c7c4e77f60f1ce858cf28dc2b82b00` | Wintermute (OnchainLens; full address printed in the 2026-09-28 post, Grok C09) | P1 / N4; §10 |
| `0x5b5d51203a0f9079f8aeb098a6523a13f298c060` | Abraxas Capital (HL Hub / Lookonchain) | P2 / N5; §10 |
| `0xb83de012dba672c76a7dbbbf3e459cb59d7d6e36` | Abraxas cluster | P2 / N5; §10 |
| `0xbf732ea04197942783e34730ed6e0f6099575d58` | @solanadoomer1 / 'Boomer' (Hyperbot, Hyperdash — not self-declared) | P3; §14.3; worked example §7.6 |
| `0x469e9a7f624b04c24f0e64edf8d8a277e6bf58a5` | none | P4 |
| `0x3b11267dfc4b9ebe8427e8f557056b4b6ce98112` | OIL specialist (@reisnertobias) | P5 |
| `0xe6503009ee1a648c3775b6b8444afdddb786f1a9` | Equities specialist (@reisnertobias) | P6 |
| `0x92ea19ECeB7a8dE0f50978A1583A5D8b018050e9` | Garrett Jin (Lookonchain) | N1 |
| `0x0ddf9bae2af4b874b96d287a5ad42eb47138a902` | pension-usdt.eth (display name) | N2 |
| `0x020ca66c30bec2c4fe3861a94e4db4a498a35872` | Machi Big Brother | N3 |
| `0xb7e0b9fbc9479330d70bcc82a7d4325a20e8d1aa` | HyperX copy-fit 100 + HFT/MM (DexterOnchain) | N10 — verify |
| `0xdd53C5297309130ab5fe5623DC905752E3342b13` | $124.59M shorts, 30d −$30.04M | §10.2 other rows |
| `0x337afda118de433f5a8c8ad6d6ef48b76d027a06` | 7 lifetime liqs, +$632.0k (30d +$630.1k) | §10.2; §14.3 (A06) |
| `0x9c6a5b4662c722d2c47f43d6c9813cb080ffa4ed` | SOL TWAP long, +$22.43M uPnL | §10.2; §14.3 (A10) |
| `0x77375a8c9d13bf79afb2a87f1b0ac1dfd5f5bf66` | @mk4_lul (OnchainLens) | §10.2; §14.3 (A18, B09) |
| `0xf5629393e446a103a4be1c49a956255e7c87c1d3` | 'Whale 0xf562' spot ZEC sale (Lookonchain) | §10.2; §14.3 (A21) |
| `0xe4c6ae25959d7fc66cf2dd5965fb78c5e09c4048` | Minara: high-turnover example | §14.3 (B09) |
| `0x523852be2db1a76a0e088ecbff32e849544054e5` | Minara: 'perpfumbler' | §14.3 (B09) |
| `0x399965e15d4e61ec3529cc98b7f7ebb93b733336` | Minara: fastest high-turnover | §14.3 (B09) |
| `0x8c625ff57d8a4374784c7eff585dfdc42ccec974` | Minara: DOGE day trader | §14.3 (B09) |
| `0xc926ddba8b7617dbc65712f20cf8e1b58b8598d3` | Minara: small-size scalper | §14.3 (B09) |
| `0x862dd8e68f30693e3d3c9daa42a440bc6d2a1f0c` | Minara: concentrated directional | §14.3 (B09) |
| `0xcb7b6dd3b61c438746d998a4237d7c4cb4eb1efe` | HyperX 'rejected' example (lucas_faster) | §14.3 (B01) |
| `0x9e8b1e51c642f4C8b87c6BA11c53D516a218Afc4` | 'Venom Gibbon' (Mirrorly nickname) | §14.3 (A45) |
| `0x9B864dDE6ED1c21608b1665a0ac0fAA4F7E36e6E` | 'Citadel' (Mirrorly nickname, not the firm) | §14.3 (A46) |
| `0x7491180d3e43719bd8a53cdfbef27a1527a1d90f` | HyperX 90d screen (low-leverage alt long) | §14.3 (C07) |
| `0xb7658d7c63b6c1fc7254fe9402a95d044db70dbc` | HyperX September screen (alt trend long) | §14.3 (C07) |
| `0x07f5b6823751c2e2cd4560f28af75ff887102241` | token contract, **not a trader** | A32; exclude |
| `0xace0a4…03fd`, `0xaeaa…2416`, `0xa5b0…1d41`, `0x880a…311c` | still truncated | §14.3 |
| `0x4000…0000 + dex_index` | HIP-3 backstop liquidator — not a trader | G9; exclude |

---

## Appendix D — Glossary

| Term | Meaning |
|---|---|
| HL / HyperCore | Hyperliquid and its native perp/spot layer; HyperEVM is the EVM layer. |
| HIP-3 | Builder-deployed perp markets (coins prefixed like `xyz:XYZ100`); require `dex` parameters / `allDexs*` calls. |
| HIP-4 | Prediction-style markets purged from the node API after settlement. |
| Vault / HLP | Pooled trading account; leader needs ~5% skin and takes ~10% of profits; no spot, no HIP-3. |
| TWAP | Time-weighted order executed as slices; slices are a separate fill tape. |
| Builder code / builder fee | Fee a front-end adds to a user's trade (cap 0.1%); `fill.fee` already includes it. |
| ADL / backstop | Auto-deleveraging / venue liquidation absorber (HIP-3 backstop address `0x4000…+dex_index`). |
| uPnL / closedPnl | Unrealized PnL / PnL realized by a specific fill (not account net PnL). |
| Official ROI | `pnl / max($100, start_value + max_net_deposits)`. |
| Recovery Factor / Calmar | HyperX helper ratios (standard definitions: net profit ÷ max drawdown; annualized return ÷ max drawdown). |
| Copy score / copy-fit | Vendor measures of followability (Hyperdash 0–100; HyperX copy-fit; Hyperank score) — not skill. |
| Flock | PerpPilot signal: 2+ tracked traders on the same side within 15 minutes. |
| Exit window | Seconds between a smart-money wallet's first sell and price moving −1%. |
| Meridian | Nansen buildathon that produced PerpPilot, Bet or Book, Exit Window, Whale Street. |
| CT | Crypto Twitter. |
