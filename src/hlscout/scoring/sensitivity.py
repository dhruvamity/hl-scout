"""Threshold sensitivity (plan §14.3): how many wallets does each gate remove, and which verdicts flip under a
±10% threshold move? Works purely from the stored metrics + detector verdicts, so it never touches the network
and uses the SAME gate and stage code as the live decision (`evaluate_gates`, `decide_stage`)."""

from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace
from typing import Any

from hlscout.config import Config
from hlscout.scoring.engine import decide_stage, evaluate_gates

# parameter -> True if it is a ceiling ("_max": looser = higher), False if a floor ("_min": looser = lower)
PARAMS = {
    "gates.min_track_days": False, "gates.weekly_coverage_min": False, "gates.max_gap_days": True,
    "gates.hold_median_max_s": True, "gates.intraday_close_share_min": False, "gates.best_month_share_max": True,
    "gates.top5_trades_share_max": True, "gates.max_dd_twr": True, "gates.eff_leverage_tw_max": True,
    "gates.tstat_min": False, "gates.dsr_prob_min": False, "gates.median_equity_min_usd": False,
    "history.genuine_coverage_min": False, "history.rolling90_positive_min": False,
}


def load(con: sqlite3.Connection) -> list[dict[str, Any]]:
    vet = {}
    for ent, code, sev, ev in con.execute("SELECT entity, code, severity, evidence_json FROM detector_results "
                                          "WHERE run_id='latest'"):
        vet.setdefault(ent, []).append(SimpleNamespace(code=code, severity=sev,
                                                       metrics=json.loads(ev).get("metrics", {})))
    out = []
    for ent, st, mj, gj, cat in con.execute("SELECT entity, stage, metrics_json, gates_json, category FROM scores "
                                            "WHERE run_id='latest'"):
        if gj in (None, "[]"):
            continue
        out.append({"address": ent, "stage": st, "m": json.loads(mj or "{}"), "findings": vet.get(ent, []),
                    "cat": {"category": cat}})
    return out


def _stage(cfg: Config, w: dict, ignore: str | None = None) -> str:
    ctx = SimpleNamespace(cfg=cfg)
    gates = evaluate_gates(ctx, w["m"], w["findings"], w["cat"])
    failed = [g["gate"].split()[0] for g in gates if g["pass"] is False]
    if ignore:
        failed = [g for g in failed if g != ignore]
    vetoes = [f.code for f in w["findings"] if f.severity == "VETO"]
    if ignore == "G10":
        vetoes = []
    return decide_stage(cfg, w["m"], failed, vetoes, False)


def _cfg_with(base: Config, path: str, value: float) -> Config:
    c = base.model_copy(deep=True)
    sec, name = path.split(".")
    setattr(getattr(c, sec), name, type(getattr(getattr(base, sec), name))(value))
    return c


def counts(cfg: Config, ws: list[dict], ignore: str | None = None) -> dict[str, int]:
    out: dict[str, int] = {}
    for w in ws:
        s = _stage(cfg, w, ignore)
        out[s] = out.get(s, 0) + 1
    return out


def report(con: sqlite3.Connection, cfg: Config) -> str:
    ws = load(con)
    base = counts(cfg, ws)
    sel = lambda c: c.get("qualified", 0) + c.get("provisional", 0)  # noqa: E731
    lines = ["# Threshold sensitivity", "",
             f"Wallets with full gate evaluation: {len(ws)}. Baseline stages: "
             + ", ".join(f"{k}={v}" for k, v in sorted(base.items())), "",
             "## What each gate removes (counterfactual: wallets that would be Qualified+Provisional if that gate were ignored)",
             "", "| Gate ignored | Qualified | Provisional | Gain vs baseline |", "|---|---|---|---|"]
    gates = ["G1", "G1b", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10", "G11", "G12"]
    for g in gates:
        c = counts(cfg, ws, g)
        lines.append(f"| {g} | {c.get('qualified', 0)} | {c.get('provisional', 0)} | +{sel(c) - sel(base)} |")
    lines += ["", "## ±10% threshold moves (Qualified+Provisional count; flips = wallets whose stage changes)", "",
              "| Parameter | Baseline value | 10% stricter | 10% looser | Flips (stricter / looser) |",
              "|---|---|---|---|---|"]
    for path, ceiling in PARAMS.items():
        sec, name = path.split(".")
        v0 = getattr(getattr(cfg, sec), name)
        cells, flips = [], []
        for factor in ((0.9, 1.1) if ceiling else (1.1, 0.9)):  # stricter first
            c2 = _cfg_with(cfg, path, v0 * factor)
            cells.append(str(sel(counts(c2, ws))))
            flips.append(sum(1 for w in ws if _stage(c2, w) != _stage(cfg, w)))
        lines.append(f"| {path} | {v0} | {cells[0]} | {cells[1]} | {flips[0]} / {flips[1]} |")
    mr: dict[str, int] = {}
    walls: dict[str, int] = {}
    for w in ws:
        for k, v in (w["m"].get("month_reasons") or {}).items():
            mr[k] = mr.get(k, 0) + v
            walls[k] = walls.get(k, 0) + 1
    if mr:
        lines += ["", "## Why months were not 'genuine' (drives G1b)", "", "| Reason | Month-instances | Wallets affected |",
                  "|---|---|---|"] + [f"| {k} | {v} | {walls[k]} |" for k, v in sorted(mr.items(), key=lambda x: -x[1])]
    return "\n".join(lines) + "\n"
