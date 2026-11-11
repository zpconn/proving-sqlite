#!/bin/sh
# usage: run.sh <toy.c> [extra goto-cc flags]: compile with the overlay, then the legacy passes, each capped at 24 GB
P=/home/zpconn/code/proving-sqlite-wt/wip-t006-c15; src=$1; shift; o=${src%.c}
cap() { ( ulimit -v 25165824; timeout 600 nice -n 10 "$@" ) 2>&1; }
cap goto-cc -m64 -include $P/proofs/include/proof.h -I $P/overlay -I $P/proofs/include -I $P/proofs "$@" --function h $src -o $o.0.goto | grep -i error | head -3
cap goto-instrument --remove-function-body ${CALLEE:-sqlite3VdbeSerialGet} $o.0.goto $o.0b.goto > /dev/null
cap goto-instrument --drop-unused-functions $o.0b.goto $o.1.goto > /dev/null
cap goto-instrument --replace-call-with-contract ${CALLEE:-sqlite3VdbeSerialGet} --apply-loop-contracts $o.1.goto $o.2.goto | grep -E 'Reason' | head -1
r=$(cap goto-instrument --enforce-contract walk $o.2.goto $o.3.goto | grep -E 'Reason|Writing' | head -1); echo "$src enforce: $r"
