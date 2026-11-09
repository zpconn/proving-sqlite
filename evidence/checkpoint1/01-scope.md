# Appendix A confirmed against the pin (GOAL.md §2, item 1)

Checked 2026-11-09 against upstream/sqlite3.c (pin.txt: SQLite 3.53.4, sha256 b1dd5d74…).
- **Lines:** each is the line that names the function (evidence/bringup/01-lines.txt). Function extents come from tools/overlay.py's function_ranges.
- **NLOC:** non-blank lines left after comments are removed, `#if` lines included. Appendix A counted differently, and is for budgeting only.
- **Loops:** `for`, `while` and `do` statements.
- **Direct callees:** from `goto-instrument --call-graph` on the whole overlay, compiled per configuration (proofs/C-01/build/<config>/harness.o.goto), so macros are expanded. **The graph is the same on all three configurations**.

| Lvl | Function | Line | Names it | Extent | NLOC (A) | Loops (A) | Direct callees (call graph) | Appendix A | Card |
|---|---|---|---|---|---|---|---|---|---|
| 0 | sqlite3VarintLen | 38215 | yes | 38215–38219 | 5 (7) | 1 (1) | — | — | C-05 |
| 0 | putVarint64 | 37967 | yes | 37967–37990 | 24 (25) | 3 (3) | — | — | C-01 |
| 0 | sqlite3GetVarint | 38021 | yes | 38021–38169 | 104 (106) | 0 (0) | — | — | C-03 |
| 0 | sqlite3VdbeSerialTypeLen | 91862 | yes | 91862–91870 | 9 (9) | 0 (0) | — | — | C-06 |
| 0 | sqlite3VdbeOneByteSerialTypeLen | 91871 | yes | 91871–91874 | 4 (5) | 0 (0) | — | — | C-06 |
| 0 | serialGet | 91945 | yes | 91945–91979 | 26 (20) | 0 (0) | memcpy | — | C-07 |
| 0 | serialGet7 | 91980 | yes | 91980–91996 | 17 (18) | 0 (0) | memcpy | — | C-07 |
| 0 | vdbeRecordDecodeInt | 92552 | yes | 92552–92584 | 32 (33) | 0 (0) | — | — | C-10 |
| 0 | sqlite3VdbeFindCompare | 93010 | yes | 93010–93055 | 32 (34) | 0 (0) | — | — | C-16 |
| 0 | isAllZero | 92369 | yes | 92369–92375 | 7 (7) | 1 (1) | — | — | C-12 |
| 0 | sqlite3IsNaN | 36445 | yes | 36445–36456 | 12 (8) | 0 (0) | memcpy | — | C-11 |
| 0 | sqlite3VdbeMemSetNull | 86607 | yes | 86607–86613 | 7 (7) | 0 (0) | vdbeMemClearExternAndSetNull | — | C-13 |
| 1 | sqlite3PutVarint | 37991 | yes | 37991–38002 | 12 (12) | 0 (0) | putVarint64 | putVarint64 | C-01 |
| 1 | sqlite3GetVarint32 | 38182 | yes | 38182–38209 | 21 (23) | 0 (0) | sqlite3GetVarint | sqlite3GetVarint | C-04 |
| 1 | sqlite3VdbeSerialGet | 91997 | yes | 91997–92088 | 71 (68) | 0 (0) | serialGet | serialGet | C-08 |
| 1 | sqlite3IntFloatCompare | 92425 | yes | 92425–92442 | 16 (16) | 0 (0) | sqlite3IsNaN | sqlite3IsNaN | C-11 |
| 1 | sqlite3VdbeAllocUnpackedRecord | 92096 | yes | 92096–92109 | 14 (15) | 0 (0) | sqlite3DbMallocRaw | sqlite3DbMallocRaw (boundary) | C-14 |
| 2 | sqlite3VdbeRecordUnpack | 92116 | yes | 92116–92159 | 38 (41) | 1 (1) | sqlite3GetVarint32, sqlite3VdbeMemSetNull, sqlite3VdbeSerialGet, sqlite3VdbeSerialTypeLen | sqlite3GetVarint32, sqlite3VdbeSerialGet, sqlite3VdbeSerialTypeLen, sqlite3VdbeMemSetNull | C-15 |
| 2 | sqlite3VdbeRecordCompareWithSkip | 92607 | yes | 92607–92827 | 192 (198) | 1 (1) | isAllZero, memcmp, serialGet7, sqlite3CorruptError, sqlite3GetVarint32, sqlite3IntFloatCompare, sqlite3VarintLen, sqlite3VdbeSerialGet, sqlite3VdbeSerialTypeLen, vdbeCompareMemString, vdbeRecordDecodeInt | sqlite3GetVarint32, sqlite3VdbeSerialGet, serialGet7, sqlite3VdbeSerialTypeLen, sqlite3VarintLen, vdbeRecordDecodeInt, sqlite3IntFloatCompare, isAllZero; vdbeCompareMemString, sqlite3CorruptError (boundary) | C-17 |
| 3 | sqlite3VdbeRecordCompare | 92828 | yes | 92828–92833 | 6 (6) | 0 (0) | sqlite3VdbeRecordCompareWithSkip | sqlite3VdbeRecordCompareWithSkip | C-18 |
| 3 | vdbeRecordCompareString | 92940 | yes | 92940–93003 | 59 (61) | 0 (0) | memcmp, sqlite3CorruptError, sqlite3GetVarint32, sqlite3VdbeRecordCompareWithSkip | sqlite3GetVarint32, sqlite3VdbeRecordCompareWithSkip; sqlite3CorruptError (boundary) | C-19 |
| 4 | vdbeRecordCompareInt | 92845 | yes | 92845–92932 | 73 (76) | 0 (0) | sqlite3VdbeRecordCompare, sqlite3VdbeRecordCompareWithSkip | sqlite3VdbeRecordCompare, sqlite3VdbeRecordCompareWithSkip | C-20 |

**Result.** Every line names its function, and the loop counts match Appendix A (7 in all). The direct callees match Appendix A's, with three additions:
1. **memcpy**, called by serialGet (91976), serialGet7 (91989) and sqlite3IsNaN (36449). Like memcmp, it is CBMC's library model, so it goes in TRUSTED.md.
2. **vdbeMemClearExternAndSetNull** (86180), called by sqlite3VdbeMemSetNull at 86609 only for a dynamic Mem. Appendix A's facts already say C-13's contract requires `!VdbeMemDynamic(pMem)`, so this callee is unreached in its proof. It is neither in scope nor a boundary, and C-13's card says so.
3. **memcmp**, which Appendix A already notes for sqlite3VdbeRecordCompareWithSkip and vdbeRecordCompareString.

The three boundary functions are at the lines Appendix A gives: sqlite3DbMallocRaw 32113, vdbeCompareMemString 92350, sqlite3CorruptError 191373.

## In-scope callers (the reverse graph)

The count of callers outside milestone 1 comes from the same graph. Function-pointer removal makes it an over-count for the comparators, which are called through a pointer.

| Function | In-scope callers | Callers outside milestone 1 |
|---|---|---|
| sqlite3VarintLen | sqlite3VdbeRecordCompareWithSkip | 3 |
| putVarint64 | sqlite3PutVarint | 0 |
| sqlite3GetVarint | sqlite3GetVarint32 | 3 |
| sqlite3VdbeSerialTypeLen | sqlite3VdbeRecordCompareWithSkip, sqlite3VdbeRecordUnpack | 4 |
| sqlite3VdbeOneByteSerialTypeLen | — | 1 |
| serialGet | sqlite3VdbeSerialGet | 0 |
| serialGet7 | sqlite3VdbeRecordCompareWithSkip | 0 |
| vdbeRecordDecodeInt | sqlite3VdbeRecordCompareWithSkip | 0 |
| sqlite3VdbeFindCompare | — | 1 |
| isAllZero | sqlite3VdbeRecordCompareWithSkip | 1 |
| sqlite3IsNaN | sqlite3IntFloatCompare | 3 |
| sqlite3VdbeMemSetNull | sqlite3VdbeRecordUnpack | 14 |
| sqlite3PutVarint | — | 5 |
| sqlite3GetVarint32 | sqlite3VdbeRecordCompareWithSkip, sqlite3VdbeRecordUnpack, vdbeRecordCompareString | 6 |
| sqlite3VdbeSerialGet | sqlite3VdbeRecordCompareWithSkip, sqlite3VdbeRecordUnpack | 5 |
| sqlite3IntFloatCompare | sqlite3VdbeRecordCompareWithSkip | 2 |
| sqlite3VdbeAllocUnpackedRecord | — | 4 |
| sqlite3VdbeRecordUnpack | — | 5 |
| sqlite3VdbeRecordCompareWithSkip | sqlite3VdbeRecordCompare, vdbeRecordCompareInt, vdbeRecordCompareString | 3 |
| sqlite3VdbeRecordCompare | vdbeRecordCompareInt | 40 |
| vdbeRecordCompareString | — | 38 |
| vdbeRecordCompareInt | — | 38 |
| sqlite3DbMallocRaw | sqlite3VdbeAllocUnpackedRecord | 22 |
| vdbeCompareMemString | sqlite3VdbeRecordCompareWithSkip | 1 |
| sqlite3CorruptError | sqlite3VdbeRecordCompareWithSkip, vdbeRecordCompareString | 67 |

## The order the cards will run in

campaign.py starts a card once every card on its Depends on line is merged, ready cards in card order, at most 4 sessions at once (GOAL.md §3.1). From the cards' Depends on lines:

| Wave | Cards (functions) | Waits for |
|---|---|---|
| merged | C-01 (sqlite3PutVarint, putVarint64), C-02 (P2 round trip) | — |
| 1 | C-03 GetVarint, C-05 VarintLen, C-06 SerialTypeLen and OneByteSerialTypeLen, C-07 serialGet and serialGet7, C-09 P3, C-10 DecodeInt, C-11 IsNaN and IntFloatCompare, C-12 isAllZero, C-13 MemSetNull, C-14 AllocUnpackedRecord, C-16 FindCompare | nothing; 11 cards, run 4 at a time in this order |
| 2 | C-04 GetVarint32 | C-03 |
| 2 | C-08 SerialGet | C-07 |
| 3 | C-15 RecordUnpack | C-04, C-06, C-08, C-13, C-14 |
| 3 | C-17 RecordCompareWithSkip | C-04, C-05, C-06, C-07, C-08, C-10, C-11, C-12 |
| 4 | C-18 RecordCompare | C-17 |
| 4 | C-19 vdbeRecordCompareString | C-04, C-16, C-17 |
| 5 | C-20 vdbeRecordCompareInt | C-16, C-17, C-18 |

There are two critical paths, both five merges long: C-03 → C-04 → C-17 → C-18 → C-20, and C-07 → C-08 → C-17 → C-18 → C-20.
- C-19 and C-20 also depend on C-16, because their requires rest on what sqlite3VdbeFindCompare ensures when it returns them.
- C-15 depends on C-14, because its alignment requires on p->aMem rests on C-14's ensures (UB-CLASSES.md).
- C-09 depends on nothing: like C-02, it runs the real code, with no contracts.

## Statements with two or more side effects (UB-CLASSES.md, 6.5p2)

The scan covered the 22 functions' source, with comments removed, split at `;`, `{` and `}`. It counted assignments, `++`/`--`, calls other than SQLite's pure macros, and the getVarint32 macros. It found these 26 statements, besides two in `#if` branches the default build compiles out: serialGet 91968–91972 (NDEBUG off) and sqlite3IsNaN 36452 (HAVE_ISNAN).
- **putVarint64** (37967–37990): `buf[n++] = ...`; `for(i=0, j=n-1; ...; j--, i++)`.
- **sqlite3GetVarint32:** `n = sqlite3GetVarint(p, &v64)`.
- **sqlite3VdbeAllocUnpackedRecord:** `p = (UnpackedRecord *)sqlite3DbMallocRaw(pKeyInfo->db, nByte)`.
- **sqlite3VdbeRecordUnpack:**
  - `idx = getVarint32(aKey, szHdr)`;
  - `idx += getVarint32(&aKey[idx], serial_type)`;
  - `d += sqlite3VdbeSerialTypeLen(serial_type)`.
- **sqlite3VdbeRecordCompareWithSkip** (12 statements):
  - idx1 assigned from sqlite3GetVarint32, which writes s1 or szHdr1;
  - d1 assigned from sqlite3VdbeSerialTypeLen;
  - rc assigned from sqlite3IntFloatCompare, vdbeCompareMemString or memcmp;
  - `getVarint32NR` twice;
  - `idx1 += sqlite3VarintLen(...)`;
  - `d1 += ...`;
  - lhs initialized from vdbeRecordDecodeInt.
- **vdbeRecordCompareString:** res assigned from memcmp, and from sqlite3VdbeRecordCompareWithSkip.
- **vdbeRecordCompareInt:** res assigned from sqlite3VdbeRecordCompareWithSkip.

In every case:
- the objects modified are different from one another, and from those the rest of the expression reads;
- or the macro's `?:` and `,` order the effects;
- or the compound-assignment rule does (C11 6.5.16p3).

A callee's writes (errCode, eqSeen, *v, s1, szHdr1) never land on the object its result is assigned to. `gcc -Wsequence-point` and `clang -Wunsequenced` (clang 18) report nothing in sqlite3.c.
