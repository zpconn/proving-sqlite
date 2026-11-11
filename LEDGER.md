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
- Evidence: none. The premise is *tested*: without slack, sqlite3VdbeRecordUnpack(2, {0x02, 0x81}) on an exact-size allocation is an ASan heap-buffer-overflow read at 38190, called from 92137 (evidence/bringup/08-probes.md, §1.8.2).
- Status: draft

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
- Evidence: none
- Status: draft

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
- Evidence: none
- Status: draft

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
- Evidence: none
- Status: draft

## A-005 Nine writable bytes at a varint's output
- Function(s): sqlite3PutVarint (37991), and putVarint64 (37967) called directly (C-01's contracts).
- Clause, as CBMC states it: `__CPROVER_requires(__CPROVER_w_ok(p, 9))`. This is proofs/contracts/sqlite3PutVarint.h's requires, as merged in C-01; putVarint64's contract has the same.
- Plain English: callers provide nine writable bytes starting at the output pointer. The bytes' contents and the u64 value are unrestricted.
- Why the proof needs it:
  - Without it, putVarint64 stores p[8] outside the object (extent 3, offset 3, v = 9223372037123211264; 37971).
  - Without it, sqlite3PutVarint stores p[0] outside an empty one (extent 8, offset 8; 37993).
  - Eight bytes are not enough, because the ninth-byte store exceeds the object. (reports/C-01-b2.md; C-01's builder proposed this entry.)
- Who must make it true: callers in later milestones: the record and b-tree writers, and the sorter (balance_nonroot, fillInCell, sqlite3BtreeTransferRow, sqlite3VdbeExec, vdbePmaWriteVarint). One example is vdbePmaWriteVarint's `aByte[10]` (108087–108088); that one example does not establish the obligation for the others. In milestone 1, C-02's harness supplies `buffer[9]`.
- Evidence: none
- Status: draft

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
- Why the proof needs it: CBMC's memcmp model loops once per byte, so under `--unwinding-assertions` it can't be unwound for unbounded lengths (C-17 round 3, B2; evidence/orchestrator/tool-issues/T-010/). The result's range matters because 92739–92740 and 92767–92768 pass memcmp's result to the DESC negation at 92793, which overflows for INT_MIN (F-001). C11 fixes only the sign, so the bound is an assumption about the C library, not the standard.
- Who must make it true: the C library SQLite is linked with. glibc returns the byte difference (C-17 round 3, *tested* on 65-byte buffers differing by 0x00/0xff at byte 40: −255 and 255), and so does CBMC's own model. A C library returning other magnitudes would bring the memcmp paths to F-001's overflow too.
- Evidence: none yet (the ledger agent's second run tests it).
- Status: draft (approved by Zach, 2026-11-10, as C-17's B2)
