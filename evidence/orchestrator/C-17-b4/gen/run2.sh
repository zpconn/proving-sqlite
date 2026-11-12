#!/bin/bash
# run2.sh <name> <K> <L> [extra]: like run1.sh but against the scratch root tmp/root2 (its own contract header)
cd /home/zpconn/code/proving-sqlite-wt/C-17
n=$1; shift
python3 tmp/gen/gen.py grid "$1" "$2" tmp/grid2/$n "$3" || exit 1
CFG=${CFG:-lp64-le}
nice -n 10 python3 tmp/root2/tools/prove.py prove --card-dir tmp/grid2/$n/C-17 --config $CFG --overlay tmp/root2/overlay --timeout ${TO:-600} > tmp/grid2/$n.$CFG.log 2>&1
grep RESULT tmp/grid2/$n.$CFG.log
grep -h FAILURE tmp/grid2/$n/C-17/build/$CFG/*.cbmc | cut -c1-220 | sort | uniq -c
