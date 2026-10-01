"""Synthetic wallet builders for detector tests."""

from __future__ import annotations

import random

import polars as pl

from hlscout.detectors.base import build_ctx
from hlscout.ingest.hydrate import FILL_SCHEMA, FUNDING_SCHEMA, LEDGER_SCHEMA

DAY = 86_400_000
HOUR = 3_600_000
ADDR = "0x" + "a" * 40


class Wallet:
    def __init__(self, t0: int = 1_700_000_000_000):
        self.fills, self.ledger, self.eq, self.pnl = [], [], [], []
        self.pos: dict[str, float] = {}
        self.i = 0
        self.t0 = t0

    def fill(self, t, coin, side, sz, px, pnl=0.0, fee=0.05, crossed=True, dir_="", liq=None, oid=None):
        sp = self.pos.get(coin, 0.0)
        self.i += 1
        self.fills.append({"time": t, "coin": coin, "px": px, "sz": sz, "side": side, "dir": dir_,
                           "start_position": sp, "closed_pnl": pnl, "fee": fee, "crossed": crossed,
                           "oid": oid if oid is not None else self.i, "tid": self.i, "twap_id": None,
                           "fee_token": "USDC", "liquidation": liq, "hash": "h"})
        self.pos[coin] = sp + (sz if side == "B" else -sz)

    def trip(self, t, coin="BTC", side="B", sz=1.0, px=100.0, exit_px=101.0, hold=HOUR, **kw):
        sign = 1 if side == "B" else -1
        self.fill(t, coin, side, sz, px)
        self.fill(t + hold, coin, "A" if side == "B" else "B", sz, exit_px,
                  pnl=sign * (exit_px - px) * sz, **kw)

    def deposit(self, t, usdc):
        self.ledger.append({"time": t, "hash": f"d{t}", "type": "deposit", "usdc": usdc, "user": None,
                            "destination": None, "token": None, "amount": None, "to_perp": None,
                            "fee": None, "raw_json": "{}"})

    def equity(self, t, e, cum_pnl):
        self.eq.append((t, e, cum_pnl))

    def ctx(self, **kw):
        eq = sorted(self.eq)
        pf = {"perpAllTime": {"accountValueHistory": [[t, str(e)] for t, e, _ in eq],
                              "pnlHistory": [[t, str(p)] for t, _, p in eq]},
              "perpMonth": {"accountValueHistory": [], "pnlHistory": kw.pop("month_pnl", [])}}
        now = kw.pop("now_ms", (max(t for t, _, _ in eq) if eq else self.t0) + DAY)
        return build_ctx(
            ADDR, pl.DataFrame(self.fills, schema=FILL_SCHEMA),
            pl.DataFrame([], schema=FUNDING_SCHEMA),
            pl.DataFrame(self.ledger, schema=LEDGER_SCHEMA), pf, now_ms=now, **kw)


def clean_wallet(n_trips=150, days=240, seed=1, equity0=20_000.0) -> Wallet:
    """Disciplined intraday trader: ~1h holds, steady small edge, low leverage, human hours."""
    rnd = random.Random(seed)
    w = Wallet()
    e, cum = equity0, 0.0
    w.deposit(w.t0 - HOUR, equity0)
    w.equity(w.t0 - HOUR, equity0, 0.0)
    for k in range(n_trips):
        day = int(k * days / n_trips)
        t = w.t0 + day * DAY + (13 + rnd.randint(0, 6)) * HOUR + rnd.randint(0, 3000) * 1000
        win = rnd.random() < 0.55
        move = rnd.uniform(0.3, 1.2) if win else -rnd.uniform(0.2, 0.9)
        coin = rnd.choice(["BTC", "ETH", "SOL"])
        w.trip(t, coin, rnd.choice("BA"), sz=1.0, px=100.0, exit_px=100.0 + move * 1.0,
               hold=int(rnd.uniform(0.3, 3) * HOUR))
        pnl = move * 1.0 * 20 * (1 if True else 0)
        e += pnl
        cum += pnl
        w.equity(t + 4 * HOUR, e, cum)
    return w
