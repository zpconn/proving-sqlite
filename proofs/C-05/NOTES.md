# C-05: sqlite3VarintLen (P1)

Proved: lp64-le, ilp32-le and lp64-be each pass 16 properties, zero failures,
under proofs/CHECKS. No float-to-integer conversion properties occur.
Contract: accepts every u64, writes no caller-visible state, returns 1..10.
The harness has an unrestricted automatic u64 and an empty SETUP block.
No callee contracts or ledger assumptions are needed.
Exact encoding-length relationships belong to C-02's P2 proof.

| Requires | Counterexample without it | Caller justification |
| --- | --- | --- |
| None | Not applicable | sqlite3VdbeRecordCompareWithSkip passes a u32 serial type at sqlite3.c:92806; every such value is accepted. |

Footprint minimality: no pointers or storage preconditions; assigns is empty.
There is no slack or length requirement to reduce by one.

Loop at sqlite3.c:38217: unwind 10 with unwinding assertions. Each condition
shifts the unsigned 64-bit input right by seven bits. The body runs at most
nine times; the tenth condition yields zero. This is within the <=16-iteration
exception, so no loop invariant or overlay span is needed. The DFCC-renamed
body is named in UNWINDSET. SQLite's default NDEBUG removes the debug assert;
the contract separately checks the return bound, including the value 10.

Tested: coverage reaches 4/4 lines per configuration (12/12 total).
Both M-021 and M-022 are killed by the loop unwinding assertion on lp64-le.
Overlay check passes with zero spans; scan passes with zero problems.
Assumed: no LEDGER.md entry is used. Trusted: CBMC, its C semantics and
transformations, and the preprocessor as recorded in TRUSTED.md.

## Unreached lines
- none

## Open questions
None.
