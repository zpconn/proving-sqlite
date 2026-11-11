#!/bin/sh
# Zach's C-15 encoding diagnostic (2026-11-11): K=8, N=256, lp64-le, the round-4 harness (card/C-15 0beec51) set by
# the builder's configure.py. Measurement only: the gate's 600 s limit is unchanged.
#   1. default solver through tools/prove.py --timeout 3600 (prove.py caps each tool process at 12 GB)
#   2-4. the same goto program, prove.py's own CBMC command plus one option, under ulimit -v 12 GB, timeout 1200 s
set -u
cd "$(dirname "$0")/.."
T='elapsed_s=%e peak_rss_kib=%M exit=%x'
/usr/bin/time -f "$T" -o diag/default.time nice -n 10 python3 tools/prove.py prove --card-dir proofs/C-15 --config lp64-le \
  --build-dir diag/default --timeout 3600 > diag/default.log 2>&1
echo "default: $(cat diag/default.time | tail -1) | $(grep '^RESULT' diag/default.log | tail -1)"
G=diag/default/lp64-le/unpack.goto
BASE=$(head -1 diag/default/lp64-le/unpack.cbmc | sed 's/^\$ //')
echo "base command: $BASE" > diag/base-command.txt
for opt in "--sat-solver cadical" "--arrays-uf-always" "--refine-arrays"; do
  name=$(echo "$opt" | sed 's/^--//; s/ /-/g')
  ( ulimit -v 12582912; /usr/bin/time -f "$T" -o diag/$name.time nice -n 10 timeout 1200 $BASE $opt > diag/$name.cbmc 2>&1 )
  v=$(grep -E 'VERIFICATION (SUCCESSFUL|FAILED|ERROR)' diag/$name.cbmc | tail -1)
  echo "$name: $(tail -1 diag/$name.time) | ${v:-no verdict} | $(grep -c ': FAILURE$' diag/$name.cbmc) FAILURE, $(grep -c ': ERROR$' diag/$name.cbmc) ERROR, $(grep -c ': SUCCESS$' diag/$name.cbmc) SUCCESS | $(grep -m1 -i 'out of memory\|bad_alloc' diag/$name.cbmc)"
done
