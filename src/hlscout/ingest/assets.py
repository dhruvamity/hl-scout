"""Perp asset index -> coin name (main dex), needed to decode explorer actions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


async def ensure_asset_names(info: Any, root: Path) -> list[str]:
    p = Path(root) / "asset_names.json"
    meta = await info.post({"type": "meta"}, lane="backfill")
    names = [u["name"] for u in meta["universe"]]
    p.write_text(json.dumps(names))
    return names


def load_asset_names(root: Path) -> list[str] | None:
    p = Path(root) / "asset_names.json"
    return json.loads(p.read_text()) if p.exists() else None
