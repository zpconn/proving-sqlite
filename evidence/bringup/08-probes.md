# §1.8 Native probes (2026-11-08)

Against unmodified upstream/sqlite3.c with its default compile options, clang 18 with `-fsanitize=address,undefined`. Rerun: `probes/run.sh`.

1. **Varints** (`probes/varint_probe.out`): 23 boundary values and 1,000,000 random values, with bit length uniform in 0..64, round-trip through sqlite3PutVarint, sqlite3GetVarint and the getVarint32 macro with 0 failures, decoding from exact-size heap buffers with no ASan or UBSan report. No write past n bytes. sqlite3VarintLen(2^63−1) = 9, (2^63) = 10, (2^64−1) = 10. It equals the encoded length for every v < 2^63 tried, and returned 10 for all 7,704 random values ≥ 2^63. **P2's wording stands as GOAL.md states it.**
2. **Over-read** (`probes/unpack_probe.out`): sqlite3VdbeRecordUnpack(2, {0x02, 0x81}) on an exact-size malloc gives "AddressSanitizer: heap-buffer-overflow … READ of size 1 … 0 bytes after 2-byte region", in sqlite3GetVarint32 at sqlite3.c:38190, called from sqlite3VdbeRecordUnpack at 92137. **A-001's premise holds.**
