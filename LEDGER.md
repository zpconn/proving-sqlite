# LEDGER

What milestone 1 *assumes*: each entry is a clause CBMC takes as given, with who must make it true. Format: GOAL.md Appendix C. Every entry here is a **draft** (checkpoint 1). Builders write a boundary callee's contract header from its clause, word for word; LEDGER.md is read-only to them, so a clause that doesn't work comes back to the orchestrator through the builder's report. The ledger agent (GOAL.md §3, agents/ledger/GOAL.md) tests the entries once they settle.

Lines are upstream/sqlite3.c's.

## A-001 Readable slack after a record
- Function(s): sqlite3VdbeRecordUnpack (C-15). Also, where their proofs show they need it, vdbeRecordCompareInt (C-20), sqlite3VdbeRecordCompareWithSkip (C-17) and vdbeRecordCompareString (C-19). Each card states its own slack.
- Clause, as CBMC states it: `__CPROVER_requires(__CPROVER_r_ok(pKey, (size_t)nKey + S))` on sqlite3VdbeRecordUnpack, with S a constant (for C-20: `__CPROVER_r_ok(pKey1, (size_t)nKey1 + S)`).
  - S is not yet fixed. Each card determines the smallest S that works: its proof passes at S and fails at S − 1 (builder §2.4).
  - S is then written here before the entry leaves draft.
  - If the slack a card needs grows with the field count, the clause is restated in terms of it, or the card reports a FINDING.
- Plain English: whoever passes an nKey-byte record also makes S more bytes after it readable. Their contents are unconstrained.
- Why the proof needs it:
  - sqlite3VdbeRecordUnpack's loop (92134) checks `idx<szHdr` and `d<=nKey` before each field. Nothing bounds how far the varint at aKey[idx] or the value at aKey[d] extends.
  - A corrupt record therefore makes getVarint32 and sqlite3VdbeSerialGet read past pKey+nKey. The comment at 92150–92153 notes the last Mem may then hold uninitialized memory.
  - idx is bounded only by szHdr and by the field count, not by nKey.
  - vdbeRecordCompareInt reads up to 8 bytes at offset `pKey1[0] & 0x3F` (92849) without comparing it to nKey1.
- Who must make it true: callers in milestone 2: the b-tree layer, for cell payloads and overflow pages, and the sorter. sqlite3VdbeFindCompare's comment (93011–93023) states that callers guarantee "at least 74 (but not 136) bytes of padding following each buffer" passed to vdbeRecordCompareInt. That is SQLite's own statement of this obligation for the comparators, not evidence that it holds.
- Evidence: none. The premise is *tested*: without slack, sqlite3VdbeRecordUnpack(2, {0x02, 0x81}) on an exact-size allocation is an ASan heap-buffer-overflow read at 38190, called from 92137 (evidence/bringup/08-probes.md, §1.8.2).
- Status: draft

## A-002 sqlite3DbMallocRaw returns NULL or a fresh block of at least n bytes
- Function(s): sqlite3DbMallocRaw (32113), a boundary callee of sqlite3VdbeAllocUnpackedRecord (C-14, call at 92103).
- Clause, as CBMC states it (proofs/contracts/sqlite3DbMallocRaw.h, written by C-14's builder):
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
- Clause, as CBMC states it (proofs/contracts/vdbeCompareMemString.h, written by C-17's builder):
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
  - It writes nothing but *prcErr, which it may set to SQLITE_NOMEM.
  - The result's sign is the collation's business; the clause says nothing about it.
- Why the proof needs it: vdbeCompareMemString calls the collation's xCmp (92359, 92344), which is application code. When the encodings differ, it converts through vdbemem.c (sqlite3ValueText) and allocates. Neither is in milestone 1.
- Who must make it true:
  - the application: a collation's xCmp reads only the n bytes it is given, and changes nothing the caller can see;
  - callers in a later milestone, for the encoding-conversion path (vdbemem.c).
- Evidence: none
- Status: draft

## A-004 sqlite3CorruptError returns SQLITE_CORRUPT and changes nothing the caller sees
- Function(s): sqlite3CorruptError (191373), a boundary callee of sqlite3VdbeRecordCompareWithSkip (C-17: 92646, 92727, 92757, 92808, through SQLITE_CORRUPT_BKPT) and vdbeRecordCompareString (C-19: 92971).
- Clause, as CBMC states it (proofs/contracts/sqlite3CorruptError.h, written by C-17's builder, used by C-19):
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
