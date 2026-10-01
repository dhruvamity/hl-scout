"""Stage S1: cheap screen with no per-user IO (plan §3.2). Returns drop reasons per address."""

from __future__ import annotations

import polars as pl

from hlscout.config import ScreenCfg


def screen_s1(df: pl.DataFrame, cfg: ScreenCfg, tape_days: int = 0,
              tape_active_days: pl.DataFrame | None = None) -> pl.DataFrame:
    """Adds `reasons` (list[str]) and `keep` (bool). `tape_active_days` has address, active_days."""
    sys_expr = pl.lit(False)
    for pre in cfg.system_prefixes:
        sys_expr = sys_expr | pl.col("address").str.starts_with(pre)
    checks = {
        "system_address": sys_expr,
        "zero_volume": (pl.col("vlm_month") <= 0) & (pl.col("vlm_allTime") <= 0),
        "low_equity": pl.col("account_value") < cfg.min_account_value,
        "alltime_loss": (pl.col("pnl_allTime") <= cfg.min_alltime_pnl) | (pl.col("roi_allTime") <= 0),
        "low_alltime_vlm": pl.col("vlm_allTime") < cfg.min_alltime_vlm,
        "low_month_vlm": pl.col("vlm_month") < cfg.min_month_vlm,
    }
    out = df
    if tape_active_days is not None and tape_days >= cfg.min_tape_active_days:
        out = out.join(tape_active_days, on="address", how="left").with_columns(
            pl.col("active_days").fill_null(0))
        checks["tape_inactive"] = pl.col("active_days") < cfg.min_tape_active_days
    out = out.with_columns(
        pl.concat_list([pl.when(e).then(pl.lit(k)).otherwise(None) for k, e in checks.items()])
        .list.drop_nulls().alias("reasons"))
    return out.with_columns((pl.col("reasons").list.len() == 0).alias("keep"))


def hint_recent_green(df: pl.DataFrame) -> pl.DataFrame:
    """Minara/LabelYX hint: 30d and all-time both green (ranking hint, not a gate)."""
    return df.with_columns(((pl.col("pnl_month") > 0) & (pl.col("pnl_allTime") > 0)).alias("recent_green"))
