"""Per-coin position timeline: (time, signed size, average entry) after every fill."""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field

import polars as pl

from hlscout.recon.roundtrips import EPS, _ordered_rows


@dataclass
class Timeline:
    times: dict[str, list[int]] = field(default_factory=dict)
    state: dict[str, list[tuple[float, float]]] = field(default_factory=dict)  # (pos, entry)
    last_px: dict[str, list[float]] = field(default_factory=dict)
    flat_since: dict[str, list[int]] = field(default_factory=dict)  # time position last became flat

    def at(self, coin: str, t: int) -> tuple[float, float, float | None, int]:
        """(pos, entry, last fill px, time the position opened) just after the last fill <= t."""
        ts = self.times.get(coin)
        if not ts:
            return 0.0, 0.0, None, 0
        i = bisect.bisect_right(ts, t) - 1
        if i < 0:
            return 0.0, 0.0, None, 0
        pos, entry = self.state[coin][i]
        return pos, entry, self.last_px[coin][i], self.flat_since[coin][i]

    def open_positions(self, t: int) -> dict[str, tuple[float, float, float | None, int]]:
        out = {}
        for c in self.times:
            pos, entry, px, opened = self.at(c, t)
            if abs(pos) > EPS:
                out[c] = (pos, entry, px, opened)
        return out


def build_timeline(fills: pl.DataFrame) -> Timeline:
    tl = Timeline()
    if fills.is_empty():
        return tl
    for key, g in fills.sort(["coin", "time", "tid"]).group_by("coin", maintain_order=True):
        coin = key[0]
        pos, entry, opened = 0.0, 0.0, 0
        ts, st, lp, op = [], [], [], []
        for r in _ordered_rows(g):
            sp = r["start_position"]
            if sp is not None and abs(sp - pos) > max(1e-6, 1e-6 * abs(sp)):
                pos = sp
                if abs(pos) > EPS and entry == 0.0:
                    entry = r["px"]
            signed = r["sz"] if r["side"] == "B" else -r["sz"]
            if abs(pos) < EPS:
                pos, entry, opened = 0.0, 0.0, r["time"]
            if pos * signed >= 0:
                new = pos + signed
                entry = (abs(pos) * entry + abs(signed) * r["px"]) / abs(new) if abs(new) > EPS else 0.0
                pos = new
            elif abs(signed) > abs(pos) + EPS:  # flip
                pos = pos + signed
                entry, opened = r["px"], r["time"]
            else:
                pos = pos + signed
            if abs(pos) < EPS:
                pos, entry = 0.0, 0.0
            ts.append(r["time"])
            st.append((pos, entry))
            lp.append(r["px"])
            op.append(opened)
        tl.times[coin], tl.state[coin], tl.last_px[coin], tl.flat_since[coin] = ts, st, lp, op
    return tl
