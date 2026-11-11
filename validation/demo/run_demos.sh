#!/bin/sh
# validation/demo/run_demos.sh: build demo.c against the patched
# amalgamation, with ASan and without, run every case with its own
# LEDGER_DIR, and check the logs (check_demos.py).
# Usage: run_demos.sh <patched-amalgamation-dir> <out-dir>
set -e
AMAL=$1; OUT=$2
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT"
CF="-O1 -g -I$AMAL -DSQLITE_OMIT_LOAD_EXTENSION -DSQLITE_THREADSAFE=0"
gcc $CF -fsanitize=address -fsanitize-recover=address -fno-omit-frame-pointer \
    -o "$OUT/demo-asan" "$HERE/demo.c" -lm
gcc $CF -o "$OUT/demo-plain" "$HERE/demo.c" -lm
for build in asan plain; do
  for c in a001_control a001_slack a001_overread a001_negative \
           a002_control a002_misaligned a002_short \
           a003_control a003_assigns a003_requires \
           a004_control a004_assigns a004_rc \
           a005_control a005_heap1 a005_heap3 a005_stack; do
    d="$OUT/$build/$c"; rm -rf "$d"; mkdir -p "$d"
    LEDGER_DIR="$d" ASAN_OPTIONS=halt_on_error=0:detect_leaks=0 \
      "$OUT/demo-$build" $c > "$d/stdout.txt" 2> "$d/stderr.txt" || echo "exit $?" >> "$d/stdout.txt"
  done
done
python3 -I "$HERE/check_demos.py" "$OUT"
