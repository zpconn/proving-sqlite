# C-15: bounded measurement candidate, round 4

NEEDS-DECISION: proposed K=4, N=256; neither bound is approved.
Proved: bounded CBMC runs return PASS on all three configurations, 1,759
properties each, zero failures. This is not an approved P1 claim: Tested
negative controls expose a legacy function/loop framing gap (report b4).
Tested: native ASan/UBSan, 1,414 cases, 1,362 beyond the proposed bounds.
Assumed: A-001 exact readable extent and A-002 native eight-byte alignment.
Trusted: legacy contracts T-006, CBMC/C/models/preprocessor; b4 requests
triage of the observed framing gap before this contract is used by callers.

Requires writable record and incoming nField Mems, positive capacity,
readable KeyInfo prefix through db, C-14's shared layout, eight-byte aMem
alignment, and input/KeyInfo objects distinct from the output object.
A-001 is verbatim: nKey>=0 and max(nKey,1)+8 readable bytes at pKey.
Ensures default_rc=0 and output nField<=incoming capacity. Assigns names
only default_rc,nField and each eligible cell's u,z,n,flags,enc,db,szMalloc.
Four guarded cell groups describe only the proposed bounded domain.
The broader loop frame is retained as instructed; it currently prevents
claiming the narrower function frame was checked soundly (b4's toy).
| Requires | Negative evidence | Caller justification |
| --- | --- | --- |
| writable record | Deletion unrun. | C-14 success, upstream 92102-92108. |
| readable KeyInfo prefix through db | Deletion unrun here; C-14 checked prefix minimality. | C-14 retains pKeyInfo; external callers preserve lifetime. |
| writable nField Mems; nField>0 | Zero-capacity deletion still unrun. | C-14 ensures nKeyField+1 with nKeyField<65535. |
| aMem at ROUND8P(sizeof(UnpackedRecord)) after p | Layout deletion unrun. | C-14 source 92105; its contract does not state this equality. |
| input and KeyInfo distinct from output object | Alias deletion unrun. | Fresh allocation in C-14/A-002; external lifetime obligation. |
| eight-byte alignment | Not a CBMC native-alignment check. | Assumed A-002 and C-14's rounded offset; UB-CLASSES.md. |
| A-001 exact clause | +7 fails: nKey=0, one varint precondition; nKey=2, four callee preconditions. Native ASan confirms both real overreads. | Assumed A-001; external b-tree/sorter callers. |

SETUP proposes nKey<=256 and capacity<=4; requires filters out capacity=0.
Constant-sized malloc objects have variable leading offsets: the remaining
input extent is exactly max(nKey,1)+8, and the shared record/Mem suffix is
exactly ROUND8P(sizeof(UnpackedRecord))+capacity*sizeof(Mem). KeyInfo is
separately allocated. Bytes and initial Mem/KeyInfo contents stay nondet.
C-14's relative layout is preserved. Leading padding is not accessed by
SQLite: input indices are unsigned; pMem is aMem+u, with its final backward
step guarded by u>0. See b4 for grid recipes and the padding limitation.

Loop 92134: assigns idx,d,u,pMem,object_from(pMem); decreases nField-u.
Invariant u==0 || u<nField bounds the next slot; same_object and
pMem==aMem+u locate it; idx>=1 && szHdr<=d support A-001; when u>0 the
preceding flags exclude MEM_Agg|MEM_Dyn, supplying MemSetNull's premise.
Only unpack uses legacy. SerialGet's body stays for T-012; its writes are
u,flags,n,z. Its serialGet helper is replaced by C-07's unchanged contract.
Unpack adds enc,db,szMalloc. T-014 forbids the dereferencing-length frame.

## Unreached lines

## Open questions
Coverage runner fails on all configurations: it seeks DFCC's body name,
not legacy's __CPROVER_contracts_original_sqlite3VdbeRecordUnpack. Raw
results have seven uncovered instrumentation goals at 92134; no accepted
coverage claim or invented gap explanation. M-050/M-051/M-063 are killed.
Approve the bounded scope and labels, resolve the framing/coverage tool
issues, complete remaining requires-deletion evidence, and rerun the gate.
The orchestrator's separate pre-merge --adhoc planted-bug check remains.
