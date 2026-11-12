#!/bin/bash
# run1.sh <name> <K> <L> [extra makefile suffix, e.g. 'OBJECT_BITS := 10']; env NKEY, SLACK, CFG, TO
cd /home/zpconn/code/proving-sqlite-wt/C-17
n=$1; shift
python3 tmp/gen/gen.py grid "$1" "$2" tmp/grid/$n "$3" || exit 1
CFG=${CFG:-lp64-le}
nice -n 10 python3 tools/prove.py prove --card-dir tmp/grid/$n/C-17 --config $CFG --overlay overlay --timeout ${TO:-600} > tmp/grid/$n.$CFG.log 2>&1
grep RESULT tmp/grid/$n.$CFG.log
