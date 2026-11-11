# C-15: sqlite3VdbeRecordUnpack, incomplete round 3

Proved: only a bounded lp64-le diagnostic, 2,017 properties, zero failures,
128 s CBMC. It used 64 input bytes and four Mem slots; not the card's P1.
STUCK: eight subsequent attempts obtained no full-range verdict. See b3.
The retained full-range candidate is not approved for replacement by callers.
Trusted: legacy contracts (T-006), CBMC/C/models and preprocessor.
Tested: diagnostic tool executions only; no native SQLite runtime claim.
Overlay, scan and all-config include checks pass; these do not establish P1.
Assumed: A-001's exact max(nKey,1)+8 readable extent, with nKey>=0;
A-002's native eight-byte allocation alignment through C-14.

Candidate: writable record, readable KeyInfo prefix through db, positive
capacity, writable incoming nField Mems, aligned aMem, and A-001 verbatim.
Ensures default_rc=0 and output nField<=incoming capacity. Assigns default_rc,
nField and the incoming Mem region. Exact member framing is unfinished.
| Requires | Counterexample evidence | Caller justification |
| --- | --- | --- |
| w_ok(p,sizeof(UnpackedRecord)) | Deletion check unrun. | C-14 ensures writable record on success. |
| r_ok(pKeyInfo,offsetof(KeyInfo,db)+sizeof(sqlite3*)) | Deletion check unrun. | C-14's input prefix and retained pointer; lifetime remains external. |
| w_ok(aMem,sizeof(Mem)*nField) | Deletion check unrun. | C-14's output extent. |
| nField>0 | No completed zero-capacity trace; loop writes before testing capacity. | C-14 ensures nKeyField+1, with nKeyField<65535. |
| ((size_t)aMem%8)==0 | Alignment is outside CBMC's checks (UB-CLASSES.md). | Assumed A-002 and C-14's ROUND8P offset. |
| A-001 exact clause | Full-range proof and minus-one check incomplete. | Assumed A-001; external b-tree and sorter callers. |

The harness now allows every nonnegative int nKey and the full u16 capacity,
allocates exactly max(nKey,1)+8 nondet bytes and a shared record/Mem block,
and places aMem at ((sizeof(UnpackedRecord)+7)/8)*8, C-14's layout here.
Allocation failure is excluded before pointer arithmetic. KeyInfo has its
own allocation. No record bytes or Mem string/blob contents are constrained.
The contract still needs any required alias/region separation made explicit;
the harness supplies disjoint record/Mem regions and separate input/KeyInfo.
No claim that this harness discharges all layouts admitted by the contract.

Loop 92134 uses induction, not bounded unwinding; candidate invariants:
- u==0 || u<nField: next slot index, with nField positive under requires.
- same_object(pMem,aMem) and pMem==aMem+u: pointer position.
- idx>=1 && szHdr<=d: relation supporting A-001's read bound.
- u==0 || previous flags exclude MEM_Agg|MEM_Dyn: null-call premise.
- decreases nField-u; assigns idx,d,u,pMem and object_from(pMem).
The tail frame starts at initial pMem; in the exact C-14-shaped allocation
it is exactly the Mem region. Larger allocation tails need further scrutiny.
Using object_upto(aMem,sizeof(Mem)*nField) generated a dereference in an
array type: SAT exhausted memory; SMT aborted. The local-pointer tail frame
avoids that particular encoder fault (independent toy and bounded pass).

Only unpack opts into legacy. sqlite3VdbeSerialGet keeps its body because
its static aFlag aborts replacement under T-012. Its serialGet helper uses
C-07's unchanged contract, as in C-08. Kept-body writes are u,flags,n,z;
Unpack adds enc,db,szMalloc; all lie in the Mem region. Full-range frame and
MemSetNull precondition checks have no completed positive verdict.

## Unreached lines

## Open questions
Full-range encoding; explicit alias premises; precise member framing;
requires deletion and minus-one evidence; all configurations, coverage,
M-050/M-051, and the orchestrator's separate pre-merge planted-bug check.
