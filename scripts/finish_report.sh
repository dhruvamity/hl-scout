#!/bin/sh
# Wait for the capped deep-vet shortlist to finish, then cluster + score + write reports/latest.md.
cd "$(dirname "$0")/.." || exit 1
CAP=${1:-400}
while :; do
  done_n=$(sqlite3 data/state.sqlite "select count(*) from queue where kind='deep' and state='done' and priority<1000000000")
  left=$(sqlite3 data/state.sqlite "select count(*) from queue where kind='deep' and state in ('pending','running') and priority<1000000000")
  [ "$done_n" -ge "$CAP" ] && break
  [ "$left" -eq 0 ] && break
  sleep 60
done
rm -f data/final.done
uv run hlscout links --no-enqueue-members > data/final_links.log 2>&1
uv run hlscout score > data/final_score.log 2>&1
echo finished > data/final.done
