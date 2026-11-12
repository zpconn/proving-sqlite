# LEDGER

What milestone 1 *assumes*: each entry is a clause CBMC takes as given, with who must make it true. Format: GOAL.md Appendix C. Every entry here is a **draft** (checkpoint 1). The boundary contract headers (A-002 to A-004) are their entries' clauses word for word, with a `Ledger: A-NNN` line. They were written at checkpoint 1 (decision D2): scan.py, in the gate, checks each header against its clause, and proof.lock freezes them. LEDGER.md and the headers are read-only to builders, so a clause that doesn't work comes back to the orchestrator through the builder's report. The ledger agent (GOAL.md §3, agents/ledger/GOAL.md) tests the entries once they settle.

Lines are upstream/sqlite3.c's.

## A-001 Readable slack after a record
- Function(s): sqlite3VdbeRecordUnpack (C-15). Also, where their proofs show they need it, vdbeRecordCompareInt (C-20), sqlite3VdbeRecordCompareWithSkip (C-17) and vdbeRecordCompareString (C-19). Each comparator card states its own slack.
- Clause, as CBMC states it, on sqlite3VdbeRecordUnpack:
  ~~~
  __CPROVER_requires(nKey >= 0 && __CPROVER_r_ok(pKey, (size_t)(nKey > 0 ? nKey : 1) + 8))
  ~~~
  - That is, sqlite3VdbeRecordUnpack reads at most E(nKey) = max(nKey, 1) + 8 bytes from pKey, whatever p->nField is: 8 bytes of slack after a non-empty record, 9 bytes after an empty one. The derivation is below.
  - C-15 proves the function under this requires, and shows one byte less, max(nKey, 1) + 7, fails (builder §2.4).
  - For the comparators, S is not yet fixed. Each card determines the smallest that works: its proof passes at S and fails at S − 1 (for C-20: `__CPROVER_r_ok(pKey1, (size_t)nKey1 + S)`). Each S is written here before the entry leaves draft.
- Plain English: whoever passes an nKey-byte record to sqlite3VdbeRecordUnpack also makes 8 more bytes after it readable, or 9 bytes in all when nKey is 0. Their contents are unconstrained.
- Why the proof needs it:
  - sqlite3VdbeRecordUnpack's loop (92134) checks `idx<szHdr` and `d<=nKey` before each field. Nothing bounds how far the varint at aKey[idx] or the value at aKey[d] extends past nKey. A corrupt record therefore makes getVarint32 and sqlite3VdbeSerialGet read past pKey+nKey. The comment at 92150–92153 notes the last Mem may then hold uninitialized memory.
  - **Derivation of E(nKey)**, from the source lines that bound each read. N is (u32)nKey, and nKey ≥ 0, since a negative nKey wraps to a huge N:
    1. The header varint at aKey[0] (92131, getVarint32): one byte if aKey[0] < 0x80, otherwise sqlite3GetVarint32, which reads at most 9 bytes. Reads end at or before aKey[8].
    2. d starts at szHdr (92132) and only grows: `d += sqlite3VdbeSerialTypeLen(serial_type)` (92144).
       - The loop body runs only when `d<=(u32)nKey` (92134), so d ≤ N ≤ 2^31−1 there.
       - sqlite3VdbeSerialTypeLen returns at most (2^32−1−12)/2 = 2^31−7, so the sum is below 2^32 and cannot wrap.
       - In the body, therefore, szHdr ≤ d ≤ N, and with `idx<szHdr`, idx ≤ N − 1.
    3. The varint at aKey[idx] (92137) reads at most 9 bytes, ending at or before aKey[N+7].
    4. sqlite3VdbeSerialGet at aKey[d] (92143) reads at most 8 bytes, for types 6 and 7; types 8–11 and t ≥ 12 read none (PROPERTIES.md P3, D2–D3). Its reads end at or before aKey[N+7].
    5. Nothing else reads pKey: sqlite3VdbeSerialTypeLen and sqlite3VdbeMemSetNull (92153) don't.
    6. So every read is below max(9, N+8) = max(nKey, 1) + 8. p->nField only limits how many fields are read, not where.
  - **The bound is tight.**
    - For N ≥ 2: the header {N, 6} (szHdr = N, encoded as a varint shorter than N, and serial type 6) reads an 8-byte integer at aKey[N], whose last byte is aKey[N+7].
    - For N = 1: a header varint of 9 bytes reads aKey[8] = aKey[N+7].
    - For N = 0: a header varint of 9 bytes reads aKey[8] = aKey[N+8]; the loop can't run, since szHdr ≤ 0 < idx.
  - This corrects the checkpoint 1 draft, which said idx is bounded only by szHdr and the field count. Inside the loop, idx < szHdr ≤ d ≤ nKey.
  - vdbeRecordCompareInt reads up to 8 bytes at offset `pKey1[0] & 0x3F` (92849) without comparing it to nKey1.
- Who must make it true: callers in milestone 2: the b-tree layer, for cell payloads and overflow pages, and the sorter. sqlite3VdbeFindCompare's comment (93011–93023) states that callers guarantee "at least 74 (but not 136) bytes of padding following each buffer" passed to vdbeRecordCompareInt. That is SQLite's own statement of this obligation for the comparators, not evidence that it holds.
  - **Callers that don't make it true** (ledger run 2026-11-10, by backtrace, reports/ledger-2026-11-10.md §3). For each, whether its record can come from the database file, and so be corrupt, or is always built by SQLite. "Source reading" means the orchestrator read the code and nothing has tested it yet.
    1. **sqlite3_preupdate_old → vdbeUnpackRecord** (95938–95944): `aRec = sqlite3DbMallocRaw(db, nRec)` with `nRec = sqlite3BtreePayloadSize(...)`, exactly the payload's size, filled by sqlite3BtreePayload. **From the file; can be corrupt.** F-002.
    2. **sqlite3_preupdate_new → vdbeUnpackRecord** (96086–96094). Only an INSERT unpacks; an UPDATE copies registers (96108). The ledger report calls this the UPDATE path, but the source has it on INSERT. An ordinary INSERT's record is built by OP_MakeRecord. With SQLITE_ENABLE_PREUPDATE_HOOK, though, xferOptimization (142204–142207) copies the source table's stored record with OP_RowData into the register it inserts from. So `INSERT INTO t2 SELECT * FROM t1` hands preupdate_new t1's record as stored (source reading). **From the file; can be corrupt.** F-002. The ledger agent's second run tries this route as a possible second repro (Zach, 2026-11-11; evidence/orchestrator/ledger-run-2.md).
    3. **sqlite3BtreeInsert with BTREE_SAVEPOSITION** (82916–82924): after a rebalance on an index or WITHOUT ROWID cursor, `pCur->pKey = sqlite3Malloc(pX->nKey)`, exact size. Source reading: the inserts that set SAVEPOSITION all insert a record from OP_MakeRecord: ALTER TABLE DROP COLUMN (122937–122940), and sqlite3CompleteInsertion for a one-pass multi-row UPDATE (141703–141722, from 160859). xferOptimization's inserts don't set it (142200–142207, 142260–142268). So the reading is **always built by SQLite**. **Zach's hypothesis (2026-11-11), to test, not a claim:** xferOptimization (`INSERT INTO t2 SELECT * FROM t1`, matching schemas, t1 from a corrupt file) may carry file records into this path too, and so overread like F-002. The ledger agent's second run tries a repro.
    4. **The sorter** (vdbeSorterCompare 107326, vdbeSorterCompareTail 107299, sqlite3VdbeSorterCompare 109314). Its records come from OP_SorterInsert of OP_MakeRecord results: CREATE INDEX (130362), ORDER BY (149863) and GROUP BY (157597). They are kept in SQLite's memory or its own temporary files (source reading). **Always built by SQLite.**
    5. **btreeMoveto ← btreeRestoreCursorPosition ← btreeNext** (74100) restores a cursor from `pCur->pKey`. That key comes from path 3, with no padding, or from saveCursorKey (73950–73957), which pads 9 + 8 bytes and zeroes them against exactly this overread. **The same source as path 3.**
    - A record SQLite builds is well formed, so a missing slack matters only if the record is corrupt. That makes paths 1 and 2 the reachable overreads (F-002). In the suites no overread actually fired on any path.
- Evidence: tested (ledger agent run 2026-11-10, J0079): the site was reached about 14.4M times and ASan-checked 6.85M times in sdevtest. The slack after the record was below 8 bytes in 151,429 sdevtest calls (665 in test's ASan build, 124 in fuzztest-asan, 665 in fuzzcheck-native), and 0 bytes in 4,136 of them. The nKey = 0 case was not reached. Earlier, the premise was *tested*: without slack, sqlite3VdbeRecordUnpack(2, {0x02, 0x81}) on an exact-size allocation is an ASan heap-buffer-overflow read at 38190, called from 92137 (evidence/bringup/08-probes.md, §1.8.2).
- Status: violated at callers (Zach, 2026-11-11). The clause stays as the proof's assumption; the callers above don't make it true.

## A-002 sqlite3DbMallocRaw returns NULL or a fresh block of at least n bytes
- Function(s): sqlite3DbMallocRaw (32113), a boundary callee of sqlite3VdbeAllocUnpackedRecord (C-14, call at 92103).
- Clause, as CBMC states it (proofs/contracts/sqlite3DbMallocRaw.h is this clause word for word, written at checkpoint 1 and frozen; C-14 replaces the call with it):
  ~~~
  void *contract_sqlite3DbMallocRaw(sqlite3 *db, u64 n)
    __CPROVER_assigns()
    __CPROVER_ensures(__CPROVER_return_value == NULL || __CPROVER_is_fresh(__CPROVER_return_value, n));
  ~~~
- Plain English:
  - It returns either NULL or a new block of at least n bytes. The block is uninitialized, belongs to no other object and is aligned to 8 bytes.
  - CBMC does not model alignment, so the 8-byte alignment is argued, not checked (UB-CLASSES.md, the `(Mem*)` conversion at 92105).
  - The real function also updates the connection's allocator state: lookaside, `db->mallocFailed` on failure, and statistics. The clause leaves those writes out because no milestone-1 caller reads them: sqlite3VdbeAllocUnpackedRecord reads only pKeyInfo->nKeyField after the call.
- Why the proof needs it: the allocator and lookaside (sqlite3DbMallocRawNN, 32120; sqlite3Malloc) belong to a later milestone (GOAL.md Appendix A), so their bodies are not proved here.
- Who must make it true: the allocator: SQLite's memory subsystem and the configured sqlite3_mem_methods, whose xMalloc must return 8-byte-aligned memory (SQLite asserts EIGHT_BYTE_ALIGNMENT on its allocations).
- Evidence: tested (ledger agent run 2026-11-10, J0079: 514,651 field and ASan checks, 0 violations; site reached; reports/ledger-2026-11-10.md)
- Status: tested

## A-003 vdbeCompareMemString compares two strings and writes at most *prcErr
- Function(s): vdbeCompareMemString (92350), a boundary callee of sqlite3VdbeRecordCompareWithSkip (C-17, call at 92734).
- Clause, as CBMC states it (proofs/contracts/vdbeCompareMemString.h is this clause word for word, written at checkpoint 1 and frozen; C-17 replaces the call with it):
  ~~~
  int contract_vdbeCompareMemString(const Mem *pMem1, const Mem *pMem2, const CollSeq *pColl, u8 *prcErr)
    __CPROVER_requires(__CPROVER_r_ok(pMem1, sizeof(Mem)) && __CPROVER_r_ok(pMem2, sizeof(Mem))
                       && __CPROVER_r_ok(pColl, sizeof(CollSeq)))
    __CPROVER_requires(pMem1->n >= 0 && __CPROVER_r_ok(pMem1->z, pMem1->n)
                       && pMem2->n >= 0 && __CPROVER_r_ok(pMem2->z, pMem2->n))
    __CPROVER_requires(prcErr == NULL || __CPROVER_w_ok(prcErr, 1))
    __CPROVER_assigns(prcErr != NULL: *prcErr);
  ~~~
- Plain English:
  - Given two string Mems whose n bytes at z are readable, and a collation, it returns some int.
  - The clause lets it write nothing but *prcErr, which it may set to SQLITE_NOMEM. The real function does more on one path.
  - When pMem1->enc differs from pColl->enc, it calls vdbeCompareMemStringWithEncodingChange (92324). That function copies both strings, converts them with sqlite3ValueText, which allocates through pMem1->db, and frees the copies before returning (sqlite3VdbeMemReleaseMalloc). On OOM, the allocator sets `db->mallocFailed` (sqlite3OomFault), and the function sets *prcErr = SQLITE_NOMEM.
  - The clause leaves out that allocation and `db->mallocFailed` because no milestone-1 caller reads them. After the call, sqlite3VdbeRecordCompareWithSkip reads only the result and pPKey2->errCode. The only reader of `db->mallocFailed` in the record code is vdbeRecordCompareDebug (92277), which is compiled only under SQLITE_DEBUG; the assert at 92523 is compiled out. The allocator's state (lookaside, statistics) is left out for the same reason, as in A-002.
  - The result's sign is the collation's business; the clause says nothing about it.
- Why the proof needs it: vdbeCompareMemString calls the collation's xCmp (92359, 92344), which is application code. When the encodings differ, it converts through vdbemem.c (sqlite3ValueText) and allocates. Neither is in milestone 1.
- Who must make it true:
  - the application: a collation's xCmp reads only the n bytes it is given, and changes nothing the caller can see;
  - callers in a later milestone, for the encoding-conversion path (vdbemem.c).
- Evidence: tested (ledger agent run 2026-11-10, J0079: 3.22M call-site checks and 23.7M entry checks, 0 violations; the assigns clause held; reports/ledger-2026-11-10.md)
- Status: tested

## A-004 sqlite3CorruptError returns SQLITE_CORRUPT and changes nothing the caller sees
- Function(s): sqlite3CorruptError (191373), a boundary callee of sqlite3VdbeRecordCompareWithSkip (C-17: 92646, 92727, 92757, 92808, through SQLITE_CORRUPT_BKPT) and vdbeRecordCompareString (C-19: 92971).
- Clause, as CBMC states it (proofs/contracts/sqlite3CorruptError.h is this clause word for word, written at checkpoint 1 and frozen; C-17 and C-19 replace the calls with it):
  ~~~
  int contract_sqlite3CorruptError(int lineno)
    __CPROVER_assigns()
    __CPROVER_ensures(__CPROVER_return_value == SQLITE_CORRUPT);
  ~~~
- Plain English: it reports the corruption through sqlite3_log and returns SQLITE_CORRUPT (11). Callers store that as `(u8)SQLITE_CORRUPT_BKPT`. It writes nothing their proofs read.
- Why the proof needs it: it calls sqlite3_log (191369), which can call the application's log callback (SQLITE_CONFIG_LOG). That callback is application code.
- Who must make it true: the application: a log callback returns, and changes no state of the comparison in progress.
- Evidence: tested (ledger agent run 2026-11-10, J0079: 945 or more checks, 0 violations; site reached; reports/ledger-2026-11-10.md). Not tested: an application log callback, which no run installed, so a callback that writes where it shouldn't is untested.
- Status: tested

## A-005 Writable bytes at a varint's output, as many as the value needs
- Function(s): sqlite3PutVarint (37991), and putVarint64 (37967) called directly (C-01's contracts, restated in C-01's round 4, merged 2026-11-11).
- Clause, as CBMC states it (proofs/contracts/sqlite3PutVarint.h's requires; putVarint64's is the same):
  ~~~
  __CPROVER_requires(__CPROVER_w_ok(p, (1 + (v >= ((u64)1 << 7)) + (v >= ((u64)1 << 14))
      + (v >= ((u64)1 << 21)) + (v >= ((u64)1 << 28))
      + (v >= ((u64)1 << 35)) + (v >= ((u64)1 << 42))
      + (v >= ((u64)1 << 49)) + (v >= ((u64)1 << 56)))))
  ~~~
- Plain English: a caller writing v provides that many writable bytes at p: one byte below 2^7, k bytes from 2^(7(k−1)) through 2^(7k)−1 for k = 2..8, and nine bytes for every v >= 2^56. That is min(sqlite3VarintLen(v), 9), so sqlite3VarintLen(v) bytes always suffice. The bytes' contents are unrestricted.
- Why the proof needs it: without it, the writers store outside the object. C-01 proves exactly k bytes suffice in each length band, on all three configurations, and that one byte less gives a bounds counterexample in every band (reports/C-01-b4.md).
- Who must make it true: callers in later milestones: the record and b-tree writers and the sorter. OP_MakeRecord budgets sqlite3VarintLen per serial type; vdbePmaWriteVarint supplies `aByte[10]`; C-02's harness supplies `buffer[9]`. Those examples don't establish it for every call.
- Evidence: tested against the old nine-byte clause (ledger agent run 2026-11-10, J0079): no write overflowed in about 125M calls, while 6,518 + 363 calls had fewer than nine addressable bytes, which this restatement allows. The second ledger run retests it as restated (evidence/orchestrator/ledger-run-2.md).
- Status: draft. Restated (Zach, 2026-11-11: C-01 reopened for a footprint that depends on the value written); the old nine-byte clause was not met at real calls.

## A-006 memcmp reads n bytes of each argument, writes nothing, and returns a value in [-255, 255]
- Function(s): memcmp, the C library's, a boundary callee of sqlite3VdbeRecordCompareWithSkip (C-17: 92739, 92767) and vdbeRecordCompareString (C-19: 92975).
- Clause, as CBMC states it (proofs/contracts/memcmp.h is this clause word for word, frozen in proof.lock; C-17 and C-19 replace the calls with it):
  ~~~
  int contract_memcmp(const void *s1, const void *s2, size_t n)
    __CPROVER_requires(__CPROVER_r_ok(s1, n) && __CPROVER_r_ok(s2, n))
    __CPROVER_assigns()
    __CPROVER_ensures(-255 <= __CPROVER_return_value && __CPROVER_return_value <= 255);
  ~~~
- Plain English: memcmp reads exactly n bytes from each of its two arguments and writes nothing. Its result has the sign C11 7.24.4.1 gives it, and its magnitude is at most 255: the difference of the first differing bytes, read as unsigned char, or 0.
- Why the proof needs it: CBMC's memcmp model loops once per byte, so under `--unwinding-assertions` it can't be unwound for unbounded lengths (C-17 round 3, B2; evidence/orchestrator/tool-issues/T-010/). The result's range matters because 92739–92740 and 92767–92768 pass memcmp's result to the DESC negation at 92793, which overflows for INT_MIN (F-001). C11 fixes only the sign, so the bound is an assumption about the C library, not the standard. The proofs need less than the whole range: C-17 needs only a result other than INT_MIN (the negation at 92793), and C-19 uses only the sign. [−255, 255] is what glibc and CBMC's model give, and stating it is simpler than a weaker clause.
- Who must make it true: the C library SQLite is linked with. glibc returns the byte difference (C-17 round 3, *tested* on 65-byte buffers differing by 0x00/0xff at byte 40: −255 and 255), and so does CBMC's own model. A C library returning other magnitudes would bring the memcmp paths to F-001's overflow too.
- Evidence: none yet (the ledger agent's second run tests it).
- Status: draft (approved by Zach, 2026-11-10, as C-17's B2)
