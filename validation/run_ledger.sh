#!/bin/sh
# validation/run_ledger.sh: run one of SQLite's Makefile test targets on the
# tree built from ledger.patch, with the ledger checks logging to a raw dir.
# Usage: run_ledger.sh <name> <make-target> [configure args...]
#   name: build/run-<name> is the build dir, build/raw/<name> the LEDGER_DIR.
# Output: build/run-<name>/run.log, ending with "RESULT <name> exit=<rc>".
set -u
V=$(cd "$(dirname "$0")" && pwd)
NAME=$1; TARGET=$2; shift 2
TREE=$V/build/tree/sqlite-src-3530400
RUN=$V/build/run-$NAME
RAW=$V/build/raw/$NAME
rm -rf "$RUN" "$RAW"; mkdir -p "$RUN" "$RAW"
cd "$RUN"
{
  echo "START $NAME target=$TARGET configure=$* $(date -Is)"
  "$TREE/configure" "$@" > configure.log 2>&1 || { echo "RESULT $NAME exit=configure-failed"; exit 1; }
  LEDGER_DIR=$RAW nice -n 10 make $TARGET ${TSTRNNR_OPTS:+TSTRNNR_OPTS="$TSTRNNR_OPTS"}
  rc=$?
  echo "END $NAME $(date -Is)"
  echo "RESULT $NAME exit=$rc"
} > run.log 2>&1
