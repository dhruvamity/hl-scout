"""Single-address audit: hydrate -> reconstruct -> reconcile (the `hlscout vet` backbone)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from hlscout.ingest.hydrate import hydrate_deep, raw_path
from hlscout.recon import equity as eq
from hlscout.recon.roundtrips import build_round_trips, perp_only

DAY_MS = 86_400_000


def load_raw(root: Path, address: str) -> dict[str, Any]:
    r = Path(root)
    return {
        "fills": perp_only(pl.read_parquet(raw_path(r, "fills", address))),
        "funding": pl.read_parquet(raw_path(r, "funding", address)),
        "ledger": pl.read_parquet(raw_path(r, "ledger", address)),
        "portfolio": json.loads(raw_path(r, "portfolio", address).with_suffix(".json").read_text()),
    }


def audit(address: str, raw: dict[str, Any]) -> dict[str, Any]:
    fills, funding, ledger, pf = raw["fills"], raw["funding"], raw["ledger"], raw["portfolio"]
    trips, broken = build_round_trips(fills, funding, address)
    flows = eq.flow_events(ledger, address)
    equity = eq.equity_series(pf)
    curve = eq.twr_curve(equity, flows)
    daily = eq.daily_returns(curve)
    inflow = flows.filter(pl.col("flow") > 0)["flow"].sum() if not flows.is_empty() else 0.0
    rec = eq.reconcile(fills, funding, pf, capital=inflow)
    first_fill = int(fills["time"].min()) if not fills.is_empty() else None
    first_ledger = int(ledger["time"].min()) if not ledger.is_empty() else None
    # history looks truncated if fills start long after the account's first ledger activity
    truncated = bool(first_fill and first_ledger and first_fill - first_ledger > 14 * DAY_MS
                     and fills.height >= 9500)
    holds = (trips["close_ts"] - trips["open_ts"]) / 1000 if not trips.is_empty() else None
    return {
        "address": address, "n_fills": fills.height, "n_round_trips": trips.height,
        "coins_with_gaps": sorted(broken), "history_truncated": truncated,
        "reconcile": rec, "reconcile_ok": rec["ok"],
        "net_trading_pnl": rec.get("ours"), "inflow_total": inflow,
        "twr": float(curve["twr_index"][-1] - 1) if not curve.is_empty() else None,
        "max_dd_twr": eq.max_drawdown(curve), "sharpe": eq.sharpe(daily),
        "unstable_intervals": int((~curve["stable"]).sum()) if not curve.is_empty() else 0,
        "median_hold_s": float(holds.median()) if holds is not None else None,
        "liquidations": int(trips["liquidated"].sum()) if not trips.is_empty() else 0,
        "round_trips": trips, "curve": curve,
    }


async def vet_address(info: Any, address: str, root: Path) -> dict[str, Any]:
    await hydrate_deep(info, address, root)
    return audit(address, load_raw(root, address))
