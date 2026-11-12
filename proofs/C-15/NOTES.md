# C-15: sqlite3VdbeRecordUnpack, bounded P1 (round 5)

Proved: both shapes, all three configurations, 1,730 properties per proof,
zero failures under unchanged CHECKS; no float-to-integer properties.
C-15 unpack: bounded: p->nField <= 4, nKey <= 256
C-15 unpack_start: bounded: p->nField <= 4, nKey <= 256
Assumed: A-001 readable slack, A-007 layout/lifetime, A-002 alignment.
Trusted: CBMC/C/models/preprocessor and legacy contracts, T-006/T-012.
The whole-cell function frame is reviewed, not Proved, under T-015.

Requires live writable record/cells, live KeyInfo through db, A-007's
positive capacity, shared rounded layout, input/output separation and
8-byte alignment. A-001 is verbatim: nKey>=0 and max(nKey,1)+8 readable
bytes. Ensures default_rc=0 and nField<=old(nField). Assigns default_rc,
nField and all bytes of the incoming nField Mem cells (object_upto).
| Requires | Negative evidence / reason | Caller justification |
| --- | --- | --- |
| w_ok(p,sizeof(UnpackedRecord)) | Needed for aMem/pKeyInfo loads and default_rc/nField stores; SETUP already supplies it. | C-14 success, upstream 92102-92108. |
| r_ok(pKeyInfo,offsetof(KeyInfo,db)+sizeof(sqlite3 *)) | enc/db read at 92138-92139; C-14's prefix minimality evidence applies; SETUP supplies full KeyInfo. | C-14 retains pKeyInfo; A-007 lifetime. |
| w_ok(aMem,sizeof(Mem)*nField) | Last cell is written before capacity break; end-exact SETUP supplies the extent. | C-14 ensures extent; A-007 keeps it live. |
| nField>0 | Deleting this requires: capacity=0,nKey=56, out-of-bounds enc store at 92138 (b5). | C-14's nKeyField<65535 and nField=nKeyField+1; A-007. |
| rounded aMem offset; distinct output/input objects | Needed for frame geometry and stable inputs; not independently minimized. | A-007; C-14 source 92105, not its contract. |
| eight-byte aMem alignment | Native-alignment obligation, not a CBMC alignment check. | A-002/A-007; C-14 rounds its offset. |
| A-001 exact clause | +7 fails at nKey=0 (header) and nKey=2 (serial/varint); b4 CBMC traces and native ASan. | Assumed A-001, still conditional despite known caller violations. |

Both SETUPs use approved separate bounds and constant backing objects;
record bytes, initial Mem bytes and KeyInfo fields remain nondeterministic.
unpack's offsets leave exactly max(nKey,1)+8 bytes and rounded-record+
capacity*sizeof(Mem) bytes to the ends. unpack_start uses zero offsets,
checking the lower boundaries; it has unused trailing space below maxima.
Malloc failure is excluded before arithmetic; no input bytes are narrowed.

Loop 92134: assigns idx,d,u,pMem,object_from(pMem); decreases nField-u.
Invariant u==0 || u<nField bounds the next cell (capacity is positive).
Invariant same_object(pMem,aMem) and pMem==aMem+u locate that cell.
Invariant idx>=1 && szHdr<=d supports A-001 with the loop guard d<=nKey.
Invariant u==0 || !VdbeMemDynamic(pMem-1) supports the final MemSetNull.
T-015 inclusion: in unpack's end-exact layout, the object ends at
&aMem[capacity], so object_from(pMem) is cells [u,capacity), wholly inside
the function's [0,capacity) frame. It excludes the preceding record.
The start-exact helper's havoc also includes unused trailing backing bytes;
its frame inclusion is not independently claimed. Real writes are to the
current cell with u<capacity; the final NULL write is in cell u-1 when
u<capacity or capacity-1 on break. This also argues the frame for larger
caller allocations. The only record writes are default_rc and nField.
SerialGet keeps its body (T-012 static aFlag); it writes u,flags,n,z;
its replaced serialGet helper writes u,flags. Unpack adds enc,db,szMalloc.
Both proofs use legacy (T-006); T-014 requires the pointer-tail loop frame.
Tested: native seven-member preservation, 1,414 cases, 1,362 past bounds;
M-050/M-051/M-063 killed by unpack on lp64-le. Full details are in b5.
Tested diagnostic, measured once, not gated: K=8,N=256, lp64-le, 1,036 s,
default solver, timeout 3600 s, 1,787 properties/0 failed (approval evidence).
The approved gate remains K=4,N=256 and 600 s; full-range P1 is not claimed.

## Unreached lines
- sqlite3.c:92134: Legacy's duplicate preheader havoc is skipped by an unconditional jump (blocks 28-32); block 118 requires non-base mode in the base copy, and block 209 requires base mode after it is set false for induction. The condition, body, break and live induction checks are reached; coverage conservatively marks the line uncovered if any mapped block is unreached.

## Open questions
None for the builder. The reviewer checks T-015 and both shapes; the
orchestrator performs the separate --adhoc planted-bug check before merge.
