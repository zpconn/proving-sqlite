# C-12: isAllZero (P1)

Proved: all three configurations pass 79 properties each, zero failures,
under unchanged proofs/CHECKS. No float-to-integer conversions occur.
Contract: if n>0, z supplies n readable bytes; otherwise no storage is needed.
Every int n is accepted. The result is 0 or 1; assigns is empty. The contract
does not specify which bytes produce which result; P1 needs no such ensures.
No callees, struct fields, function-body macros, or ledger entries are used.

| Requires | Counterexample without it (lp64-le) | Caller justification |
| --- | --- | --- |
| `n <= 0 || __CPROVER_r_ok(z,n)` | extent=offset=402653183, n=236978175, i=0: z[0] is one past the allocation; upstream 92372 fails the bounds check. The initial no-requires run reports 3 FAILURE and 33 UNKNOWN, not 36 bugs. | sqlite3VdbeRecordCompareWithSkip sets nStr=(serial_type-12)/2 at 92753 and checks d1+nStr <= (unsigned)nKey1 at 92756 before passing &aKey1[d1],nStr at 92760. Its readable record and valid offsets must discharge this requirement in C-17. |

The harness allocates a nondet extent in [0,INT_MAX], chooses any offset up
to extent, and excludes malloc failure. It leaves length and all bytes
unrestricted. These are allocation/pointer-formation setup bounds, not
contract requirements. Short, exact, larger, and interior tails are present;
only the contract excludes too-short storage for a positive length. The
storage range covers every positive int length at offset zero, subject to
the Trusted CBMC allocation model. No assumption constrains data bytes.

Footprint minimality: the positive proof requires exactly n bytes for n>0.
A scratch contract changes only r_ok(z,n) to r_ok(z,n-1). CBMC then fails
z[0] for n=1, extent=offset=1207959551 (zero bytes remaining). This run has
2 FAILURE and 34 UNKNOWN properties. No requires or byte assumptions are
added to suppress these expected failures, which violate the final contract.
Commands, results, and scratch evidence paths are in reports/C-12-b1.md.

Loop at upstream 92371: assigns i; invariant 0<=i<=max(n,0); decreases
max(n,0)-i, expressed as n>0 ? n-i : 0. It supports up to INT_MAX iterations
without unwinding; i<n ensures i++ cannot overflow, and n<=0 skips the body.
The invariant constrains only the index, never input contents. The sole
PROOF span contains all added whitespace and clauses; SQLite is unchanged.

Tested: coverage passes on all configurations: 12/15 fully covered lines,
three mapped loop-header gaps explained below, zero unexplained. Both
M-044 and M-045 are killed on lp64-le; no equivalents. Overlay equality,
scan, and allowed-includes checks pass.

Assumed: no LEDGER.md entry is used or proposed. Trusted: CBMC 6.11.0,
its C semantics, loop/DFCC transformations and malloc model, and the
preprocessor, as listed in TRUSTED.md. Tested: no native runtime claim.

## Unreached lines
- sqlite3.c:92371: DFCC emits a dead preheader havoc copy skipped by an unconditional jump (coverage blocks 6-15), a non-base branch while __in_base_case is true (28), and a base branch after it becomes false (52). The live initialization, condition, increment, and induction step on this same line are reached; coverage conservatively marks a line uncovered if any mapped block is unreached.

## Open questions
None. C-17 must check this precondition at its call as part of its own proof.
