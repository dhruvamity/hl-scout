"""Run every implemented single-wallet detector against a context (plan §6)."""

from __future__ import annotations

from hlscout.detectors import automation, flows, optics, risk
from hlscout.detectors.base import Ctx, Finding

DETECTORS = [
    flows.d_m1_deposit_inflation, flows.d_m2_rescue_deposit, flows.d_m8_income_dressing,
    risk.d_r1_martingale, risk.d_r2_bag_holding, risk.d_r3_negative_skew, risk.d_r4_liquidations,
    risk.d_r5_leverage_spikes, risk.d_r6_size_inconsistency,
    optics.d_c1_board_vs_account, optics.d_c2_concentration, optics.d_c5_funding_farming,
    automation.d_b1_hft_mm, automation.d_b3_vault_protocol, automation.d_b5_blacklist,
    automation.d_b6_twap,
]

# Not yet implemented (need the link graph / explorer actions / volume data): D-M3..M7,
# D-H1..H6, D-C3, D-C4, D-C7, D-C8, D-R7, D-B4.


def run_all(ctx: Ctx) -> list[Finding]:
    out = []
    for d in DETECTORS:
        f = d(ctx)
        if f is not None:
            out.append(f)
    return out


def verdict(findings: list[Finding]) -> dict:
    vetoes = [f.code for f in findings if f.severity == "VETO"]
    flags = [f for f in findings if f.severity == "FLAG"]
    fams = {f.family for f in flags}
    return {"vetoes": vetoes, "flags": [f.code for f in flags], "flag_families": sorted(fams),
            "needs_qa": len(fams) >= 3, "penalty": sum(f.penalty for f in flags)}
