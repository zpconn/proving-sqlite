#!/bin/sh
# Orchestrator's check of C-15 round 2's DFCC toy (T-006). Usage: run.sh <toy.c> <timeout-seconds>
# Builds as tools/prove.py does for a DFCC proof (goto-cc, dfcc with loop contracts and a replaced call,
# slice-global-inits), then runs cbmc with every option line in proofs/CHECKS, under a 24 GB address-space cap.
set -u
src=$1; t=$2; o=${src%.c}
CHECKS=$(grep '^--' /home/zpconn/code/proving-sqlite/proofs/CHECKS | tr '\n' ' ')
goto-cc -m64 --function entry "$src" -o "$o.0.goto" || exit 1
goto-instrument --dfcc entry --replace-call-with-contract reset/reset_spec --apply-loop-contracts "$o.0.goto" "$o.1.goto" > "$o.dfcc.log" 2>&1 || { echo "$src dfcc FAIL"; exit 1; }
goto-instrument --slice-global-inits "$o.1.goto" "$o.goto" > /dev/null 2>&1 || exit 1
start=$(date +%s)
( ulimit -v 25165824; timeout "$t" nice -n 10 cbmc "$o.goto" $CHECKS > "$o.cbmc.log" 2>&1 ); rc=$?
end=$(date +%s)
echo "$src rc=$rc secs=$((end-start)) $(grep -E 'VERIFICATION|\*\* [0-9]+ of [0-9]+ failed' "$o.cbmc.log" | tr '\n' ' ')$(tail -1 "$o.cbmc.log" | grep -i -E 'memory|bad_alloc|out of' )"
