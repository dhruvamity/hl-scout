# Backtest of integrity rules (cutoff = 120 days ago)

Wallets with >= 120 d of history before the cutoff, >= 40 round trips before and >= 20 after: **223**. Features use only data before the cutoff; outcomes are measured after it. 'bad' = lost money, or liquidated, or drawdown > 30% in the period after.

Caveat: the pool is leaderboard survivors, so outcomes regress towards the mean for every group; compare groups with each other, not with zero.

## Martingale frequency (share of round trips that scaled into a loser >= 3x), D-R1 vetoes above 10%

| mart_freq | wallets | profitable after | median return after | share 'bad' after | liquidated after |
|---|---|---|---|---|---|
| < 2% | 38 | 92% | +60.5% | 63% | 16% |
| 2-10% | 96 | 83% | +75.9% | 62% | 24% |
| 10-25% (veto zone) | 69 | 78% | +46.1% | 61% | 25% |
| > 25% | 20 | 80% | +44.7% | 55% | 15% |

## Months with a martingale-heavy share of trips (drives G1b)

| mart_months | wallets | profitable after | median return after | share 'bad' after | liquidated after |
|---|---|---|---|---|---|
| no such month | 51 | 90% | +69.9% | 55% | 24% |
| up to a third of months | 74 | 84% | +74.7% | 69% | 20% |
| a third to two thirds | 49 | 84% | +60.4% | 57% | 22% |
| most months | 49 | 73% | +31.8% | 61% | 22% |

## Stricter month rule: months where > 35% of trips are martingale-like

| mart35 | wallets | profitable after | median return after | share 'bad' after | liquidated after |
|---|---|---|---|---|---|
| no such month | 165 | 85% | +67.3% | 62% | 23% |
| up to a third of months | 43 | 74% | +46.1% | 60% | 21% |
| more than a third of months | 15 | 87% | +68.6% | 53% | 13% |

## Months with in-month drawdown > 30% (drives G1b)

| dd_months | wallets | profitable after | median return after | share 'bad' after | liquidated after |
|---|---|---|---|---|---|
| none | 84 | 81% | +47.4% | 51% | 15% |
| < 25% of months | 65 | 71% | +29.3% | 60% | 20% |
| 25-50% of months | 45 | 96% | +138.9% | 64% | 24% |
| > 50% of months | 29 | 97% | +207.9% | 90% | 41% |

## Months with a trip above 25x leverage

| lev25_months | wallets | profitable after | median return after | share 'bad' after | liquidated after |
|---|---|---|---|---|---|
| none | 116 | 84% | +63.3% | 59% | 20% |
| < 25% of months | 78 | 87% | +63.6% | 56% | 21% |
| >= 25% of months | 29 | 69% | +70.9% | 83% | 34% |

## Liquidations before the cutoff (G9)

| liq_pre_c | wallets | profitable after | median return after | share 'bad' after | liquidated after |
|---|---|---|---|---|---|
| 0 | 96 | 79% | +39.9% | 54% | 2% |
| 1 | 40 | 80% | +85.9% | 55% | 22% |
| 2+ | 87 | 89% | +69.9% | 72% | 44% |

## Does each rule separate outcomes? (flagged minus unflagged, 90% bootstrap interval; negative = flagged wallets did worse)

| Rule | flagged | unflagged | return after: flagged - unflagged | 'bad' rate: flagged - unflagged |
|---|---|---|---|---|
| martingale freq > 10% (D-R1 veto) | 89 | 134 | [-33.6%, +6.9%] | [-14%, +7%] |
| any month with martingale-heavy trips | 172 | 51 | [-43.5%, +2.4%] | [-4%, +21%] |
| any month with > 35% martingale-like trips | 58 | 165 | [-39.8%, +8.4%] | [-16%, +8%] |
| >= 1/3 of months with > 35% martingale-like trips | 15 | 208 | [-19.4%, +52.5%] | [-30%, +14%] |
| any month with in-month DD > 30% | 139 | 84 | [+6.9%, +47.7%] | [+5%, +28%] |
| >= 25% of months with DD > 30% | 74 | 149 | [+49.4%, +88.0%] | [+9%, +29%] |
| any month with > 25x leverage | 107 | 116 | [-9.3%, +31.3%] | [-6%, +15%] |
| liquidated before cutoff | 127 | 96 | [+12.8%, +54.0%] | [+2%, +24%] |
