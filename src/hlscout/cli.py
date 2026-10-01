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
def vet(address: str) -> None:
    """Full pipeline on one address (implemented in P3+)."""
    raise typer.Exit(code=_not_yet("vet"))


def _not_yet(name: str) -> int:
    typer.echo(f"{name}: not implemented yet")
    return 2
