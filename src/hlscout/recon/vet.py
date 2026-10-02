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
from hlscout.recon.roundtrips import perp_only

DAY_MS = 86_400_000


def load_raw(root: Path, address: str) -> dict[str, Any]:
    r = Path(root)
    from hlscout.recon.marks import daily_mark_provider

    prov = daily_mark_provider(r)
    return {
        "marks_eod": prov,
        "marks": lambda c, t: prov(c, t - DAY_MS),  # strictly-known mark (previous day's close): no look-ahead
        "fills": perp_only(pl.read_parquet(raw_path(r, "fills", address))),
        "funding": pl.read_parquet(raw_path(r, "funding", address)),
        "ledger": pl.read_parquet(raw_path(r, "ledger", address)),
        "portfolio": json.loads(raw_path(r, "portfolio", address).with_suffix(".json").read_text()),
        "meta": json.loads(raw_path(r, "meta", address).with_suffix(".json").read_text())
        if raw_path(r, "meta", address).with_suffix(".json").exists() else {},
        "actions": json.loads(raw_path(r, "actions", address).with_suffix(".json").read_text())
        if raw_path(r, "actions", address).with_suffix(".json").exists() else None,
        "asset_names": __import__("hlscout.ingest.assets", fromlist=["x"]).load_asset_names(r),
        "states": json.loads(raw_path(r, "state", address).with_suffix(".json").read_text())
        if raw_path(r, "state", address).with_suffix(".json").exists() else [],
    }


def make_ctx(address: str, raw: dict[str, Any], cfg: Any = None):
    """One shared analysis context per wallet (round trips, daily curve, timeline are built once)."""
    meta = raw.get("meta", {})
    return build_ctx(address, raw["fills"], raw["funding"], raw["ledger"], raw["portfolio"], cfg=cfg,
                     states=raw.get("states", []), role=meta.get("role"), rate_limit=meta.get("rate_limit"),
                     extra_agents=meta.get("extra_agents"), actions=raw.get("actions"),
                     asset_names=raw.get("asset_names"), lb=raw.get("lb"), marks=raw.get("marks"),
                     marks_eod=raw.get("marks_eod"), now_ms=raw.get("now_ms"))


def audit(address: str, raw: dict[str, Any], ctx: Any = None, cfg: Any = None) -> dict[str, Any]:
    fills, funding, ledger, pf = raw["fills"], raw["funding"], raw["ledger"], raw["portfolio"]
    ctx = ctx or make_ctx(address, raw, cfg)
    trips, broken, flows, curve = ctx.trips, ctx.broken_coins, ctx.flows, ctx.curve
    daily = eq.daily_returns(curve)
    inflow = flows.filter(pl.col("flow") > 0)["flow"].sum() if not flows.is_empty() else 0.0
    upnl = sum(float(p["position"]["unrealizedPnl"]) for s in raw.get("states", [])
               for p in s["state"]["assetPositions"])
    # reconcile over the reliable window only (ctx.fills is already cut); start at the first platform point
    # at/after the cut so the platform delta covers the same period
    start = None
    if ctx.reliable_since is not None:
        pts = [t for t in eq.equity_series(pf)["time"].to_list() if t >= ctx.reliable_since]
        start = pts[0] if pts else ctx.reliable_since
    rec = eq.reconcile(ctx.fills, funding, pf, start_ms=start, capital=inflow, unrealized=upnl)
    fills = ctx.fills
    first_fill = int(fills["time"].min()) if not fills.is_empty() else None
    first_ledger = int(ledger["time"].min()) if not ledger.is_empty() else None
    # history looks truncated if fills start long after the account's first ledger activity
    truncated = bool(first_fill and first_ledger and first_fill - first_ledger > 14 * DAY_MS
                     and fills.height >= 9500)
    now_ms = raw.get("now_ms") or int(__import__("time").time() * 1000)
    covered = bool(first_fill) and (now_ms - first_fill) / DAY_MS >= 180
    cut = ctx.reliable_since is not None  # fills before the last material break were discarded
    if cut:
        truncated = True  # earlier history is missing even if the account's first ledger entry is recent
    partial = truncated and covered  # recent fills span >= 180 d: older months are graded coarse
    if partial:
        truncated = False
    meta = raw.get("meta", {})
    if meta.get("archive", {}).get("done"):
        truncated = False  # archive pass done: what remains before it is graded coarse
    holds = (trips["close_ts"] - trips["open_ts"]) / 1000 if not trips.is_empty() else None
    findings = run_all(ctx)
    return {
        "findings": findings, "verdict": verdict(findings), "category": classify_algo(ctx),
        "fills_capped": meta.get("fills_capped", False),
        "address": address, "n_fills": fills.height, "n_round_trips": trips.height,
        "coins_with_gaps": sorted(broken), "history_truncated": truncated, "partial_history": partial,
        "reliable_since": ctx.reliable_since, "material_breaks": ctx.n_material_breaks,
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
    ctx = make_ctx(address, raw, cfg)
    a = audit(address, raw, ctx)
    ctx.coarse_ok = bool(meta.get("archive", {}).get("done")) or a["partial_history"]
    return assess(ctx, recon_ok=a["reconcile_ok"], recon_soft=a["reconcile"].get("soft", False)
                  and not a["reconcile_ok"], history_truncated=a["history_truncated"]
                  or meta.get("fills_capped", False), n_trials=n_trials, extra=extra)
