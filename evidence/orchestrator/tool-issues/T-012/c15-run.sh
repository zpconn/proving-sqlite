#!/bin/sh
# T-006 probe (Zach, 2026-11-10): what CBMC 6.11's legacy contracts do on C-15's real function, sqlite3VdbeRecordUnpack,
# with the builder's round-2 harness, contract and loop annotations (card/C-15 at 98429d8), lp64-le.
# Every tool step runs under a 24 GB address-space cap and a timeout, and GNU time records wall time and peak memory.
# Usage: probe/run.sh separate | combined
set -u
R=$(cd "$(dirname "$0")/.." && pwd)
B=$R/probe/build; mkdir -p "$B"; cd "$B" || exit 1
CAP=25165824          # KiB: 24 GB
REPL="sqlite3GetVarint32 sqlite3VdbeSerialGet sqlite3VdbeSerialTypeLen sqlite3VdbeMemSetNull"
CHECKS=$(grep '^--' "$R/proofs/CHECKS" | tr '\n' ' ')
step() {   # step <name> <timeout s> <command...>
  name=$1; t=$2; shift 2
  ( ulimit -v $CAP; /usr/bin/time -f "$name: exit %x, %e s wall, %M KiB max RSS" -o "$name.time" \
      timeout "$t" nice -n 10 "$@" ) > "$name.log" 2>&1
  rc=$?; cat "$name.time" 2>/dev/null || echo "$name: rc $rc (no time record)"
  return $rc
}
build() {
  python3 "$R/probe/gen.py" "$R" legacy.c || exit 1
  step compile 900 goto-cc -m64 -include "$R/proofs/include/proof.h" -I "$R/overlay" -I "$R/proofs/include" \
      -I "$R/proofs" -c legacy.c -o o.goto || exit 1
  step link 900 goto-cc --function harness_unpack o.goto -o 0.goto || exit 1
  rm_opts=""; for f in $REPL; do rm_opts="$rm_opts --remove-function-body $f"; done
  step remove-bodies 900 goto-instrument $rm_opts 0.goto 0b.goto || exit 1
  step drop-unused 900 goto-instrument --drop-unused-functions 0b.goto 1.goto || exit 1
}
rep_opts=""; for f in $REPL; do rep_opts="$rep_opts --replace-call-with-contract $f"; done
case "${1:-}" in
separate)   # replace, then loops, then enforce: three passes
  build
  step sep-replace 1800 goto-instrument $rep_opts 1.goto s1.goto || exit 1
  step sep-loops 1800 goto-instrument --apply-loop-contracts s1.goto s2.goto || exit 1
  step sep-enforce 1800 goto-instrument --enforce-contract sqlite3VdbeRecordUnpack s2.goto s3.goto
  grep -E 'Invariant check failed|^File:|^Condition:|^Reason:' sep-enforce.log
  ;;
combined)   # replace and loops in one pass, then enforce
  build
  step comb-replace-loops 1800 goto-instrument $rep_opts --apply-loop-contracts 1.goto c1.goto || {
      grep -E 'Reason:|error|Killed|bad_alloc|memory' comb-replace-loops.log | tail -3; exit 1; }
  step comb-enforce 1800 goto-instrument --enforce-contract sqlite3VdbeRecordUnpack c1.goto c2.goto || {
      grep -E 'Invariant check failed|^File:|^Reason:|error|bad_alloc' comb-enforce.log | tail -4; exit 1; }
  step comb-slice 900 goto-instrument --slice-global-inits c2.goto c3.goto || exit 1
  step comb-cbmc 1800 cbmc c3.goto $CHECKS
  grep -E 'VERIFICATION|failed \(|out of memory' comb-cbmc.log | tail -2
  ;;
*) echo "usage: $0 separate | combined"; exit 2 ;;
esac
