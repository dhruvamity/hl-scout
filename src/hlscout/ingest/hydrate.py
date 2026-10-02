"""Hydrator: pull raw per-address data via the Info API and persist it as Parquet (plan §4.2).

Raw files live at data/raw/<kind>/<address>.parquet and are merged incrementally. Fills use
aggregateByTime=false so scale-in clips stay visible (compendium G13).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Protocol

import polars as pl

log = logging.getLogger(__name__)

FILLS_PAGE = 2000
FUNDING_PAGE = 500
MAX_FILLS = 60_000  # hard stop for market-maker-sized books; flagged as capped
FILL_CAP_SUSPECT = 9500  # public API retains only ~10k most recent fills


class Poster(Protocol):
    async def post(self, payload: dict[str, Any], lane: str = ...) -> Any: ...


FILL_SCHEMA = {
    "time": pl.Int64, "coin": pl.Utf8, "px": pl.Float64, "sz": pl.Float64, "side": pl.Utf8,
    "dir": pl.Utf8, "start_position": pl.Float64, "closed_pnl": pl.Float64, "fee": pl.Float64,
    "crossed": pl.Boolean, "oid": pl.Int64, "tid": pl.Int64, "twap_id": pl.Int64,
    "fee_token": pl.Utf8, "liquidation": pl.Utf8, "hash": pl.Utf8,
}
FUNDING_SCHEMA = {"time": pl.Int64, "coin": pl.Utf8, "usdc": pl.Float64, "szi": pl.Float64,
                  "funding_rate": pl.Float64}
LEDGER_SCHEMA = {"time": pl.Int64, "hash": pl.Utf8, "type": pl.Utf8, "usdc": pl.Float64,
                 "user": pl.Utf8, "destination": pl.Utf8, "token": pl.Utf8, "amount": pl.Float64,
                 "to_perp": pl.Boolean, "fee": pl.Float64, "raw_json": pl.Utf8}


def _f(x: Any) -> float | None:
    return None if x is None else float(x)


def norm_fill(r: dict[str, Any]) -> dict[str, Any]:
    liq = r.get("liquidation")
    return {
        "time": int(r["time"]), "coin": r["coin"], "px": float(r["px"]), "sz": float(r["sz"]),
        "side": r["side"], "dir": r.get("dir", ""), "start_position": _f(r.get("startPosition")),
        "closed_pnl": float(r.get("closedPnl") or 0), "fee": float(r.get("fee") or 0),
        "crossed": r.get("crossed"), "oid": r.get("oid"), "tid": r.get("tid"),
        "twap_id": r.get("twapId"), "fee_token": r.get("feeToken"),
        "liquidation": json.dumps(liq) if liq else None, "hash": r.get("hash"),
    }


def norm_funding(r: dict[str, Any]) -> dict[str, Any]:
    d = r["delta"]
    return {"time": int(r["time"]), "coin": d["coin"], "usdc": float(d["usdc"]),
            "szi": _f(d.get("szi")), "funding_rate": _f(d.get("fundingRate"))}


def norm_ledger(r: dict[str, Any]) -> dict[str, Any]:
    d = r["delta"]
    usdc = d.get("usdc")
    if usdc is None:
        usdc = d.get("usdcValue")
    return {
        "time": int(r["time"]), "hash": r.get("hash"), "type": d["type"], "usdc": _f(usdc),
        "user": d.get("user"), "destination": d.get("destination"), "token": d.get("token"),
        "amount": _f(d.get("amount")), "to_perp": d.get("toPerp"), "fee": _f(d.get("fee")),
        "raw_json": json.dumps(d),
    }


async def page_forward(
    info: Poster, payload: dict[str, Any], start: int, page: int, lane: str, key: str,
    max_rows: int | None = None,
) -> list[dict[str, Any]]:
    """Page a time-ascending endpoint forward from `start`; dedupes on `key(row)`."""
    out: list[dict[str, Any]] = []
    seen: set[Any] = set()
    while True:
        rows = await info.post({**payload, "startTime": start}, lane=lane)
        if not rows:
            break
        fresh = 0
        for r in rows:
            k = r.get(key) if key in r else json.dumps(r, sort_keys=True)
            if k not in seen:
                seen.add(k)
                out.append(r)
                fresh += 1
        last = int(rows[-1]["time"])
        if len(rows) < page or (max_rows and len(out) >= max_rows):
            break
        start = last if fresh else last + 1
    return out


def _merge_write(path: Path, new: pl.DataFrame, subset: list[str]) -> pl.DataFrame:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        new = pl.concat([pl.read_parquet(path), new], how="diagonal_relaxed")
    new = new.unique(subset=subset, keep="last", maintain_order=True).sort("time")
    tmp = path.with_suffix(".tmp")
    new.write_parquet(tmp, compression="zstd")
    tmp.rename(path)
    return new


def raw_path(root: Path, kind: str, address: str) -> Path:
    return root / "raw" / kind / f"{address}.parquet"


def last_time(root: Path, kind: str, address: str) -> int:
    p = raw_path(root, kind, address)
    return int(pl.read_parquet(p, columns=["time"])["time"].max()) if p.exists() else 0


async def page_twap(info: Poster, address: str, start: int, lane: str,
                    max_rows: int = 200_000) -> list[dict[str, Any]]:
    """TWAP slice fills live only on `userTwapSliceFillsByTime` ([{fill, twapId}], <=2000/call, ascending);
    `userFillsByTime` never returns them, which silently breaks position continuity."""
    out: list[dict[str, Any]] = []
    seen: set[Any] = set()
    while True:
        rows = await info.post({"type": "userTwapSliceFillsByTime", "user": address, "startTime": start},
                               lane=lane)
        if not rows:
            break
        fresh = 0
        for r in rows:
            f = {**r["fill"], "twapId": r.get("twapId")}
            if f["tid"] not in seen:
                seen.add(f["tid"])
                out.append(f)
                fresh += 1
        last = int(rows[-1]["fill"]["time"])
        if len(rows) < FILLS_PAGE or len(out) >= max_rows or not fresh:
            break
        start = last
    return out


def last_twap_time(root: Path, address: str) -> int:
    p = raw_path(root, "fills", address)
    if not p.exists():
        return 0
    t = pl.read_parquet(p, columns=["time", "twap_id"]).filter(pl.col("twap_id").is_not_null())
    return int(t["time"].max()) if not t.is_empty() else 0


async def hydrate_twap(info: Poster, address: str, root: Path, lane: str = "deep_vet") -> int:
    """Merge TWAP slice fills into the wallet's fills file. Incremental; returns rows fetched."""
    root = Path(root)
    p = raw_path(root, "fills", address)
    start = max(0, last_twap_time(root, address) - 1)
    if start == 0 and p.exists():  # first pull: from the wallet's first known fill (or ledger) onward
        led = raw_path(root, "ledger", address)
        firsts = [int(pl.read_parquet(p, columns=["time"])["time"].min())]
        if led.exists():
            lt = pl.read_parquet(led, columns=["time"])
            if not lt.is_empty():
                firsts.append(int(lt["time"].min()))
        start = min(firsts)
    rows = await page_twap(info, address, start, lane)
    if rows:
        _merge_write(p, pl.DataFrame([norm_fill(r) for r in rows], schema=FILL_SCHEMA), ["coin", "tid"])
    return len(rows)


async def hydrate_light(info: Poster, address: str, lane: str = "light_hydrate",
                        with_role: bool = True) -> dict[str, Any]:
    """userRole costs weight 60 vs ~20 for portfolio: the S2 pass skips it (deep vet checks it)."""
    role = await info.post({"type": "userRole", "user": address}, lane=lane) if with_role else None
    portfolio = await info.post({"type": "portfolio", "user": address}, lane=lane)
    state = await info.post({"type": "clearinghouseState", "user": address}, lane=lane)
    return {"role": role, "portfolio": dict(portfolio), "state": state}


async def hydrate_deep(info: Poster, address: str, root: Path, lane: str = "deep_vet") -> dict[str, Any]:
    """Fetch fills, funding, ledger, portfolio, role, sub-accounts, state. Incremental by time."""
    root = Path(root)
    light = await hydrate_light(info, address, lane)
    fills_raw = await page_forward(
        info, {"type": "userFillsByTime", "user": address, "aggregateByTime": False},
        max(0, last_time(root, "fills", address) - 1), FILLS_PAGE, lane, "tid", max_rows=MAX_FILLS)
    fills = _merge_write(
        raw_path(root, "fills", address),
        pl.DataFrame([norm_fill(r) for r in fills_raw], schema=FILL_SCHEMA), ["coin", "tid"])
    await hydrate_twap(info, address, root, lane)
    fills = pl.read_parquet(raw_path(root, "fills", address))
    fund_raw = await page_forward(
        info, {"type": "userFunding", "user": address}, last_time(root, "funding", address),
        FUNDING_PAGE, lane, "__nokey__")
    _merge_write(
        raw_path(root, "funding", address),
        pl.DataFrame([norm_funding(r) for r in fund_raw], schema=FUNDING_SCHEMA),
        ["time", "coin"])
    led_raw = await page_forward(
        info, {"type": "userNonFundingLedgerUpdates", "user": address},
        last_time(root, "ledger", address), FUNDING_PAGE, lane, "__nokey__")
    _merge_write(
        raw_path(root, "ledger", address),
        pl.DataFrame([norm_ledger(r) for r in led_raw], schema=LEDGER_SCHEMA),
        ["hash", "type", "time"])
    dexes = [""] + sorted({c.split(":")[0] for c in fills["coin"].unique().to_list() if ":" in c})
    states = []
    for d in dexes:  # per-dex state: the default call misses HIP-3 books (G8)
        st = light["state"] if d == "" else await info.post(
            {"type": "clearinghouseState", "user": address, "dex": d}, lane=lane)
        states.append({"dex": d, "state": st})
    sp = raw_path(root, "state", address).with_suffix(".json")
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps(states))
    meta = {
        "role": light["role"],
        "rate_limit": await info.post({"type": "userRateLimit", "user": address}, lane=lane),
        "extra_agents": await info.post({"type": "extraAgents", "user": address}, lane=lane),
        "fills_capped": len(fills_raw) >= MAX_FILLS,
    }
    subs = await info.post({"type": "subAccounts", "user": address}, lane=lane)
    meta["subaccounts"] = subs or []
    mp = raw_path(root, "meta", address).with_suffix(".json")
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(json.dumps(meta))
    explorer = getattr(info, "explorer_user_details", None)
    if explorer is not None:  # only the margin/leverage actions matter; orders are bulky
        txs = await explorer(address, lane=lane)
        keep = [{"time": t["time"], "hash": t.get("hash"), "action": t["action"]} for t in txs
                if t.get("action", {}).get("type") in ("updateIsolatedMargin", "updateLeverage")]
        ap = raw_path(root, "actions", address).with_suffix(".json")
        ap.parent.mkdir(parents=True, exist_ok=True)
        ap.write_text(json.dumps(keep))
    p = raw_path(root, "portfolio", address)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.with_suffix(".json").write_text(json.dumps(light["portfolio"]))
    return {**light, "subaccounts": subs or [], "n_fills": fills.height,
            "history_truncated": fills.height >= FILL_CAP_SUSPECT}
