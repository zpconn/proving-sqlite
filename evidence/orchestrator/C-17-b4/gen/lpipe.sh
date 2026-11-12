#!/bin/bash
# lpipe.sh <name> <bSkip> <n> [contract variant file]: the legacy pipeline with the loop unwound (goto-instrument
# --unwindset ... --unwinding-assertions) between --replace-call-with-contract and --enforce-contract. prove.py (scratch
# root ${R2:-tmp/root2}) builds through legacy-replace; its legacy-enforce then aborts on the loop (expected), and the rest is
# done here. Every step capped at 24 GB. Prints wall time, peak RSS and the verdict.
set -u
R=/home/zpconn/code/proving-sqlite-wt/C-17; cd $R
name=$1; b=$2; n=$3; CFG=${CFG:-lp64-le}
[ -n "${4:-}" ] && cp "$4" ${R2:-tmp/root2}/proofs/contracts/sqlite3VdbeRecordCompareWithSkip.h
d=tmp/grid3/$name/C-17; mkdir -p $d
python3 - "$d" "$b" "$n" <<'PY'
import sys, os; sys.path.insert(0,'/home/zpconn/code/proving-sqlite-wt/C-17/tmp/gen'); import gen
d, b, n = sys.argv[1] + '/', int(sys.argv[2]), int(sys.argv[3])
open(d+'harness.c','w').write(gen.harness(1,0).split('void harness_b0n1')[0] + gen.entry(b, n, int(os.environ.get('L','0')), int(os.environ.get('SLACK','8')), os.environ.get('NKEY')))
p='b%dn%d' % (b, n)
m=['CARD := C-17','PROOFS := '+p,'%s_ENTRY := harness_%s'%(p,p),
   '%s_ENFORCE := sqlite3VdbeRecordCompareWithSkip/contract_sqlite3VdbeRecordCompareWithSkip'%p,
   '%s_REPLACE := %s sqlite3VdbeSerialGet/contract_sqlite3VdbeSerialGet'%(p,gen.REPL),
   '%s_LOOPS := unwind'%p,'%s_CONTRACTS := legacy'%p,'%s_COVER := sqlite3VdbeRecordCompareWithSkip'%p,'include ../Makefile.common']
open(d+'Makefile','w').write('\n'.join(m)+'\n')
PY
p=b${b}n$n; bd=$d/build/$CFG
rm -rf $d/build
nice -n 10 python3 ${R2:-tmp/root2}/tools/prove.py prove --card-dir $d --config $CFG --overlay ${R2:-tmp/root2}/overlay > $d/../prove.log 2>&1
if ! grep -q 'legacy-enforce failed' $d/../prove.log; then echo "$name: unexpected prove.py result:"; grep -E 'ERROR|RESULT' $d/../prove.log; exit 1; fi
cd $bd; ulimit -v 25165824
goto-instrument --unwindset sqlite3VdbeRecordCompareWithSkip.0:$n --unwinding-assertions $p.2a.goto u.goto > u.log 2>&1 || { echo "$name: unwind failed"; exit 1; }
goto-instrument --enforce-contract sqlite3VdbeRecordCompareWithSkip u.goto e.goto > e.log 2>&1 || { echo "$name: enforce failed"; tail -3 e.log; exit 1; }
goto-instrument --slice-global-inits e.goto f.goto > s.log 2>&1 || { echo "$name: slice failed"; exit 1; }
CH=$(grep -v '^#' $R/proofs/CHECKS | grep -v '^%' | tr '\n' ' ')
/usr/bin/time -v timeout ${TO:-1800} nice -n 10 cbmc f.goto $CH ${OB:+--object-bits $OB} > f.log 2>&1; rc=$?
w=$(grep Elapsed f.log | awk '{print $NF}'); r=$(grep 'Maximum resident' f.log | awk '{print $NF}')
v=$(grep -E '^\*\* [0-9]+ of|too many addressed|Out of memory|VERIFICATION ERROR' f.log | tail -1)
fl=$(grep FAILURE f.log | sed -E 's/^\[([^]]*)\].* line ([0-9]+) .*/\1@\2/' | sed -E 's/\.[0-9]+@/@/' | sort | uniq -c | tr '\n' ';')
echo "$name $CFG b=$b n=$n rc=$rc wall=$w rss_kb=$r | $v | $fl"
