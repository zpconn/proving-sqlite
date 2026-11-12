# C-17 sqlite3VdbeRecordCompareWithSkip: round 4 (bounded measurement; NEEDS-DECISION, nothing *proved*)

## B1 under legacy (T-010 toys, evidence/orchestrator/tool-issues/T-010/; commands in reports/C-17-b4.md)
Each toy run with goto-cc --function h, then goto-instrument (DFCC: --dfcc h --enforce-contract f/contract_f;
legacy: --enforce-contract f on the same text with the clauses on f), then cbmc --pointer-check --bounds-check
--pointer-primitive-check --unwinding-assertions, MiniSat and --z3. All under ulimit -v 24 GB. *Tested*:
- np.c (forall q: n>=0 && r_ok(a[q].z, n)): DFCC and legacy alike, MiniSat 11 failed (the r_ok itself, 4
  pointer-primitive checks; the guarded m->z[n-1] read, 6; the reachability marker); Z3 "unknown constant
  ...requires::1::q!0@34#0", VERIFICATION ERROR.
- np2.c (the same for one index j, no quantifier): DFCC 4 of 137 failed, legacy 4 of 118, same four.
- np3.c (is_fresh under forall): goto-cc "quantifier must not contain function calls" on both.
- np4L.c (new; forall over integers only): MiniSat 1 of 101 failed (the quantified assumption has no effect);
  Z3 0 of 101 failed. So with SAT a symbolic-bound forall is not assumed at all.
- np5L.c (new; z == one is_fresh buffer, by equality under forall): MiniSat 7 failed; Z3 aborts
  (smt2_conv.cpp:2978, "unsupported expression", as T-014).
So B1 holds under legacy too: the per-field obligations can't be stated for unbounded nField.

## Bounded contract (proofs/contracts/sqlite3VdbeRecordCompareWithSkip.h; this tree K = 3)
Requires: nKey1 >= 0 and pKey1 readable for max(nKey1, 10+(bSkip!=0)) + 8 bytes; pPKey2 rw for the struct;
1+(bSkip!=0) <= nField <= K; aMem readable for nField Mems; KeyInfo readable for SZ_KEYINFO(0), nAllField >= 1,
and readable for SZ_KEYINFO(min(nField, nAllField)); aSortFlags readable for nField bytes; for each field j < nField
(unrolled to K): a Blob|Zero non-Str non-numeric Mem has u.nZero >= 0, any other Str or Blob non-numeric Mem has
n >= 0 and z readable for n; aColl[j], j < nAllField, is NULL or readable for sizeof(CollSeq).
Assigns pPKey2->errCode, pPKey2->eqSeen. No ensures. Data bytes (record, z contents) are never constrained.

| requires | without it (CBMC, lp64-le) | callers |
|---|---|---|
| record max(nKey1,10+b)+8 | slack 7: GetVarint32/serialGet7/SerialGet/DecodeInt preconditions; floor 9+b: GetVarint32 | A-001 (comparators' S = 8, floor 18/19 bytes); ledger draft |
| nField >= 1+b | nField 0: pRhs->flags out of bounds at 92660, unwinding fails | btreeMoveto 74101 rejects nField==0; C-19/C-20 call with nField>1 (92919, 92984) |
| nField <= K | the bound itself (B1) | Zach's bounded P1 |
| u.nZero >= 0 | 92763 nStr - u.nZero overflows | sqlite3VdbeMemSetZeroBlob clamps n<0 to 0 (86627); ledger draft |
| z readable for n | Str/Blob paths: memcmp and A-003 preconditions (B1) | Mems from RecordUnpack (z into the record) or registers; ledger draft |
| aColl[j] NULL or a CollSeq | A-003 precondition | sqlite3KeyInfoAlloc's users; ledger draft |
| KeyInfo SZ_KEYINFO(min) | one entry less: array bounds at 92729 (aColl[i]) | KeyInfo is allocated whole (sqlite3KeyInfoAlloc) |
| nAllField >= 1 | the harness can't place aColl writes for nA = 0 | nKeyField > 0 asserted at 92655 |

## Footprint minimality (tested in CBMC on lp64-le, K = 2 harness; natively for KeyInfo)
- Slack 8 passes, 7 fails (all four 8-byte/varint reads). Floor 10+b passes, 9+b fails (header varint at idx1).
- KeyInfo allocated at exactly SZ_KEYINFO(min) (T-003): one entry less fails array_bounds at 92729.
  Natively (tmp/native/kinfo.c, quoted in the report): SZ_KEYINFO(1) runs clean, SZ_KEYINFO(1)-1 is an ASan
  heap-buffer-overflow, READ of size 8 at 92729.

## Loop and engine
Unwound, one proof per (bSkip, nField): b0n1..b0nK, b1n2..b1nK, nField and bSkip assigned constants in SETUP (callers
pass 0 or 1), unwinding assertions at n. DFCC, OBJECT_BITS 12, every callee replaced (memcmp by A-006). The bound is
the harness's, not the code's: it needs the PROPERTIES.md change. T-006: the loop contract hit it under DFCC in round 3
(16 object bits, SAT out of memory at 102 s) and under legacy here (K = 2, out of memory; the havocked pRhs is
dereferenced over every object). Legacy with goto-instrument unwinding before enforcement scales to K = 16 (report §4).

## Unreached lines
- sqlite3.c:92626-92636: the bSkip branch; the b0 proofs assign bSkip = 0 (C-18's call, 92832), the b1 proofs cover it
- sqlite3.c:92637-92643: the bSkip == 0 branch; the b1 proofs assign bSkip = 1 (92922, 92985), the b0 proofs cover it
- sqlite3.c:92656: a second iteration's loop head; b0n1 and b1n2 run one iteration, b0n2 and b1n3 cover it
- sqlite3.c:92803-92811: the loop tail after the i==nField break (92802) in the one-iteration proofs b0n1, b1n2; others cover it

## Open questions
- F-001 fails every run (92793 negation of A-003's unbounded result); nothing excludes it. How should a bounded P1 record it?
- The bound, the SETUP rule for aColl[k], and the engine are Zach's decision: reports/C-17-b4.md.
