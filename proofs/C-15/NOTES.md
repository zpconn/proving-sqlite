# C-15: sqlite3VdbeRecordUnpack, incomplete round 2

Proved: none for C-15. NEEDS-DECISION; reports/C-15-b2.md contains
reproducers for CBMC 6.11 DFCC pointer-havoc encoding and a failed workaround.
No card proof run occurred in round 2; the harness, contract, Makefile,
and loop annotations remain the unsuccessful round-1 diagnostic candidate.
Tested: diagnostic tool executions, not native SQLite behavior; see report.
Trusted: CBMC transformations/C/models and preprocessor per TRUSTED.md.
Assumed: A-001 remains exactly max(nKey,1)+8 readable bytes and nKey>=0.
The retained initial contract's max(nKey,1) extent is insufficient; it was
intended to elicit a counterexample, which encoding prevented. It is not
an alternative to A-001 or a usable contract for another card.

| Candidate requires | Counterexample evidence | Caller obligation |
| --- | --- | --- |
| Writable full UnpackedRecord | Not obtained. | C-14 provides this on success. |
| Readable KeyInfo prefix through db | Not obtained. | C-14 retains its input pointer; external lifetime obligation. |
| Writable nField Mems at aMem | Not obtained. | C-14 provides the extent; count and disjoint regions need completing. |
| nKey>=0 and readable max(nKey,1) bytes | Initial insufficient candidate; no trace. | Assumed A-001 supplies the exact stronger extent above. |

Candidate ensures default_rc=0 and output nField<=input nField.
Candidate assigns default_rc, nField, and the incoming whole Mem region;
precise member framing remains unfinished. Eight-byte aMem alignment is
an explicit completion obligation under UB-CLASSES.md and C-14/A-002.
No footprint sufficiency or minimality claim is Proved.

Loop at upstream 92134 uses a contract, never bounded unwinding:
- u==0 || u<nField: count; the initial zero-capacity case remains unresolved.
- same_object(pMem,aMem) and pMem==aMem+u: next output slot.
- idx>=1 && szHdr<=d: header/data relationship needed for A-001.
- u==0 || previous Mem is non-dynamic: intended MemSetNull premise.
- decreases nField-u; assigns idx,d,u,pMem and the incoming Mem region.
None of these obligations has a completed card verdict.

The retained harness uses separate allocations for record and Mems, four
Mem slots, and 64 nondet record bytes: diagnostics only. Completion must
include C-14's shared allocation with disjoint regions and full input range.
No byte constraint or SQLite-body change was introduced in either round.
The toy isolates unconstrained typed pointer havoc followed by callee
write-set havoc. Recomputing the pointer resolves it in the toy but would
rewrite SQLite. A byte-slice pointer frame creates a false failure in an
independent toy and is not adopted. Pure pointer-object/offset invariants
do not materially shrink the SSA. Details and decision request: b2 report.

## Unreached lines

## Open questions
Coverage and mutants remain unrun without a positive card proof.
Resolve the Trusted-tool encoding blocker, then obtain initial traces,
finish structural/layout/alignment requirements, prove the exact A-001
footprint and one-byte-less failure, and run all configurations and checks.
