"""Seed importer: pull 0x addresses out of any pasted text/CSV (X desks, Perpy, Proliquid)."""

from __future__ import annotations

import re
from pathlib import Path

ADDR = re.compile(r"0x[0-9a-fA-F]{40}\b")


def extract_addresses(text: str) -> list[str]:
    seen: dict[str, None] = {}
    for m in ADDR.findall(text):
        seen[m.lower()] = None
    return list(seen)


def load_seed_file(path: Path) -> list[str]:
    return extract_addresses(Path(path).read_text())
