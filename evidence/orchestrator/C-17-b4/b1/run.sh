#!/bin/bash
# B1 rerun: T-010 toys under DFCC (as in round 3) and under legacy contracts. Each step capped at 24 GB.
ulimit -v 25165824
CH="--pointer-check --bounds-check --pointer-primitive-check --unwinding-assertions"
for n in np np2 np3; do
  echo "######## $n DFCC"
  goto-cc --function h $n.c -o $n.0.gb > $n.dfcc.log 2>&1; echo "goto-cc rc=$?" | tee -a $n.dfcc.log
  if [ -f $n.0.gb ]; then
    goto-instrument --dfcc h --enforce-contract f/contract_f $n.0.gb $n.1.gb >> $n.dfcc.log 2>&1; echo "instrument rc=$?" | tee -a $n.dfcc.log
    for s in "" "--z3"; do echo "== cbmc $s" >> $n.dfcc.log; timeout 300 cbmc $n.1.gb $CH $s >> $n.dfcc.log 2>&1; echo "cbmc $s rc=$?" | tee -a $n.dfcc.log; done
  fi
  tail -n 200 $n.dfcc.log | grep -E 'FAILURE|VERIFICATION|error|failed|ERROR' | sort | uniq -c | head -30
  echo "######## $n LEGACY"
  goto-cc --function h ${n}L.c -o ${n}L.0.gb > $n.legacy.log 2>&1; echo "goto-cc rc=$?" | tee -a $n.legacy.log
  if [ -f ${n}L.0.gb ]; then
    goto-instrument --enforce-contract f ${n}L.0.gb ${n}L.1.gb >> $n.legacy.log 2>&1; echo "instrument rc=$?" | tee -a $n.legacy.log
    for s in "" "--z3"; do echo "== cbmc $s" >> $n.legacy.log; timeout 300 cbmc ${n}L.1.gb $CH $s >> $n.legacy.log 2>&1; echo "cbmc $s rc=$?" | tee -a $n.legacy.log; done
  fi
  grep -E 'FAILURE|VERIFICATION|error|failed|ERROR' $n.legacy.log | sort | uniq -c | head -30
done
