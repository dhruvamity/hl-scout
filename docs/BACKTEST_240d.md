# Backtest of integrity rules (cutoff = 240 days ago)

Wallets with >= 120 d of history before the cutoff, >= 40 round trips before and >= 20 after: **169**. Features use only data before the cutoff; outcomes are measured after it. 'bad' = lost money, or liquidated, or drawdown > 30% in the period after.

Caveat: the pool is leaderboard survivors, so outcomes regress towards the mean for every group; compare groups with each other, not with zero.

## Martingale frequency (share of round trips that scaled into a loser >= 3x), D-R1 vetoes above 10%

| mart_freq | wallets | profitable after | median return after | share 'bad' after | liquidated after |
|---|---|---|---|---|---|
| < 2% | 28 | 79% | +62.0% | 86% | 32% |
| 2-10% | 78 | 83% | +55.3% | 74% | 44% |
| 10-25% (veto zone) | 47 | 83% | +55.7% | 66% | 21% |
| > 25% | 16 | 75% | +21.6% | 56% | 31% |

## Months with a martingale-heavy share of trips (drives G1b)

| mart_months | wallets | profitable after | median return after | share 'bad' after | liquidated after |
|---|---|---|---|---|---|
| no such month | 44 | 80% | +74.7% | 86% | 41% |
| up to a third of months | 52 | 79% | +52.9% | 79% | 42% |
| a third to two thirds | 44 | 84% | +46.1% | 52% | 18% |
| most months | 29 | 86% | +62.1% | 69% | 34% |

## Stricter month rule: months where > 35% of trips are martingale-like

| mart35 | wallets | profitable after | median return after | share 'bad' after | liquidated after |
|---|---|---|---|---|---|
| no such month | 126 | 83% | +54.2% | 76% | 37% |
| up to a third of months | 33 | 82% | +45.4% | 64% | 30% |
| more than a third of months | 10 | 70% | +63.4% | 50% | 10% |

## Months with in-month drawdown > 30% (drives G1b)

| dd_months | wallets | profitable after | median return after | share 'bad' after | liquidated after |
|---|---|---|---|---|---|
| none | 61 | 84% | +39.7% | 66% | 30% |
| < 25% of months | 38 | 68% | +17.0% | 71% | 21% |
| 25-50% of months | 43 | 88% | +88.9% | 67% | 37% |
| > 50% of months | 27 | 85% | +280.4% | 96% | 59% |

## Months with a trip above 25x leverage

| lev25_months | wallets | profitable after | median return after | share 'bad' after | liquidated after |
|---|---|---|---|---|---|
| none | 103 | 84% | +54.2% | 69% | 33% |
| < 25% of months | 40 | 80% | +45.1% | 70% | 30% |
| >= 25% of months | 26 | 73% | +117.1% | 88% | 46% |

## Liquidations before the cutoff (G9)

| liq_pre_c | wallets | profitable after | median return after | share 'bad' after | liquidated after |
|---|---|---|---|---|---|
| 0 | 71 | 80% | +41.2% | 69% | 23% |
| 1 | 32 | 81% | +46.8% | 59% | 22% |
| 2+ | 66 | 83% | +84.8% | 82% | 53% |

## Does each rule separate outcomes? (flagged minus unflagged, 90% bootstrap interval; negative = flagged wallets did worse)

| Rule | flagged | unflagged | return after: flagged - unflagged | 'bad' rate: flagged - unflagged |
|---|---|---|---|---|
| martingale freq > 10% (D-R1 veto) | 63 | 106 | [-34.7%, +8.2%] | [-27%, -2%] |
| any month with martingale-heavy trips | 125 | 44 | [-33.9%, +17.0%] | [-29%, -8%] |
| any month with > 35% martingale-like trips | 43 | 126 | [-32.9%, +11.7%] | [-29%, -2%] |
| >= 1/3 of months with > 35% martingale-like trips | 10 | 159 | [-54.0%, +21.4%] | [-48%, +5%] |
| any month with in-month DD > 30% | 108 | 61 | [-3.2%, +38.8%] | [-1%, +22%] |
| >= 25% of months with DD > 30% | 70 | 99 | [+34.3%, +76.7%] | [-0%, +22%] |
| any month with > 25x leverage | 66 | 103 | [-16.5%, +27.3%] | [-3%, +20%] |
| liquidated before cutoff | 98 | 71 | [+3.2%, +45.0%] | [-6%, +17%] |
