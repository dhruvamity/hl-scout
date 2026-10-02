# HL-Scout — Audit and Forward Plan

| | |
|---|---|
| **Date** | 2026-10-02 |
| **Scope** | Whole repo (`src/`, `tests/`, `scripts/`, `deploy/`, docs), live state in `data/`, the first full run |
| **Goal (unchanged)** | Read-only bot that rebuilds every candidate wallet's true record and keeps only consistent, disciplined intraday traders with 6+ months of genuine history, in two ranked lists (Manual / Algorithmic), with reasons, live monitoring and forward validation. See [PROJECT_PLAN.md](../PROJECT_PLAN.md). |
| **Decisions taken today** | (1) **Two tiers**: strict *Qualified* plus a *Provisional* tier that goes straight into forward tracking. (2) **Data**: public Hyperliquid API + a free Hypedexer key (stored in `.env`, gitignored); no AWS. (3) **Hosting**: this Mac now, a Linux VPS later. (4) **Uses**: follow traders by hand, research watchlist, and a clean feed for a separate automation later (this bot stays read-only). |

---

## 1. Executive summary

**Where we are.** All ten planned phases have code, 74 unit tests pass, and the first full run completed:
46,960 leaderboard wallets → 6,897 passed the free screen → 1,084 passed the cheap per-wallet screen → the best 400 were deep-vetted (101 rejected up front as HFT/market makers) → **311 fully assessed, 0 qualified** (204 failed gates, 77 failed the PnL reconcile, 30 had too little fill history). 717 screened wallets were never deep-vetted because of the 400 cap.

**Verdict.** The pipeline shape is right and the plumbing works, but **the zero is not yet a trustworthy result.** The audit found measurement problems that sit directly under the gates that failed most often. The four that matter most:

1. **The return curve is far too coarse.** Drawdown, Sharpe, t-stat, Deflated Sharpe, the monthly grades and the rescue detector all read equity from Hyperliquid's all-time portfolio series. That series has only **70–120 points over 2–3 years, one every 7–14 days**. Drawdowns between points are invisible. Sharpe is annualised as if the points were daily, so it is inflated about 3×. The Deflated Sharpe test has too few observations to ever pass (2 of 255 wallets did). On the best near-miss this produced a TWR of +93,000% and a drawdown of 30.37% that failed the 30% gate.
2. **Fills are missing.** TWAP order fills come from a separate endpoint (`userTwapSliceFillsByTime`) that we never call. One sampled wallet had 6,821 TWAP fills absent from its history. In 40 reconcile-failed wallets I counted 1,455 mid-history position breaks, so those position histories are wrong. Adding the TWAP fills fixed only part of the breaks on the sample, so at least one more cause remains.
3. **The concentration test is mis-specified.** "Top-5 trades < 35% of net PnL" is applied to the whole history as a veto. As net PnL shrinks toward small positive values the ratio explodes, so it fails almost every high-turnover trader with a modest margin: 177 of 204 failures.
4. **The API budget is not enforced across processes.** The tape, worker and monitor each run their own limiter. Total weight went over the 1,080/min target in **255 of 543 minutes (peak 2,326)**. There were no 429s yet, which also suggests our weight accounting may not match Hyperliquid's.

**Plan in one paragraph.** First fix measurement: TWAP and other missing fills, a daily equity curve rebuilt from fills, real mark prices, and a shared rate limiter. Then rescore the 311 wallets and compare. Recalibrate the concentration and statistical gates, and introduce the Provisional tier. Then widen coverage: vet the other 717 wallets, refresh vetted wallets on a schedule, and add tape-based discovery of traders who aren't on the leaderboard. Then tighten wallet clustering. Then build the three outputs: alerts for following by hand, per-wallet dossiers for research, and a JSON/HTTP feed for later automation. Run it 24/7 on the Mac with a 72-hour and then 14-day soak, freeze the first list, and forward-validate for 30–60 days. VPS migration comes after validation.

---

## 2. Scorecard against the project plan

| Phase | Built | Verified on real data | Main gaps found in this audit |
|---|---|---|---|
| P0 Foundations, rate limiter | Yes | Partly | Limiter is per process, not global (§3, C4) |
| P1 Tape recorder | Yes | No (about 57 hours captured; 72 h soak not run) | Reconnect loop fixed yesterday; nightly compaction has never run (`addr_day_stats` empty); tape not yet used for discovery |
| P2 Universe + S1 screen | Yes | Yes | Leaderboard-only universe; S1 drops wallets whose *current* equity < $5k (traders who withdraw profits) |
| P3 Hydrate + reconstruction | Yes | 20/21 acceptance at P3, but 25% reconcile failures at scale | Missing TWAP fills; coarse equity curve; no marks; no `spotClearinghouseState` (unified margin) |
| P4 Single-wallet detectors | Yes | Partly | Rescue and leverage detectors use stale equity and last-fill prices; concentration mis-specified; no detector evidence persisted |
| P5 Scoring, gates, report | Yes | Yes (first full report) | Statistics run on coarse returns; DSR trial count arbitrary; MDT/ADT classifier weights unvalidated |
| P6 Link graph + multi-wallet | Yes | No | Clusters over-merge (largest has 78 addresses joined by single sends); cluster-level re-scoring is PnL-only |
| P7 Archive | Hypedexer path | Key verified today | Schema mismatches fixed today; credit-limited (§3, H6) |
| P8 Monitor, alerts, tracker | Yes | Tracker yes; monitor no | Watchlist empty; Telegram not configured; no WebSocket user subscriptions |
| P9 Hardening | Code yes | No | launchd not installed; 14-day run not done |
| P10 Forward validation | Code yes | No | Needs a list first |

---

## 3. Audit findings

Severity: **Critical** = can produce a wrong verdict. **High** = big coverage or reliability gap. **Medium** = weakens accuracy or explainability. **Low** = hygiene.

### Critical

**C1. Returns, drawdown and statistics run on a 1–2-week sampling grid.**
- *Evidence.* In `portfolio.perpAllTime.accountValueHistory` the median step is 168–336 hours, 70–120 points per wallet. `twr_curve` turns these into "interval returns". `daily_returns` labels them daily. `sharpe()` annualises with √365.
- *Impact.*
  - **G7:** drawdown is under-measured between points, or distorted by the capital floor.
  - **G11:** T ≈ 100 makes the DSR hurdle near-impossible.
  - **Scoring:** Sharpe and Sortino in the ranking are inflated about 2.7–3.7×.
  - **Monthly grading:** the monthly drawdown check sees 2–4 points per month.
  - **D-M2/D-M3, D-R5/G8, D-R6:** `equity_at()` can be up to 2 weeks stale, so leverage and rescue ratios are wrong when deposits or withdrawals happen between points.
  - Near-miss `0x618d…6e34` shows TWR +93,124%, Sharpe 10.5 and a 30.37% drawdown on $75k net PnL.
- *Fix.* Build a **daily equity curve from our own reconstruction**:
  - Daily components: realised PnL − fees + funding + Δ unrealised (from daily/hourly marks), plus ledger flows.
  - Anchor to the portfolio points, with per-anchor reconcile.
  - Compute returns as daily PnL / start-of-day equity.
  - Use the merged `perpMonth`/`perpWeek`/`perpDay` series (finer resolution) for the recent period.
  - All consumers (G5, G7, G11, monthly grades, D-M*, D-R5/6, G8) switch to it.

**C2. Fill histories are incomplete; TWAP slices in particular are never fetched.**
- *Evidence.*
  - `userFillsByTime` does not return TWAP slice fills; they come only from `userTwapSliceFillsByTime`. Sample wallet `0xa9b9…`: 6,821 TWAP fills, 0 of them in our data. `twap_id` is never populated, so D-B6 (TWAP-dominated) is blind.
  - Across 40 reconcile-failed wallets there are 1,455 mid-history `startPosition` breaks, against 312 benign first-fill breaks.
  - Adding the TWAP fills to the sample fixed 1 of 4 broken coins.
- *Impact.* Wrong positions, wrong round trips (martingale, holds, concentration), and most of the 77 reconcile failures. Good traders can be rejected on bad data.
- *Fix.*
  - Page `userTwapSliceFillsByTime` in `hydrate_deep` and merge it with `twap_id` set.
  - Then investigate the remaining breaks: candidates are liquidation/ADL fills, per-dex fills and sub-account books.
  - Add a "continuity report" per wallet, and treat breaks as `unknown` months rather than silently resyncing.

**C3. The concentration test penalises low-margin traders, not lottery wins.**
- *Evidence.* D-C2 vetoes when top-5 trades > 35% of *net* PnL over the **full** history (G6 repeats the test on 180 days). Example: $1M gross wins, $0.9M gross losses and $50k in the top 5 trades give 50% and a veto. It fired on 177 of 204 failures.
- *Fix.* Measure concentration on robustness instead:
  - **Ex-top-5 test:** PnL excluding the top 5 trades must still be positive.
  - **Top-5 share of gross profit** ≤ 35%.
  - **Best-month share of the sum of positive months** ≤ 40%.
  - D-C2 stays a veto only for true lottery profiles (top-1 trade > 50% of net *and* ex-top-5 PnL ≤ 0).

**C4. The rate budget is not global.**
- *Evidence.* `api_usage` shows 255 of 543 minutes above 1,080 weight, peak 2,326, average 1,318. Each process has its own `RateLimiter`. There have been zero 429s.
- *Impact.* Risk of IP throttling or a ban, and the planned 25% monitor reserve isn't real.
- *Fix.*
  - One **shared token bucket** in SQLite: one row per lane, atomic `UPDATE … RETURNING`. Every process acquires from it.
  - Then measure carefully whether the true limit is higher than our accounting assumes: step up slowly and stop at the first 429.

### High

**H1. Universe is leaderboard-only.**
- *Evidence.* The tape is recorded but never feeds the registry. `addr_day_stats` has never been produced.
- *Impact.* Leaderboard inclusion needs about $100k account value or $10M volume, so small disciplined traders, the plan's main tape benefit, are never seen.
- *Second issue.* S1 drops wallets whose *current* equity is under $5k, which removes traders who withdraw profits.
- *Fix.*
  - Run nightly compaction.
  - Register tape-only addresses.
  - After 30–60 days of tape, screen them on tape statistics.
  - Move the equity floor to S2's median-equity check (G12).

**H2. No incremental refresh.**
- Vetted wallets are never re-pulled, so their data goes stale.
- The daily `universe` job registers new wallets but nothing enqueues them unless the worker restarts.
- `links` queues cluster members that the deep cap then blocks.
- *Fix.* The scheduler should:
  - Enqueue new S1 passes daily.
  - Re-hydrate incrementally: watchlist daily, vetted wallets weekly.
  - Give cluster members of finalists their own budget.

**H3. Shortlist selection bias.**
- The 400 deep vets were picked by all-time PnL ÷ median equity. That favours big lucky multiples, and 717 eligible wallets were never vetted.
- *Fix.*
  - After the measurement fixes, vet all 1,084 (about 18 hours).
  - Rank the queue by a robustness score: consistency of portfolio PnL across weeks plus low drawdown, not a raw multiple.

**H4. Clusters over-merge.**
- *Evidence.*
  - The largest cluster has 78 addresses (23 hydrated), joined mostly by single `send`s of $100 or more.
  - Hubs are detected only by degree within our small local graph, so exchange and bridge wallets aren't recognised as hubs.
- *Impact.* The cluster hedge detector (D-H1) and the lottery detector (D-H4) could veto unrelated wallets.
- *Fix.*
  - Edge strength: hard links (sub-account or agent) count fully. A transfer edge needs ≥ 2 transfers or ≥ $1k.
  - Add a confidence score per cluster and cap cluster size before human QA.
  - Build the hub list from tape-wide counterparty degree plus known bridge and CEX addresses.

**H5. One reconcile failure in four.**
- The residual median is about 6% (scale = peak equity or gross inflows), and roughly 45% of failures are under 5%.
- Causes are mostly C2 (missing fills). The plan also lists unified-margin accounts, which we can't see because `spotClearinghouseState` is never pulled.
- *Fix.* Remeasure after C2. Pull spot state to detect unified margin. Add a `reconcile_soft` band (2–5%) that can reach Provisional at most, never Qualified.

**H6. The archive is credit-bound.**
- Verified schema: `startPosition`, `fee` and liquidation fields are present. `closedPnl`, `dir`, `crossed` and `twapId` are absent, so PnL is derived.
- An active trader costs about 150 credits per month of history, so the free 4,500 credits buy about **25–30 wallet-months a month**.
- Only one wallet currently meets the backfill rule. Today's fixes: UTC timestamps (they were off by 5.5 hours), spot fills dropped, liquidation victim only, 429 backoff, `--dry-run`.
- *Policy.* Spend credits only on Provisional or Qualified wallets that have coverage gaps.

### Medium

| # | Finding | Fix |
|---|---|---|
| M1 | **Mark prices are never fetched** (`data/marks` doesn't exist). Unrealised PnL in rescue, margin-top-up and loss-hiding checks uses the last fill price. D-C7 (beta vs skill) is always silent. | Shared mark store: daily candles for full history (1 call per coin) plus hourly for the last 208 days. Fetch once and share across all wallets. |
| M2 | Leverage is per trip and per coin, not account-wide and time-weighted. G8 margin usage is not evaluated. | Account-level gross notional ÷ daily equity from C1. Margin usage from `marginTable`. |
| M3 | The DSR trial count is `max(N, 5000)`, which is arbitrary. | Use the number of wallets that reached deep vet, logged in the report. |
| M4 | The MDT/ADT classifier uses placeholder weights. `historicalOrders`, which gives cancel ratio and stop-loss usage, is never pulled. | Pull `historicalOrders` for finalists. Hand-label about 50 wallets during QA and fit weights until agreement ≥ 85%. |
| M5 | Detector evidence is never stored (`detector_results` is empty). The report shows gate names, not evidence. | Persist findings with evidence. Write per-wallet dossiers (§4 Phase E). |
| M6 | Test gaps: `recon/equity` (TWR and reconcile) has **0 tests**. There are no calibration or golden tests. `links/audit` and the dashboard are untested. mypy reports 222 errors. | TWR invariants (deposits only → TWR 0), reconcile fixtures, golden wallets from QA, and mypy brought down to zero on core modules. |
| M7 | The tape is young and fragile: about 57 hours, many restarts, gaps logged. Dedupe is in memory only. | 72-hour soak after the limiter fix; nightly compaction; gap report on the tracker. |
| M8 | Monitor: polling only, with no WebSocket user subscriptions (≤ 10 users) and no Telegram. | Phase E1. |

### Low
- `config/config.yaml` is nearly empty, so most thresholds live only in code. Write out the full Appendix C config so tuning is visible and versioned.
- The truncation rule assumes a 10k-fill cap. Measured: median 13.9k fills returned; 64% of wallets have fills covering their whole account life, 84% cover at least 180 days. Use "first fill later than first account activity", confirmed by one API probe, instead of a count.
- Ruff: 9 style findings remain.

### Fixed during this audit (committed)
- `src/hlscout/reports/daily.py` was **untracked**: `.gitignore`'s `reports/` matched it, so a fresh clone couldn't build reports. The rule is now anchored to `/reports/`.
- `hlscout vet` crashed with a NameError. Verified working on a real wallet.
- `scores` grew duplicate `latest` rows on every run (729 rows for 332 wallets). Now one row per wallet.
- Hypedexer: naive timestamps were read as local time; spot fills are now dropped; the liquidation flag is victim-only; 429 backoff added; `backfill --dry-run` added; `.env` loader added. One accidental live call spent 41 credits and wrote no data.

### What is solid
- The funnel design cut 47k wallets to 400 deep vets at about 22 weight per cheap screen.
- The reconcile gate refuses to score bad data, so it errs toward rejection, never toward a false pass.
- Every verdict carries gate values and thresholds.
- The queue is resumable and the worker runs concurrently.
- The tape keep-alive fix holds, and the live tracker works.
- Detectors have synthetic tests.
- The code is read-only by construction, and the security check passes.

---

## 4. Forward plan

Each phase ends with an acceptance check. Estimates are in working sessions (one focused session ≈ a few hours with Claude Code). Wall-clock waits, such as API-bound vetting, tape age and forward validation, are listed separately.

### Phase A — Trustworthy measurement *(first; about 3 sessions)*
1. **Complete fills.**
   - Page `userTwapSliceFillsByTime` and merge it with `twap_id` set.
   - Re-hydrate the 400 wallets incrementally, so only TWAP fills are pulled.
   - Write a continuity report and track down the remaining break causes (liquidation/ADL, per-dex, sub-accounts).
2. **Mark store.**
   - Daily candles for every perp and HIP-3 coin over full history, plus hourly for the last 208 days.
   - Stored once and shared by all wallets.
3. **Daily equity engine.**
   - Daily curve = anchor equity + realised − fees + funding + Δ unrealised + flows.
   - Reconciled at every portfolio anchor.
   - Account-level gross leverage per day.
   - Every gate and detector switched to it, with annualisation fixed.
4. **Unified-margin visibility.** Pull `spotClearinghouseState` on deep vets.
5. **Tests.**
   - TWR invariants, reconcile fixtures, and continuity property tests.
   - A golden test: one real wallet frozen in `tests/golden/` with its expected numbers.
6. **Rescore all 311 and publish a before/after diff:** stage changes and the reason each wallet moved.

*Acceptance:*
- Mid-history breaks fall by at least 80%.
- Reconcile failures drop below 10%.
- Daily-curve cumulative PnL is within 2% of every portfolio anchor on 20 random wallets.
- Deposits only → TWR exactly 0.

### Phase B — Gates, two tiers and calibration *(about 2 sessions, plus your review time)*
1. **Concentration replaced** per C3: ex-top-5 PnL > 0, top-5 share of gross profit, best-month share of positive months.
2. **Statistics:** DSR trial count = number of wallets deep-vetted. Daily T. A bootstrap p-value alongside the t-stat.
3. **Two tiers.**
   - **Qualified:** every gate passes, as in the plan.
   - **Provisional:**
     - Must pass every integrity veto, plus G1, G3, G4, G5, G9, G12 and a clean reconcile (or `reconcile_soft`).
     - May fail **only** G11 (statistical), the G6 concentration parts, G7 within +10 points, or G2 within 10%.
     - Goes straight to forward tracking. After 30–60 days inside its own envelope it graduates to Qualified, or it is dropped.
4. **Sensitivity report.** How many wallets each gate removes, and which verdicts flip under ±10% threshold moves.
5. **Human QA of the top 20 near-misses.** I prepare a dossier for each; you confirm or reject with HypurrScan and Hyperdash. Those verdicts become golden test fixtures and the first MDT/ADT labels.
6. **Config.** The full Appendix C goes into `config/config.yaml`.

*Acceptance:* the gate and tier rules are documented in the report header; the sensitivity report is published; QA disagreements have become fixtures.

### Phase C — Coverage and freshness *(about 2 sessions, plus API wall-clock)*
1. **Shared cross-process rate limiter** (C4). Then a careful limit probe.
2. **Vet the remaining 717 wallets**, about 12–18 hours. The queue is ranked by robustness (H3), not by raw multiple.
3. **Scheduler.**
   - Daily: leaderboard snapshot, then enqueue new S1 passes.
   - Daily: incremental refresh of the watchlist.
   - Weekly: incremental refresh of all vetted wallets.
   - Nightly: tape compaction.
4. **Tape discovery.** Register tape-only addresses now. Enable the tape-based S1 screen once the tape holds 30 days, and tighten it at 60.
5. **S1 change.** Drop the current-equity rule (H1); G12 median equity does that job.
6. **Hypedexer policy.** Credits go only to Provisional and Qualified wallets with coverage gaps. Spend and wallets covered are logged on the tracker.

*Acceptance:* the API stays under the configured cap across all processes for 24 hours; all 1,084 S2 passes are assessed; new leaderboard wallets are queued within 24 hours.

### Phase D — Cluster quality *(about 1 session)*
1. **Edge strength and confidence** (H4); a hub list from tape-wide degree plus a bridge/CEX list.
2. **Cluster-level book.** Merge member fills with intra-cluster transfers netted out, then run gates on the merged book (the plan's §6.6 rule).
3. **QA the 78-address cluster** by hand.

*Acceptance:* no cluster above the size cap without QA; the synthetic hedge and wash pairs are still caught; no unrelated-wallet merges in the QA sample.

### Phase E — Outputs for your three uses *(about 3 sessions)*
1. **Follow by hand.**
   - Monitor the Qualified and Provisional wallets: WebSocket user subscriptions for the top 10, polling for the rest.
   - Telegram alerts for open, add, reduce, close, liquidation, rescue-pattern inflow and drop.
   - A **copyability card** per wallet: median trade notional, minimum copy capital, typical leverage, holding time, and estimated fee and slippage drag.
2. **Research watchlist.**
   - Per-wallet dossier (HTML): gate table with values, detector evidence (timestamps, tx hashes), monthly table, daily equity curve, cluster members and QA links.
   - Weekly summary report.
   - Detector evidence persisted.
3. **Automation feed (read-only).**
   - A versioned `watchlist.json` and an events stream.
   - Local endpoints: `/api/watchlist`, `/api/wallet/{addr}`, `/api/events?since=`.
   - A documented schema. No signing or execution code, ever.

*Acceptance:*
- A simulated liquidation or rescue causes a drop alert within one poll cycle.
- Dossiers render for every Qualified and Provisional wallet.
- The JSON schema validates in a test.

### Phase F — Operations: Mac now, VPS later *(about 1 session, plus wall-clock soaks)*
1. **Mac setup.**
   - Install the launchd services (tape, worker, monitor, scheduler, tracker).
   - `caffeinate`; lid-close on AC set to stay awake.
   - Telegram health alerts.
   - Daily state backup.
2. **Soaks.** 72-hour tape soak (gaps under 0.1% of minutes), then a 14-day unattended run.
3. **VPS-ready.** Dockerfile and systemd units, plus a migration guide (rsync `data/` and `.env`). Move once forward validation shows the list is worth keeping.

### Phase G — Forward validation *(ongoing, 30–60 days)*
- Freeze the first two-tier list after Phase B.
- Weekly forward report: live versus backtest envelope, hit rate, rank correlation, drops and reasons.
- After 30 days, graduate or drop Provisional wallets. After 60 days, write a threshold-tuning and calibration report.
- Plan §14.3 QA loop: each week, 20 random `vet_fail` wallets plus all listed ones.

### Order and timeline
| When | Work | Background, wall-clock |
|---|---|---|
| Days 1–2 | Phase A, then rescore and diff | Tape keeps recording |
| Days 2–3 | Phase B, then your QA of about 20 dossiers | — |
| Days 3–4 | Phase C, then vet the 717 | About 12–18 hours of API time |
| Day 4 | Phase D, then rescore, then **freeze list v1** | — |
| Days 5–6 | Phase E (alerts first, then dossiers, then the feed) | 72-hour tape soak |
| Day 7 | Phase F install | 14-day unattended run starts |
| Weeks 2–9 | Phase G forward validation, plus weekly QA | Tape reaches 30 then 60 days, which enables tape discovery |

---

## 5. Risks and open questions
- **Persistence is weak in general:** about 19% of top-decile wallets stay top-decile the next month. The list is a watchlist that must prove itself, not a promise.
- **The true API limit is unknown.** We exceed our own accounting without 429s. Probe it carefully once, never blindly.
- **Remaining missing-fill causes after TWAP** are unknown until Phase A1 finishes.
- **Hypedexer free credits** cover only about 25–30 wallet-months a month. Very active, long-history traders may stay partly coarse-graded.
- **Invisible hedges** (CEX hedges, CEX-funded sybil wallets) remain undetectable. They are mitigated only by the style gates and QA.

## 6. What I need from you
1. **Security:** the Hypedexer key was pasted in chat. It is stored only in `.env` (mode 600, gitignored). Rotate it later if that transcript is shared.
2. **For Phase E:** a Telegram bot token and your chat id, when you want alerts.
3. **About 1–2 hours of QA time** in Phase B to judge about 20 near-miss dossiers.
4. **Later:** a VPS account when you decide to move off the Mac.
