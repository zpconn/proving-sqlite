#!/bin/sh
# Measurement only (2026-11-11): C-15's round-4 harness (card/C-15 0beec51) in its start-exact shape, K=4, N=256: both
# offsets 0, the bounds as their own assumes. Through tools/prove.py (12 GB cap, 600 s timeout), one configuration at a time.
set -u
cd "$(dirname "$0")/.."
for c in lp64-le ilp32-le lp64-be; do
  /usr/bin/time -f 'elapsed_s=%e peak_rss_kib=%M exit=%x' -o diag/$c.time nice -n 10 python3 tools/prove.py prove \
    --card-dir proofs/C-15 --config $c --build-dir diag/$c > diag/$c.log 2>&1
  echo "$c: $(tail -1 diag/$c.time) | $(grep '^RESULT' diag/$c.log | tail -1)"
done
