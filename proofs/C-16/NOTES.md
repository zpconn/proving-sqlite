# C-16: sqlite3VdbeFindCompare (round 2)

Proved: 548 properties, zero failures on each of lp64-le, ilp32-le and lp64-be.
The contract returns one of the three actual RecordCompare functions. Integer
selection implies MEM_Int, nAllField<=13 and the cached integer. String
selection implies MEM_Str without the other five type bits, nAllField<=13,
NULL first collation, and matching cached z/n. Both specialized selections
exclude BIGNULL and establish opposite r1/r2 with the selected sort direction.
Assigns: only p->r1, p->r2, p->u and p->n. No callee replacement or loops.
String n and z remain unrestricted: this function copies them without reading
string bytes. Later comparators must establish their own buffer validity.

| Requires | Counterexample without this clause (round 1, lp64-le) | Justification |
| --- | --- | --- |
| Writable complete UnpackedRecord at p | p_extent=32; r1 write at 93034 outside object (15 FAILURE, 297 UNKNOWN). | Report's A-NNN draft; external BtreeIndexMoveto passes pIdxKey at 79278. |
| KeyInfo header plus one complete aColl entry | extra=0; aColl[0] read at 93045 (3 FAILURE). | Draft; KeyInfoAlloc allocates SZ_KEYINFO(0)+(N+X)*(sizeof(CollSeq*)+1), 150534-150544. |
| Readable complete Mem at aMem | mem_extent=18; flags read at 93026 (11 FAILURE, 414 UNKNOWN). | Draft; input is an unpacked search key with a first field, 19706-19717. |
| One readable sort flag | sort_extent=0; sort[0] read at 93027 (4 FAILURE, 439 UNKNOWN). | Draft; KeyInfoAlloc lays out sort flags at 150540. |
| At least one SQL type bit when the string path can be selected | flags=0, NULL collation, small nAllField; string ensures fails (1 FAILURE). | Draft; Mem type definitions 24540-24587 and assertion 93047. |

The last requires is conditional: nAllField>13, BIGNULL, or a non-NULL first
collation exempts an otherwise typeless Mem. No input data bytes are assumed.
Initial candidate required only allocated objects; it exposed missing flexible
array storage and flags=0. Requires were added only after those failures.

The harness allocates KeyInfo at exactly SZ_KEYINFO(1), 40 bytes on lp64 and
24 on ilp32. SETUP's call allowlist rejects the SZ_KEYINFO macro, so malloc
uses sizeof(KeyInfo)+sizeof(CollSeq*); the post-call OBJECT_SIZE assertion
Proved its equality to SZ_KEYINFO(1) on every configuration. No extra byte.
Other allocations include undersized and exact-size objects, plus one extra
byte (sort: 0..2). p has its two leading pointer fields so SETUP can connect
pKeyInfo/aMem. All remaining fields and heap bytes are nondet. Separate typed
allocations provide the input graph. Complete-struct premises do not claim
minimum accessed byte footprints. nAllField remains unrestricted.

Footprint evidence under approved T-003 (reports/C-16-b2.md reproduces it):
- Proved: one sort byte passes; zero fails (round 1).
- Proved: the whole-entry KeyInfo requires passes with exactly one entry.
- Proved negative check: require/allocate SZ_KEYINFO(0), one entry less;
  CBMC reports 3 FAILURE, 0 UNKNOWN, including aColl[0] at 93045 (lp64-le).
- Proved negative check: with retained requires and exact SZ_KEYINFO(1), add
  a post-call volatile read of key->aColl[1]; CBMC reports 1 bounds FAILURE,
  0 UNKNOWN (lp64-le). It cannot hide an extra entry in allocation slack.
- Tested: malloc(SZ_KEYINFO(1)-1), unmodified upstream, native ASan/UBSan:
  heap-buffer-overflow, READ of size 8 at 93045, 39-byte region (exit 1).
Trusted: T-003 records CBMC's partial flexible-array element check gap.
All retained KeyInfo footprints use SZ_KEYINFO(1), one whole entry, unchanged.
The exact-allocation rule and both negative probes satisfy Zach's addition in
`evidence/approvals/T-003-flexarray-bounds/APPROVED.md`; no blocker remains.

Proved coverage: 21/21 executable lines per configuration; no gaps.
Tested mutation workflow: M-052 and M-053 killed by CBMC bounds/postconditions.
Tested scans: overlay unchanged; scan passes. No invariants are needed.
Assumed: external input obligations are the report's unnumbered ledger draft,
not yet an approved LEDGER.md entry. No boundary callee or padding assumption.
Trusted: CBMC and its semantics/models, and the preprocessor (TRUSTED.md).
Open questions: no proof blocker; orchestrator assigns the ledger draft's ID.

## Unreached lines
- none
