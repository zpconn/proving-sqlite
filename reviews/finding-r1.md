APPROVE

Both finding claims hold. Severities below describe the SQLite defects, not blockers to accepting the findings.
Evidence: **Tested**, native x86-64, GCC 13.3.0; no new **Proved** claim or CBMC run.
All requested builds and executions ran in the foreground and were awaited. `$TMPDIR` was this worktree's `tmp/`.
`sha256sum upstream/sqlite3.c upstream/sqlite3.h` matched `pin.txt`: respectively
`b1dd5d74ec7f29055a6684fa06fb3c2f6821c87dd38f9a458dfd2e8a1db28189` and
`919e7f2e8ed1d8f56ac17b412b8971c76aa5d1a879752cc6058f75e7d5910e1d`.

1. **F-002 — major: public preupdate API reaches a heap-buffer-overflow on a corrupt record. Tested; accepted.**

   Build (exit 0):
   ```sh
   cc -std=gnu11 -g -O1 -fno-omit-frame-pointer -fsanitize=address,undefined -fno-sanitize-recover=undefined -I upstream -o "$TMPDIR/f002" evidence/orchestrator/F-002/repro.c -lm -lpthread -ldl
   ```
   `"$TMPDIR/f002"` exited 1 with `AddressSanitizer: heap-buffer-overflow`, `READ of size 1`.
   Stack: `serialGet:91950` <- `sqlite3VdbeSerialGet:92064` <- `sqlite3VdbeRecordUnpack:92143` <- `vdbeUnpackRecord:95888` <- `sqlite3_preupdate_old:95944` (all upstream/sqlite3.c).
   The initial `"$TMPDIR/f002" clean` exited 1 solely with LeakSanitizer's sandbox/ptrace fatal error, so it was not counted as a clean result.
   Reran both with campaign.py's exact ASan environment (tools/campaign.py:1240):
   ```sh
   ASAN_OPTIONS=detect_leaks=0:abort_on_error=0 "$TMPDIR/f002"
   ASAN_OPTIONS=detect_leaks=0:abort_on_error=0 "$TMPDIR/f002" clean
   ```
   Corrupt case: exit 1, same ASan error; clean case: exit 0, no sanitizer report, and:
   ```text
   record headers found: 1; corrupted: no
   preupdate_old(b): rc=0 type=1
   DELETE rc=0 (not an error); hook calls=1
   ```
   **Tested:** the error, access size, allocation extent and all SQLite stack frames match `evidence/orchestrator/F-002/campaign-run.txt`; clean stdout matches `campaign-control.txt` exactly. Address/undefined-behavior instrumentation remained enabled.
   Local logs: `tmp/f002-run.txt`, `tmp/f002-clean.txt`, `tmp/f002-campaign-env-run.txt`, `tmp/f002-campaign-env-clean.txt`.

   Caller path 1 is confirmed: upstream/sqlite3.c:95938-95944 obtains the stored payload size, allocates exactly `nRec`, copies the payload, and unpacks it without adding slack.
   The changed serial type requests bytes 1999..2006 of a 2000-byte record. ASan stops at the first invalid read; source inspection establishes the seven-byte excess extent.
   ASan's 2008-byte malloc region includes the allocator's eight-byte prefix (28035-28038), not eight bytes after the record.
   The decoder checks `d<=nKey` before the read (92134), then notices the excessive decoded length only afterward (92148-92153).
   Reachability is through public APIs only: deserialize the corrupted database, register a preupdate hook, then `DELETE FROM t WHERE rowid=1`; the callback calls `sqlite3_preupdate_old(db,1,...)` with the correct connection and valid column during DELETE, as required by sqlite3.h:10864-10871. Only `SQLITE_ENABLE_PREUPDATE_HOOK` is enabled by the repro; deserialize is available by default.

   Caller path 2's file provenance is also supported by source inspection: `sqlite3_preupdate_new` unpacks the INSERT register (96086-96094); UPDATE copies individual register values (96108 onward).
   With matching tables, `INSERT INTO t2 SELECT * FROM t1` can use xferOptimization's `OP_RowData` (142204-142207), followed by `OP_Insert` and its INSERT hook (102395-102396).
   `OP_RowData` reads stored bytes through `sqlite3VdbeMemFromBtreeZeroOffset` (102742), allowing a page pointer or a copy with only one explicit trailing byte (87090-87093, 87119-87125); it establishes no general eight-byte slack guarantee.
   This route can therefore carry a corrupt stored record to `_new`; a heap overread through `_new` is not independently **Tested** by the supplied DELETE repro.
   Minor report correction: replace the ledger report's `_new` UPDATE description with INSERT, as LEDGER.md already does, and distinguish that source-inspected route from the **Tested** `_old` failure. This repro reaches `serialGet`, not a varint overread.

   **Assumed:** A-001 requires `max(nKey,1)+8` readable bytes. SQLite's own reachable caller fails to establish this obligation; the application does not directly call the decoder with an invalid footprint. This is a finding, not evidence of a defective conditional proof, and the 2000-byte repro is outside C-15's current bounded proof domain.
   Fix: make both preupdate decoding paths supply the full worst-case readable extent, with checked allocation arithmetic and initialized padding (the `saveCursorKey` precedent at 73950-73961 uses `+9+8` and zeroes it), or validate every read's extent before decoding. Preserve A-001 and record its unmet caller obligation; changing its wording alone does not repair the overread. No SQLite patch was applied.

2. **F-001-b — major: a legal collation produces wrong DESC-index query results and integrity-check failures. Tested; accepted.**

   Built separately, without sanitizers; both builds exited 0:
   ```sh
   cc -std=gnu11 -O2 -I upstream -o "$TMPDIR/misorder-O2" tests/repro/F-001-b.c upstream/sqlite3.c -lm -lpthread -ldl
   cc -std=gnu11 -O0 -I upstream -o "$TMPDIR/misorder-O0" tests/repro/F-001-b.c upstream/sqlite3.c -lm -lpthread -ldl
   ```
   Ran each binary with no arguments, `control`, and `intmin asc`, individually in the foreground; all six executions exited 0. The repro reports discrepancies through stdout rather than its exit status.
   At both optimization levels, INT_MIN/DESC printed `integrity_check: 2000 lines, 2000 errors` and `equality lookups: 2001 rows, 2000 where the index count differs from a table scan`.
   At both levels, both controls printed `integrity_check: 1 lines, 0 errors` and `equality lookups: 2001 rows, 0 where the index count differs from a table scan`.
   **Tested:** all six stdout logs match the corresponding blocks in `evidence/orchestrator/F-001-b/run.txt` exactly. Local logs: `tmp/f001b-O{2,0}-{run,control,asc}.txt`.
   The separate `probe-value` lookup returns 1 in both query forms; the evidence for wrong results is the 2000 discrepancies across the table's rows.

   The collation is legal: tests/repro/F-001-b.c:20-24 implements lexicographic byte order, with length breaking prefix ties; mapping negative results to INT_MIN preserves equality symmetry/transitivity, order reversal and transitivity. It is deterministic, and nonnegative input lengths make `n1-n2` representable.
   sqlite3.h:6678-6691 specifies the sign and ordering laws, not a bound excluding INT_MIN. A-003 likewise excludes no int return value.
   `vdbeCompareMemString` returns the callback result unchanged (92359); the DESC branch negates it at 92793. Negating INT_MIN is undefined, and the reported incorrect results are **Tested** for these two native builds, not asserted for every compiler/platform.
   Fix: reverse the comparison's sign without negating an arbitrary int, e.g. use `rc = rc < 0 ? 1 : -1` inside the existing `rc!=0` reversal branch. Keep the collation API and A-003 unrestricted; retain these cases as regressions. No SQLite patch was applied.
