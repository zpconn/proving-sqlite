#!/bin/bash
# §1.8 native probes, against unmodified upstream/sqlite3.c with its default compile options, ASan and UBSan (clang). Output: *.out
cd "$(dirname "$0")"; UP=../../../upstream
F="-g -O1 -fsanitize=address,undefined -fno-sanitize-recover=undefined -fno-omit-frame-pointer -I$UP"  # SQLite default compile options, as the proofs use
B=$(mktemp -d); trap 'rm -rf $B' EXIT
sha256sum $UP/sqlite3.c
for p in varint_probe unpack_probe; do
  echo "== build $p: clang $F $p.c"; clang $F $p.c -o $B/$p -lm -lpthread -ldl || exit 1
  ASAN_OPTIONS=detect_leaks=0 $B/$p > $p.out 2>&1; echo "exit status $?" >> $p.out
  echo "== $p: exit $(tail -1 $p.out)"
done
