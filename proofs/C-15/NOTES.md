# C-15: sqlite3VdbeRecordUnpack, incomplete round 1

Proved: none. STUCK after eight consecutive unsuccessful runner attempts
(seven CBMC invocations and one front-end rejection); no property verdict.
The files retain the last diagnostic candidate, not an approved contract.
Assumed: A-001 requires max(nKey,1)+8 readable bytes. The initial contract
still has no slack: it was intended to elicit the initial counterexample,
but encoding exhausted memory before a trace. A-001 was not weakened.
Trusted: CBMC and its transformations/models and the preprocessor per TRUSTED.md.
Tested: no native run; overlay/scan/include results are in the report.

Candidate requires and outstanding justification:
| Requires | Counterexample evidence | Caller obligation |
| --- | --- | --- |
| Writable sizeof(UnpackedRecord) at p | Not obtained; deletion/minimality pending. | C-14 provides writable result on success; no C-15 in-scope caller. |
| Readable KeyInfo prefix through db | Not obtained; deletion/minimality pending. | C-14 retains its readable input KeyInfo; lifetime remains external. |
| Writable nField Mems at aMem | Not obtained; deletion/minimality pending. | C-14 ensures this extent. The positive-count case still needs checking. |
| nKey>=0 and readable max(nKey,1) bytes | Incomplete initial premise; no CBMC trace obtained. | Assumed A-001 supplies the stronger extent; its native no-slack evidence predates this round. |

Candidate ensures default_rc=0 and returned nField<=incoming nField.
Candidate assigns default_rc, nField, and the complete incoming Mem array.
The Mem-region frame overapproximates individual member writes; exact
member framing/preservation remains unresolved, as do general alias cases.
Eight-byte aMem alignment is required by the card but not yet in this
candidate: C-14's alignment argument uses Assumed A-002; CBMC does not
model native alignment. No slack or other footprint minimality is Proved.

Loop at upstream 92134 uses a contract, never bounded unwinding:
- u==0 || u<nField: head count; zero capacity still admitted initially.
- same_object(pMem,aMem): explicit pointer object identity diagnostic.
- pMem==aMem+u: address of next output slot on continuing iterations.
- idx>=1 && szHdr<=d: header/data relationship for the proposed slack bound.
- u==0 || previous Mem has no MEM_Agg/MEM_Dyn: intended null-call premise.
- decreases nField-u; assigns idx,d,u,pMem and the incoming Mem region.
None of these invariant or frame checks has a completed verdict.

The retained diagnostic harness allocates 64 record bytes and four Mems,
with capacity in 0..4. Record bytes remain wholly nondeterministic.
The extent local/assumption is unused after fixing malloc sizes in attempt 7.
Earlier attempts used variable extents and the full u16 capacity range.
Four separate allocations omit C-14's shared record/Mem allocation layout.
These limits are diagnostics, not a completed proof of the card's domain.

## Unreached lines

## Open questions
Coverage and mutants were not run: no positive proof exists.
Next: minimize the DFCC pointer/region-havoc encoding issue in a fresh toy;
then resume from full-domain allocation and caller-compatible alias cases,
obtain counterexamples, add the A-001/necessary structural requirements,
and prove all configurations, minimality, coverage and mutants.
