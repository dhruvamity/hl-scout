# Calibration decision: martingale rule (2026-10-03)

**Question.** Should the martingale veto (D-R1) and the monthly drawdown / leverage rules be calibrated?
**Method.** Pseudo-forward backtest (`scripts/backtest_rules.py`): for each wallet, compute the rule features using only data before a
cutoff, then measure outcomes after it (profitable, return on equity, liquidation, drawdown > 30%, "bad" = any of loss / liquidation /
drawdown > 30%). Two cutoffs: 120 days ago (223 wallets) and 240 days ago (169 wallets). Reports: `docs/BACKTEST_120d.md`, `docs/BACKTEST_240d.md`.
Reproduce: `uv run python scripts/backtest_rules.py --days 120`.

| Rule | Evidence | Decision |
|---|---|---|
| Martingale freq > 10% (veto) | Flagged wallets did not do worse after the cutoff. 'Bad' rate difference (flagged − unflagged) 90% interval: [−14%, +7%] at 120 d, [−27%, −2%] at 240 d (flagged did *better* on risk). Return difference includes zero both times. A stricter month rule (> 35% of trips) shows the same | **Demoted to FLAG** (> 10%); VETO only above 50% of round trips. No longer a "not genuine" month reason |
| Monthly in-month DD > 30% | Predicts risk: 'bad' rate +5…+29 points, more later liquidations (41% vs 15% in the heaviest group). Returns are higher for these wallets (risk-taking pays on average in this pool) | **Keep** (the target is disciplined, low-drawdown traders) |
| Trip leverage > 25x | Weak overall (intervals include zero); heavy users (≥ 25% of months) have a 83% vs 59% 'bad' rate and 34% vs 20% later liquidation | **Keep** |
| Liquidation before cutoff (G9) | 44% of wallets with 2+ liquidations were liquidated again vs 2% with none | **Keep** |

**Why calibrate only this one.** A rule should keep a veto only if flagged wallets do measurably worse. Martingale fails that test; the others pass it.
Loosening everything to "get a list" would be fitting thresholds to the answer we want.

**Caveats.** Small samples (169–223), overlapping windows, leaderboard survivors only (everything regresses towards the mean), and 'bad' includes
drawdown persistence. Re-run when the pool is larger and after forward validation produces real out-of-sample data. The martingale rule still
reduces the score and counts toward the three-family manual-review queue.
