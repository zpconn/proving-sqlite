#!/bin/sh
# every step capped at 24 GB (ulimit -v), niced; legacy order as prove.py (loops, then enforce; no replace here) and DFCC
set -u
cd "$(dirname "$0")"
ulimit -v 25165824
CHECKS=$(cat checks.txt)
for v in BAD GOOD; do
  D=""; [ $v = GOOD ] && D="-DGOOD"
  nice -n 10 goto-cc -m64 $D toy.c --function entry -o $v.a.goto
  nice -n 10 goto-instrument --apply-loop-contracts $v.a.goto $v.b.goto > $v.legacy-loops.log 2>&1
  nice -n 10 goto-instrument --enforce-contract f $v.b.goto $v.c.goto > $v.legacy-enforce.log 2>&1
  nice -n 10 timeout 600 cbmc $v.c.goto $CHECKS > $v.legacy.cbmc 2>&1; echo "legacy $v: $(grep -E 'VERIFICATION (SUCCESSFUL|FAILED)' $v.legacy.cbmc) $(grep -c 'FAILURE$' $v.legacy.cbmc) failed"
  nice -n 10 goto-instrument --dfcc entry --enforce-contract f --apply-loop-contracts $v.a.goto $v.d.goto > $v.dfcc.log 2>&1
  nice -n 10 timeout 600 cbmc $v.d.goto $CHECKS > $v.dfcc.cbmc 2>&1; echo "dfcc $v: $(grep -E 'VERIFICATION (SUCCESSFUL|FAILED)' $v.dfcc.cbmc) $(grep -c 'FAILURE$' $v.dfcc.cbmc) failed"
done
