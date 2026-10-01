from __future__ import annotations

import typer

from hlscout.config import load_config
from hlscout.logging_setup import setup_logging
from hlscout.storage import connect_state

app = typer.Typer(help="HL-Scout: read-only Hyperliquid trader scanner")


@app.callback()
def _main() -> None:
    setup_logging()


@app.command()
def init(config: str = "config/config.yaml") -> None:
    """Create the data dir and SQLite state."""
    cfg = load_config(config)
    connect_state(cfg.data_dir)
    typer.echo(f"initialised {cfg.data_dir}/state.sqlite")


@app.command()
def tape(config: str = "config/config.yaml", duration_s: int = 0) -> None:
    """Record all trades to Parquet (runs until stopped, or duration_s if > 0)."""
    import asyncio
    from pathlib import Path

    import websockets

    from hlscout.clients.info import InfoClient
    from hlscout.clients.ratelimit import RateLimiter
    from hlscout.ingest.tape import TapeRecorder, TradeBuffer, fetch_coins, nightly_maintenance

    cfg = load_config(config)
    root = Path(cfg.data_dir)
    state = connect_state(root)
    limiter = RateLimiter(cfg.api.weight_per_min, cfg.api.headroom, cfg.api.lanes)
    info = InfoClient(limiter, cfg.api.info_url)

    async def main() -> None:
        async def post(p: dict) -> object:
            return await info.post(p, lane="backfill")

        async def gapfill(coin: str) -> list[dict]:
            return await info.post({"type": "recentTrades", "coin": coin}, lane="backfill")

        rec = TapeRecorder(
            TradeBuffer(root / "tape"), state, lambda: fetch_coins(post),
            lambda: websockets.connect(cfg.api.ws_url, ping_interval=None),
            gapfill_fn=gapfill, ping_s=cfg.tape.ping_s,
        )
        rec.heartbeat_path = root / "tape.heartbeat"
        if duration_s:
            asyncio.get_running_loop().call_later(duration_s, rec.stop.set)
        run = asyncio.create_task(rec.run())
        maint = asyncio.create_task(nightly_maintenance(root, cfg.tape.retain_raw_days))
        if duration_s:
            await rec.stop.wait()
            run.cancel()
            maint.cancel()
            rec.buffer.flush()
        else:
            await run

    asyncio.run(main())


@app.command()
def compact(date: str, config: str = "config/config.yaml") -> None:
    """Aggregate one day (YYYY-MM-DD) of tape into addr_day_stats."""
    from pathlib import Path

    from hlscout.ingest.tape import compact_day

    root = Path(load_config(config).data_dir)
    out = compact_day(root / "tape", root / "addr_day_stats", date)
    typer.echo(f"wrote {out}" if out else "no tape for that date")


@app.command()
def vet(address: str) -> None:
    """Full pipeline on one address (implemented in P3+)."""
    raise typer.Exit(code=_not_yet("vet"))


def _not_yet(name: str) -> int:
    typer.echo(f"{name}: not implemented yet")
    return 2
