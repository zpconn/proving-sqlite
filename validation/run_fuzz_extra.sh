#!/bin/sh
# validation/run_fuzz_extra.sh: after run_ledger.sh fuzztest-asan, run in that
# ASan build (default compile options):
#   1. fuzzcheck --native-malloc over test/fuzzdata*.db (lookaside and
#      MEMSYS3/5 off, so ASan sees each SQLite allocation's bounds);
#   2. dbfuzz2 (the Makefile's target) over test/dbfuzz2-seed*.db.
# Output: build/run-fuzz-extra/run.log ending in "RESULT fuzz-extra ...".
set -u
V=$(cd "$(dirname "$0")" && pwd)
TREE=$V/build/tree/sqlite-src-3530400
B=$V/build/run-fuzztest-asan
RUN=$V/build/run-fuzz-extra
rm -rf "$RUN" "$V/build/raw/fuzzcheck-native" "$V/build/raw/dbfuzz2"
mkdir -p "$RUN" "$V/build/raw/fuzzcheck-native" "$V/build/raw/dbfuzz2"
{
  echo "START fuzz-extra $(date -Is)"
  cd "$B"
  LEDGER_DIR=$V/build/raw/fuzzcheck-native nice -n 10 ./fuzzcheck --native-malloc $TREE/test/fuzzdata*.db
  rc1=$?
  nice -n 10 make dbfuzz2 > "$RUN/dbfuzz2-build.log" 2>&1
  LEDGER_DIR=$V/build/raw/dbfuzz2 nice -n 10 ./dbfuzz2 dbfuzz2-dir/*
  rc2=$?
  echo "END fuzz-extra $(date -Is)"
  echo "RESULT fuzz-extra fuzzcheck-native-malloc=$rc1 dbfuzz2=$rc2"
} > "$RUN/run.log" 2>&1
