#!/bin/bash
# measure.sh <build dir> <bits> <proof>...: cbmc on each built goto under a 24 GB cap; prints proof, rc, verdict, wall, peak RSS
cd "$1"; bits=$2; shift 2
CH=$(grep -v '^#' /home/zpconn/code/proving-sqlite-wt/C-17/proofs/CHECKS | grep -v '^%' | tr '\n' ' ')
ulimit -v 25165824
for p in "$@"; do
  n=${p#*n}; extra=${UW_EXTRA:-}
  /usr/bin/time -v timeout ${TO:-1800} nice -n 10 cbmc $p.goto $CH --unwindset sqlite3VdbeRecordCompareWithSkip_wrapped_for_contract_checking.0:$n$extra --object-bits $bits > m-$p-$bits.log 2>&1
  rc=$?
  v=$(grep -E '^\*\* [0-9]+ of|too many addressed|Out of memory' m-$p-$bits.log | tail -1)
  w=$(grep Elapsed m-$p-$bits.log | awk '{print $NF}'); r=$(grep 'Maximum resident' m-$p-$bits.log | awk '{print $NF}')
  echo "$p bits=$bits rc=$rc wall=$w rss_kb=$r | $v"
done
