#!/bin/bash
# §1.5 and §1.6. (1) Preprocess the overlay under each configuration in proofs/CONFIGS and print what the
# preprocessor makes of SQLite's word size and byte order. (2) Show the probe fails on wrong configurations,
# in a scratch copy of the repo. (3) Time goto-cc on the whole overlay per configuration (§1.6).
cd "$(dirname "$0")"; ROOT=$(cd ../../../.. && pwd); T=$(mktemp -d); trap 'rm -rf $T' EXIT
grep -vE '^\s*(#|$)' $ROOT/proofs/CONFIGS | while read name flags; do
  echo "== $name: goto-cc $flags -E overlay/sqlite3.c"
  goto-cc $flags -include $ROOT/proofs/include/proof.h -E $ROOT/overlay/sqlite3.c -o $T/$name.i 2>/dev/null || goto-cc $flags -include $ROOT/proofs/include/proof.h -E $ROOT/overlay/sqlite3.c > $T/$name.i
  printf 'int ptr = __SIZEOF_POINTER__; int lng = __SIZEOF_LONG__;\n#include "sqlite3.c"\nint bo = SQLITE_BYTEORDER; int be = SQLITE_BIGENDIAN; int ps = SQLITE_PTRSIZE;\n' > $T/m.c
  goto-cc $flags -include $ROOT/proofs/include/proof.h -I$ROOT/overlay -E $T/m.c 2>/dev/null | grep -E '^int (ptr|lng|bo|be|ps) =' | tr '\n' ' '; echo
  echo "   sqlite3Get4byte body after preprocessing:"
  awk '/^static u32 sqlite3Get4byte\(const u8 \*p\)\{/{f=1} f{print "     " $0} f&&/^}/{exit}' $T/$name.i | grep -v '^ *$'
done
echo "== probe on wrong configurations (scratch copy of the repo)"
cp -r $ROOT/tools $ROOT/proofs $ROOT/overlay $T/ 2>/dev/null; mkdir -p $T/r; cp -r $T/tools $T/proofs $T/overlay $T/r/
for bad in "lp64-be -m64 --big-endian -DSQLITE_BYTEORDER=4321" "lp64-be --big-endian" "ilp32-le -m64" "lp64-le -m32"; do
  echo "$bad" > $T/r/proofs/CONFIGS
  echo "   CONFIGS line '$bad': $(python3 $T/r/tools/prove.py probe --build-dir $T/pb 2>&1 | grep -E 'FAILURE|^RESULT probe all' | sed 's/^ *probe [^:]*: //' | tr '\n' ';')"
done
echo "== §1.6 goto-cc on the whole overlay, per configuration"
grep -vE '^\s*(#|$)' $ROOT/proofs/CONFIGS | while read name flags; do
  /usr/bin/time -f "   $name: %e s wall, %M KB max RSS" goto-cc $flags --export-file-local-symbols -include $ROOT/proofs/include/proof.h -c $ROOT/overlay/sqlite3.c -o $T/sqlite3.$name.goto 2>&1 | tail -1
  echo "   $name: goto binary $(stat -c %s $T/sqlite3.$name.goto) bytes"
done
