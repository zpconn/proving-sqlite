#!/bin/sh
# legacy pass orders on the toy, every step capped at 24 GB
set -u
cd "$(dirname "$0")"
ulimit -v 25165824
CHECKS=$(cat checks.txt)
for v in BAD GOOD; do
  # enforce first, then loops
  nice -n 10 goto-instrument --enforce-contract f $v.a.goto $v.e1.goto > $v.ord1-enforce.log 2>&1
  nice -n 10 goto-instrument --apply-loop-contracts $v.e1.goto $v.e2.goto > $v.ord1-loops.log 2>&1; r=$?
  if [ $r -eq 0 ]; then nice -n 10 timeout 600 cbmc $v.e2.goto $CHECKS > $v.ord1.cbmc 2>&1; echo "enforce-then-loops $v: $(grep -E 'VERIFICATION (SUCCESSFUL|FAILED)' $v.ord1.cbmc) $(grep -c 'FAILURE$' $v.ord1.cbmc) failed"; else echo "enforce-then-loops $v: loops step rc=$r: $(tail -1 $v.ord1-loops.log)"; fi
  # both in one goto-instrument run
  nice -n 10 goto-instrument --apply-loop-contracts --enforce-contract f $v.a.goto $v.c1.goto > $v.ord2.log 2>&1; r=$?
  if [ $r -eq 0 ]; then nice -n 10 timeout 600 cbmc $v.c1.goto $CHECKS > $v.ord2.cbmc 2>&1; echo "combined $v: $(grep -E 'VERIFICATION (SUCCESSFUL|FAILED)' $v.ord2.cbmc) $(grep -c 'FAILURE$' $v.ord2.cbmc) failed"; else echo "combined $v: rc=$r: $(tail -1 $v.ord2.log)"; fi
done
