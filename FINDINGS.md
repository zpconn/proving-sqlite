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
  - Its impact was raised from "UB" to wrong query results and integrity_check failures (Zach, 2026-11-11), on the auditor's second repro. C-17's round-4 Codex reviewer reproduces that repro, together with F-002.
- **Related, not a finding:** memcmp's result reaches the same negation at 92739–92740 and 92767–92768. C11 7.24.4.1 fixes only its sign, and both CBMC's model and glibc return a byte difference in [−255, 255], so no overflow arises there today (C-17-b3.md, *tested* with glibc).
