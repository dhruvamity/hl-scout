"""Single-address audit: hydrate -> reconstruct -> reconcile (the `hlscout vet` backbone)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from hlscout.detectors import run_all, verdict
from hlscout.detectors.automation import classify_algo
from hlscout.detectors.base import build_ctx
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
        "meta": json.loads(raw_path(r, "meta", address).with_suffix(".json").read_text())
        if raw_path(r, "meta", address).with_suffix(".json").exists() else {},
        "states": json.loads(raw_path(r, "state", address).with_suffix(".json").read_text())
        if raw_path(r, "state", address).with_suffix(".json").exists() else [],
    }


def audit(address: str, raw: dict[str, Any]) -> dict[str, Any]:
    fills, funding, ledger, pf = raw["fills"], raw["funding"], raw["ledger"], raw["portfolio"]
    trips, broken = build_round_trips(fills, funding, address)
    flows = eq.flow_events(ledger, address)
    equity = eq.equity_series(pf)
    curve = eq.twr_curve(equity, flows)
    daily = eq.daily_returns(curve)
    inflow = flows.filter(pl.col("flow") > 0)["flow"].sum() if not flows.is_empty() else 0.0
    upnl = sum(float(p["position"]["unrealizedPnl"]) for s in raw.get("states", [])
               for p in s["state"]["assetPositions"])
    rec = eq.reconcile(fills, funding, pf, capital=inflow, unrealized=upnl)
    first_fill = int(fills["time"].min()) if not fills.is_empty() else None
    first_ledger = int(ledger["time"].min()) if not ledger.is_empty() else None
    # history looks truncated if fills start long after the account's first ledger activity
    truncated = bool(first_fill and first_ledger and first_fill - first_ledger > 14 * DAY_MS
                     and fills.height >= 9500)
    if raw.get("meta", {}).get("archive", {}).get("done"):
        truncated = False  # archive pass done: what remains before it is graded coarse
    holds = (trips["close_ts"] - trips["open_ts"]) / 1000 if not trips.is_empty() else None
    meta = raw.get("meta", {})
    ctx = build_ctx(address, fills, funding, ledger, pf, states=raw.get("states", []),
                    role=meta.get("role"), rate_limit=meta.get("rate_limit"),
                    extra_agents=meta.get("extra_agents"), lb=raw.get("lb"), marks=raw.get("marks"),
                    now_ms=raw.get("now_ms"))
    findings = run_all(ctx)
    return {
        "findings": findings, "verdict": verdict(findings), "category": classify_algo(ctx),
        "fills_capped": meta.get("fills_capped", False),
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


def assess_cached(root: Path, address: str, cfg: Any = None, n_trials: int = 5000,
                  extra: list | None = None) -> dict[str, Any]:
    """Run the full decision engine on already-hydrated raw data (no network)."""
    from hlscout.scoring.engine import assess

    raw = load_raw(root, address)
    meta = raw.get("meta", {})
    fills = raw["fills"]
    ctx = build_ctx(address, fills, raw["funding"], raw["ledger"], raw["portfolio"], cfg=cfg,
                    states=raw.get("states", []), role=meta.get("role"),
                    rate_limit=meta.get("rate_limit"), extra_agents=meta.get("extra_agents"))
    ctx.coarse_ok = bool(meta.get("archive", {}).get("done"))
    a = audit(address, raw)
    return assess(ctx, recon_ok=a["reconcile_ok"], history_truncated=a["history_truncated"]
                  or meta.get("fills_capped", False), n_trials=n_trials, extra=extra)
