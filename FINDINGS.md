# FINDINGS

Counterexamples that reproduce (GOAL.md §3.5, Appendix C). Each `tests/repro/F-NNN.c` builds natively against unmodified upstream/sqlite3.c and fails under ASan or UBSan; a reviewer reproduced each before it went in. Nothing here leaves the machine until Zach decides (GOAL.md §0.7).

## F-001 Negating a collation's INT_MIN result for a DESC key column
- **Function, line, failing check, configuration:** sqlite3VdbeRecordCompareWithSkip, upstream/sqlite3.c:92793 (`rc = -rc;`).
  - The check is signed overflow (C11 6.5p5; CHECKS' `--signed-overflow-check`). UBSan reports "negation of -2147483648 cannot be represented in type 'int'".
  - int is 32 bits on every configuration in proofs/CONFIGS. The finding is *tested* natively on x86-64, the lp64-le platform.
  - It is not shown by CBMC: C-17 has no proof yet (PROGRESS.md, Open questions).
- **Impact:** wrong query results and integrity_check failures on a DESC index with a legal collation. This is *tested* in compiled code with gcc -O2 and -O0, no sanitizers, against unmodified upstream: the auditor's test (2026-11-11), the second repro below.
  - The setup: a collation that returns INT_MIN for "less", `CREATE INDEX i ON t(x COLLATE c DESC)` and 2,001 rows.
  - PRAGMA integrity_check reports 2,000 errors ("row N missing from index i").
  - 2,000 of 2,001 equality lookups through the index disagree with a table scan.
  - Controls are clean: the same collation returning −1, and INT_MIN with an ASC index.
  - The mechanism, as compiled: at 92793, −INT_MIN wraps back to INT_MIN, so under DESC both orders compare "less". The C standard leaves that wrap undefined; it is what these builds do.
- **Counterexample (arguments and bytes):**
  - pPKey2's field i is a MEM_Str Mem.
  - The record pKey1's field i has a text serial type (odd, ≥ 13) whose bytes fit in nKey1.
  - pKeyInfo->aColl[i] is non-NULL.
  - vdbeCompareMemString returns INT_MIN, which is the collation's xCmp result returned unchanged: at 92359 when the encodings match, 92344 otherwise.
  - pKeyInfo->aSortFlags[i] is KEYINFO_ORDER_DESC with BIGNULL clear, so 92787–92793 negate rc.
  - Natively: a collation "intmin" orders by bytes but returns INT_MIN for "less". Then `CREATE TABLE t(x TEXT COLLATE intmin); CREATE INDEX t_x ON t(x DESC);` and two inserts, 'a' then 'b'. The second insert's index seek compares the stored key 'a' (pKey1) with the new key 'b' (pPKey2, bSkip 0), and xCmp('a','b') = INT_MIN.
- **Repro:** tests/repro/F-001.c, built natively against unmodified upstream with ASan/UBSan.
  - Command, campaign.py's fixed one: `cc -std=gnu11 -g -O1 -fno-omit-frame-pointer -fsanitize=address,undefined -fno-sanitize-recover=undefined -I upstream -o repro tests/repro/F-001.c -lm -lpthread -ldl`, then `./repro`.
  - It defines `__ubsan_default_options` ("halt_on_error=1:print_stacktrace=1"), so the first report stops the run with a nonzero exit.
  - campaign.py's run, in its sandbox with no network, no $HOME and an empty environment: build exit 0, run exit 1, with the UBSan report at 92793:14 (evidence/orchestrator/F-001-campaign-run.txt).
  - Stack: sqlite3VdbeRecordCompareWithSkip 92793 ← sqlite3VdbeRecordCompare 92832 ← sqlite3BtreeIndexMoveto 79377 ← sqlite3BtreeInsert 82763 ← sqlite3VdbeExec 103196 ← sqlite3_step ← sqlite3_exec.
- **Second repro, the observable consequence:** tests/repro/F-001-b.c, the auditor's test, unchanged under a provenance header.
  - Built with no sanitizers: `cc -std=gnu11 -O2 -I upstream -o misorder tests/repro/F-001-b.c upstream/sqlite3.c -lm -lpthread -ldl` (or -O0).
  - Run as `./misorder`, then `./misorder control` and `./misorder intmin asc` for the controls.
  - The auditor's results, at -O2 and -O0: evidence/orchestrator/F-001-b/results.txt.
  - The orchestrator's run in campaign.py's repro sandbox (no network, no $HOME, an empty environment; upstream sha256 b1dd5d74…): the same numbers at both levels, with clean controls (evidence/orchestrator/F-001-b/run.txt, run.py).
- **Reachable from SQL or the public API?** Yes, through sqlite3_create_collation with an xCompare that returns INT_MIN for "less", then any SQL that compares keys of a DESC index on a column with that collation; here, an INSERT.
  - The API asks only that the result be "negative, zero, or positive" (upstream/sqlite3.h:6678). The repro's collation keeps the four ordering rules at sqlite3.h:6684–6691; the reviewer checked each.
  - No ledger entry is violated: A-003 bounds nothing about the result.
- **Status:** reproduced.
  - Found by C-17's builder in round 3, on Claude (reports/C-17-b3.md).
  - Approved by C-17's Codex reviewer from campaign.py's run of the repro (reviews/C-17-r3.md). The reviewer also checked upstream's hash against pin.txt.
  - Its impact was raised from "UB" to wrong query results and integrity_check failures (Zach, 2026-11-11), on the auditor's second repro.
  - That repro was judged by a one-off Codex session instead of C-17's reviewer (J0117, reviews/finding-r1.md: APPROVE, 2026-11-11). It ran all six builds and runs, and their output matched evidence/orchestrator/F-001-b/run.txt exactly. Its suggested fix: reverse the comparison's sign without negating an arbitrary int, e.g. `rc = rc < 0 ? 1 : -1` inside the existing `rc != 0` branch.
- **Related, not a finding:** memcmp's result reaches the same negation at 92739–92740 and 92767–92768. C11 7.24.4.1 fixes only its sign, and both CBMC's model and glibc return a byte difference in [−255, 255], so no overflow arises there today (C-17-b3.md, *tested* with glibc).

## F-002 sqlite3_preupdate_old decodes a corrupt stored record from an exact-size buffer
- **Function, line, failing check, configuration:** serialGet, upstream/sqlite3.c:91950, reading past the record. The path is sqlite3VdbeSerialGet 92064 ← sqlite3VdbeRecordUnpack 92143 ← vdbeUnpackRecord 95888 ← sqlite3_preupdate_old 95944.
  - ASan reports a heap-buffer-overflow, READ of size 1, at the first byte past the allocation. The record's last field asks for 8 bytes at offset 1999 of a 2000-byte record, so 7 bytes are past it.
  - It is *tested* natively on x86-64, the lp64-le platform. It is not shown by CBMC: C-15's proof assumes A-001, max(nKey, 1) + 8 readable bytes, and is bounded to records of at most 256 bytes. This caller doesn't provide that slack.
- **Counterexample (arguments and bytes):**
  - A table row's stored record of 2000 bytes, with header {04, 9f 22, 01}: a 1995-byte blob, then a 1-byte integer. Its last serial type is changed from 1 to 6, an 8-byte integer, in the database image.
  - sqlite3_preupdate_old copies the payload into `sqlite3DbMallocRaw(db, nRec)`, exactly nRec = 2000 bytes (95938–95944), and unpacks it with no padding.
  - The decoder checks `d<=nKey` before the read (92134) and notices the excessive length only afterwards (92148–92153).
- **Repro:** tests/repro/F-002.c, the ledger agent's repro, adapted so campaign.py's fixed command builds it: it defines SQLITE_ENABLE_PREUPDATE_HOOK and includes unmodified upstream sqlite3.c first.
  - Command: `cc -std=gnu11 -g -O1 -fno-omit-frame-pointer -fsanitize=address,undefined -fno-sanitize-recover=undefined -I upstream -o f002 tests/repro/F-002.c -lm -lpthread -ldl`. Then `ASAN_OPTIONS=detect_leaks=0 ./f002`, which exits 1 with the ASan report, and `./f002 clean`, the control, which exits 0 with no report.
  - campaign.py's run in its sandbox (no network, no $HOME, an empty environment), and its control: evidence/orchestrator/F-002/.
- **Reachable from SQL or the public API?** Yes, in a build with SQLITE_ENABLE_PREUPDATE_HOOK:
  - deserialize the corrupted database (sqlite3_deserialize is available by default);
  - register a pre-update hook;
  - `DELETE FROM t WHERE rowid=1`, with the hook calling `sqlite3_preupdate_old(db, 1, ...)` as sqlite3.h:10864–10871 allows.

  sqlite3_preupdate_new on an INSERT can carry a corrupt stored record too, by source reading: xferOptimization's OP_RowData (142204–142207) feeds the register it unpacks (96086–96094), with no eight-byte slack guaranteed (87090–87093, 87119–87125). That route is not tested yet; the ledger agent's second run tries it (evidence/orchestrator/ledger-run-2.md).
- **Ledger:** A-001 is violated at callers. Its clause stays as C-15's assumption, and this is its unmet caller obligation (LEDGER.md A-001, caller paths 1 and 2).
- **Status:** reproduced.
  - Found by the ledger agent on Claude (J0079, 2026-11-10; reports/ledger-2026-11-10.md §4). That report calls preupdate_new's route the UPDATE path; the source has it on INSERT, as LEDGER.md says.
  - Reproduced by the auditor natively, and by campaign.py's sandboxed runner with its control clean.
  - Judged by a one-off Codex session (J0117, reviews/finding-r1.md: APPROVE, 2026-11-11). It rebuilt and reran the repro and its control, and they matched campaign.py's runs.
  - Its suggested fix: give both pre-update decoding paths the full worst-case readable extent, padded and zeroed as saveCursorKey does (73950–73961, +9+8), or check each read's extent before decoding.

