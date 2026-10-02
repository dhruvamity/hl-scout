# Roadmap status (updated 2026-10-02, after executing the audit plan)

Plan: [AUDIT_AND_PLAN.md](AUDIT_AND_PLAN.md). Spec: [../PROJECT_PLAN.md](../PROJECT_PLAN.md).

## Phase A — trustworthy measurement: DONE (with one open data-quality issue)
| Item | Result |
|---|---|
| Daily equity engine | `recon/daily.py`: daily PnL = realised − fees + funding + Δunrealised (daily marks), flows, re-anchored to every platform point; feeds G5/G7/G11, monthly grades, rescue/leverage detectors. Sharpe is now truly daily |
| Mark store | `hlscout marks`: daily candles, one call per coin, 457 coins stored (HIP-4 `#` outcome coins have no candles and are skipped) |
| TWAP fills | `userTwapSliceFillsByTime` is paged and merged (135k slice fills added across 335 wallets). Minor effect on continuity (−12% breaks) |
| **Missing-fill root cause** | The public API silently drops OLD fills even when it returns some: Hypedexer shows 10–20× more fills than the API for older months of a heavy wallet (23,108 vs 1,201), while recent windows agree within 0.3%. Fix: `reliable_since` cuts fills at the last material position-continuity break; earlier months are graded coarse; archive backfill targets that span |
| Reconcile | failures 78 → 29 of 311 (9.3%, target < 10%); first-fill off-by-one fixed; `reconcile_soft` (2–5%) caps at Provisional |
| Tests | equity/TWR/reconcile/continuity/daily-engine tests added (102 total) |
| Open issue | Even after the reliable-window cut, why some positions "vanish" without fills (e.g. AI16Z, Feb 2025) is unexplained; Hypedexer has no data for that window. Affected wallets are handled conservatively (coarse months) |

## Phase B — gates, two tiers, calibration: CODE DONE, NEEDS YOUR QA
* `provisional` tier, `decide_stage` shared by live scoring and the sensitivity report.
* Robust concentration (ex-top-5, gross-profit shares) is the default in `config/config.yaml`; legacy mode kept for comparison.
* `n_trials` = wallets actually vetted. Full Appendix C config written.
* `hlscout sensitivity` → `reports/sensitivity.md`. Finding: after Phase A the only gate that removes wallets by itself is **G1b (genuine throughout)**,
  driven by month-level reasons (martingale 305 month-instances, monthly drawdown 192, liquidations 145, leverage>25x 100, rescue 61).
  No threshold was loosened without your review.
* Your QA step (dossiers for the closest misses) is pending the full run.

## Phase C — coverage and freshness: IN PROGRESS
* Shared cross-process rate limiter (`data/ratelimit.sqlite`): done. API weight stays at the cap; a 429 in one process pauses all.
* Light screen over +1,160 newly eligible wallets (equity floor moved to G12; leaderboard refreshed) and quick pre-vet (one `userFills` call:
  HFT/MM, own liquidations, hold-time band, martingale) before the expensive pull: done, running.
* Scheduler jobs: universe → enqueue → tape discovery → refresh watchlist → links → score → weekly refresh of all → backup: done.
* Tape discovery: code done; becomes useful after ≥ 30 days of tape (about 4 days recorded).
* Hypedexer: credit-budgeted, planned backfill windows and affordability filter: done; spends nothing until candidates exist.

## Phase D — clusters: DONE
Strong-edge rule (hard link, ≥ 2 transfers or ≥ $1k), known hubs (Bridge2), cluster confidence, vetoes from oversized (> 12) or weak (< 0.4) clusters are demoted to FLAGs.
Cluster-level merged-book gates are NOT built (PnL-level checks only).

## Phase E — outputs: DONE except live WebSocket subscriptions and Telegram credentials
* Per-wallet HTML dossiers (`hlscout dossier`), copyability card, detector evidence persisted, read-only JSON feed (`docs/API.md`).
* Monitor: polling alerts; Telegram needs `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` in `.env`. WebSocket user subscriptions (≤ 10 wallets) not built; polling at 30–120 s covers the need.

## Phase F — operations: CODE DONE, NOT INSTALLED
launchd plists (5 services), systemd units, Dockerfile, `docs/DEPLOY.md`. Installing the services and the 72-hour / 14-day soaks are left for you to trigger.

## Phase G — forward validation: NOT STARTED (needs a frozen list; 30–60 days)
`hlscout freeze` / `hlscout forward` exist.
