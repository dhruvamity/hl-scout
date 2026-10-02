"""Typed configuration loaded from config/config.yaml (PROJECT_PLAN.md Appendix C)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict


class _Cfg(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HistoryCfg(_Cfg):
    violation_policy: str = "strict"
    forgive_after_months: int = 24
    genuine_coverage_min: float = 0.90
    genuine_start_max_month: int = 3
    rolling90_positive_min: float = 0.70
    terciles_all_positive: bool = True
    coarse_months_count_for_tenure: bool = True


class CategoriesCfg(_Cfg):
    algo_p_threshold: float = 0.70
    manual_p_threshold: float = 0.30
    rank_separately: bool = True


class ApiCfg(_Cfg):
    weight_per_min: int = 1200
    headroom: float = 0.90
    lanes: dict[str, float] = {
        "monitor": 0.25,
        "deep_vet": 0.50,
        "light_hydrate": 0.15,
        "backfill": 0.10,
    }
    worker_concurrency: int = 4
    info_url: str = "https://api.hyperliquid.xyz/info"
    ws_url: str = "wss://api.hyperliquid.xyz/ws"


class TapeCfg(_Cfg):
    retain_raw_days: int = 120
    ping_s: int = 30


class GatesCfg(_Cfg):
    min_track_days: int = 180
    min_active_months_of_last6: int = 6
    weekly_coverage_min: float = 0.60
    max_gap_days: int = 21
    hold_median_min_s: int = 300
    hold_median_max_s: int = 28800
    intraday_close_share_min: float = 0.70
    hft_avg_hold_min_s: int = 180
    maker_share_max: float = 0.80
    trades_per_day_max: int = 300
    positive_months_min_of6: int = 4
    best_month_share_max: float = 0.40
    top5_trades_share_max: float = 0.35
    max_dd_twr: float = 0.30
    eff_leverage_tw_max: float = 10
    margin_usage_p95_max: float = 0.80
    liquidations_window_max: int = 0
    tstat_min: float = 2.0
    dsr_prob_min: float = 0.90
    median_equity_min_usd: float = 5000
    cut_at_breaks: bool = True       # trust fills only after the last material continuity break (audit C2)
    concentration_mode: str = "legacy"  # "legacy" = plan as written; "robust" = ex-top-5 / gross-profit shares (audit C3)
    top1_lottery_share: float = 0.5


class TiersCfg(_Cfg):
    """Provisional tier (audit B): integrity-clean wallets that miss only soft statistical/shape gates."""

    provisional: bool = True
    dd_slack: float = 0.10          # G7 may be up to this much above max_dd_twr
    weekly_coverage_min: float = 0.50
    max_gap_days: int = 30


class ScreenCfg(_Cfg):
    """Stage-1 cheap screen (MinaraCN-style floors, relaxed to the plan's G12)."""

    leaderboard_url: str = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"
    min_account_value: float = 5000
    min_alltime_pnl: float = 0
    min_alltime_vlm: float = 1_000_000
    min_month_vlm: float = 100_000
    deep_cap: int = 400              # full-history vets allowed before raising the cap on purpose
    max_coarse_dd: float = 0.5       # coarse (flow-unadjusted) PnL drawdown vs peak equity
    max_open_leverage: float = 15.0  # current notional / equity
    recent_days: int = 30            # PnL must have moved inside this window
    min_tape_active_days: int = 60  # only enforced once the tape holds >= this many days
    system_prefixes: list[str] = ["0x4000000000000000000000000000000000000", "0x2222222222222222222222222222222222222222"]


class Config(_Cfg):
    window: str = "full_history"
    history: HistoryCfg = HistoryCfg()
    categories: CategoriesCfg = CategoriesCfg()
    api: ApiCfg = ApiCfg()
    tape: TapeCfg = TapeCfg()
    gates: GatesCfg = GatesCfg()
    screen: ScreenCfg = ScreenCfg()
    tiers: TiersCfg = TiersCfg()
    detectors: dict[str, Any] = {}
    scoring: dict[str, Any] = {}
    forward_validation_days: int = 30
    alerts: dict[str, Any] = {}
    data_dir: str = "data"


def load_config(path: str | Path = "config/config.yaml") -> Config:
    p = Path(path)
    raw = yaml.safe_load(p.read_text()) if p.exists() else {}
    return Config(**(raw or {}))
