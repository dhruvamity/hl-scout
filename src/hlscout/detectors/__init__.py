"""Run every implemented single-wallet detector against a context (plan §6)."""

from __future__ import annotations

from hlscout.detectors import automation, flows, optics, risk
from hlscout.detectors.base import Ctx, Finding

DETECTORS = [
    flows.d_m1_deposit_inflation, flows.d_m2_rescue_deposit, flows.d_m3_m4_margin_actions, flows.d_m6_borrowed_buying_power,
    flows.d_m8_income_dressing,
    risk.d_r1_martingale, risk.d_r2_bag_holding, risk.d_r3_negative_skew, risk.d_r4_liquidations,
    risk.d_r5_leverage_spikes, risk.d_r6_size_inconsistency, risk.d_r7_window_edge_loss_hiding,
    optics.d_c1_board_vs_account, optics.d_c2_concentration, optics.d_c5_funding_farming,
    optics.d_c7_beta_not_skill, optics.d_c8_event_concentration,
    automation.d_b1_hft_mm, automation.d_b3_vault_protocol, automation.d_b5_blacklist,
    automation.d_b6_twap,
]

# Not yet implemented: D-M5/M6 (needs extra ledger types), D-C3 (needs OI/volume), D-C4, D-B4.
# D-H1..H6 and D-M7 live in multiwallet.py (cluster/tape context).


def run_all(ctx: Ctx) -> list[Finding]:
    out = []
    for d in DETECTORS:
        try:
            f = d(ctx)
        except Exception as e:  # noqa: BLE001 - one broken detector must not drop the wallet; surface it instead
            f = Finding(d.__name__, "INFO", "ERR", 0, [], {"error": f"{type(e).__name__}: {e}"})
        if f is not None:
            out.append(f)
    return out


def verdict(findings: list[Finding]) -> dict:
    vetoes = [f.code for f in findings if f.severity == "VETO"]
    flags = [f for f in findings if f.severity == "FLAG"]
    fams = {f.family for f in flags}
    return {"vetoes": vetoes, "flags": [f.code for f in flags], "flag_families": sorted(fams),
            "needs_qa": len(fams) >= 3, "penalty": sum(f.penalty for f in flags)}
