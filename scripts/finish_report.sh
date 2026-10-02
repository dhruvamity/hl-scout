#!/bin/sh
# Wait for the vetting queue to drain, then cluster + score + sensitivity + dossiers + backfill plan.
cd "$(dirname "$0")/.." || exit 1
while :; do
  left=$(sqlite3 data/state.sqlite "select count(*) from queue where state in ('pending','running') and attempts < 3")
  [ "$left" -eq 0 ] && break
  sleep 120
done
rm -f data/final.done
uv run hlscout links --no-enqueue-members > data/final_links.log 2>&1
uv run hlscout score --out reports/latest.md > data/final_score.log 2>&1
uv run hlscout sensitivity > data/final_sens.log 2>&1
uv run hlscout dossier --near-misses 25 > data/final_dossier.log 2>&1
uv run hlscout backfill --dry-run > data/final_backfill.log 2>&1
echo finished > data/final.done
