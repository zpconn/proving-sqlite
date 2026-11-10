# C-16: sqlite3VdbeFindCompare (round 1)

Proved: 543 properties, zero failures on each of lp64-le, ilp32-le and lp64-be.
The contract returns one of the three actual RecordCompare functions. Integer
selection implies MEM_Int, nAllField<=13 and the cached integer. String
selection implies MEM_Str without the other five type bits, nAllField<=13,
NULL first collation, and matching cached z/n. Both specialized selections
exclude BIGNULL and establish opposite r1/r2 with the selected sort direction.
Assigns: only p->r1, p->r2, p->u and p->n. No callee replacement or loops.
String n and z remain unrestricted: this function copies them without reading
string bytes. Later comparators must establish their own buffer validity.

| Requires | Counterexample without this clause (lp64-le) | Justification |
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

Harness allocations include undersized and exact-size objects, plus one extra
byte (sort: 0..2 bytes). p has at least its two leading pointer fields so SETUP
can connect pKeyInfo and aMem; KeyInfo has its fixed header so SETUP can connect
sort flags. All remaining fields and heap bytes are nondet. Distinct allocated
typed objects provide the input graph. Struct-size requirements express valid
complete objects, not claims about how little of a struct its accesses touch.

Footprint checks: one sort byte passes, zero fails. One full collation entry
passes, no entry fails. BUT reducing SZ_KEYINFO(1) by one byte also passes CBMC
(543/543, lp64-le). Its flexible-array bounds property checks the start of the
pointer at offset 32, not its full 8-byte extent. Tested: ASan on unmodified
upstream reports an 8-byte overread at 93045 for that 39-byte allocation.
The retained contract requires all 40 bytes (24 on ilp32). No weakened contract
is retained. Byte-level minimality under builder §2.4 remains unresolved;
report is NEEDS-DECISION, with exact evidence and a request to the orchestrator.

Proved coverage: 21/21 executable lines on each configuration; no gaps.
Tested mutation workflow: M-052 and M-053 killed by CBMC bounds/postconditions.
Tested scans: overlay unchanged; scan passes. No invariants are needed.
Assumed: external input obligations are the report's ledger draft, not yet an
approved LEDGER.md entry. No boundary callee or record-padding assumption.
Trusted: CBMC and its semantics/models, and the preprocessor (TRUSTED.md).

## Unreached lines
- none
