# C-01: varint writers (P1), round 4

Proved: both contracts on lp64-le, ilp32-le and lp64-be, 273 properties
per configuration, zero failures under unchanged proofs/CHECKS.
Let N(v) = 1 + sum of [v >= 2^(7*j)] for j=1..8.
Each contract requires N(v) writable bytes at p, assigns only those bytes,
and ensures a return in [1,9]. Output contents are unrestricted.
N(v) is 1..8 at the seven-bit boundaries, and 9 for v>=2^56.
It is min(sqlite3VarintLen(v),9): VarintLen returns 10 for v>=2^63.
The size expression is written directly in each clause because CBMC rejects
function calls in assigns sizes. No shared predicate or SQLite code changed.
put64 enforces the helper; put enforces the wrapper with the helper replaced.

The unchanged round-2 harness allocates nondet extent<=16 and selects
nondet offset<=extent, excluding malloc failure. It does not require enough
remaining storage. Both values and initial output bytes are arbitrary.
The contract alone excludes insufficient storage; offsets include interior
pointers. The allocation bound is a harness bound, not a caller requirement.

| Requires | Counterexample when that requires alone is deleted (lp64-le) | Caller justification |
| --- | --- | --- |
| putVarint64: w_ok(p,N(v)) | extent=11, offset=3, v=1152921504741066752: p[8] dereference fails at sqlite3.c:37971; 11 FAILURE, 52 UNKNOWN. | sqlite3PutVarint forwards p and v at sqlite3.c:38001; its modular proof checks this requirement. External direct users: A-005 restatement in report. |
| sqlite3PutVarint: w_ok(p,N(v)) | extent=5, offset=5, v=8: p[0] dereference fails at sqlite3.c:37993; 9 FAILURE, 21 UNKNOWN. | C-02 supplies buffer[9]. OP_MakeRecord sums VarintLen(serial_type) at sqlite3.c:100267, allocates at 100298-100308, writes at 100374; external obligation: report's A-005 restatement. |

Proved footprint sufficiency: supplemental body-executing harnesses partition
all u64 values into the nine length bands and allocate exactly k bytes.
Both writers pass for every band on every configuration (54 passing runs).
Allocating k-1 bytes instead produces a concrete out-of-bounds write in each
of 54 negative runs: helper line 37987 for k=1..8, line 37971 for k=9;
wrapper line 37993 for k=1, 37998 for k=2, otherwise the helper's lines.
These scratch checks use no contracts/replacements, so cannot pass vacuously
by assuming a writable footprint. Scalar value bands leave bytes arbitrary;
the final harness does not restrict v. Report gives commands and generators.
Removing requires is a separate experiment with the final harness and frame.
All negative failures violate final requires, not findings under them.

All three helper loops use unwind 10 with unwinding assertions, permitted
because each has at most eight iterations; no loop invariants are needed.
- sqlite3.c:37973: i=7 down through zero, eight iterations.
- sqlite3.c:37980: at most 56 bits, exhausted by eight seven-bit shifts.
- sqlite3.c:37986: copies n bytes, at most eight iterations.
The card's "both loops" wording is a typo; all three are covered.

Coverage goals: 18/18 helper and 9/9 wrapper lines per config,
81/81 total, zero uncovered or unexplained. SQLite's default NDEBUG
(sqlite3.c:15192-15193) removes the debug assertion at 37985 before coverage.
The contracts independently check the return bound.
Mutation checks: M-001, M-002, M-003, M-006, M-007 killed; no equivalents.
Overlay check passes (one pre-existing span elsewhere); scan: zero problems.

Assumed: A-005's external caller obligation needs the report's restatement;
LEDGER.md is unchanged. The in-scope helper call is discharged by proof.
Tested: no new runtime claim; the earlier ledger run found zero real overflows.
Trusted: CBMC, its C semantics/library models, preprocessor (TRUSTED.md).
Open questions: none blocking; orchestrator updates A-005 from the report.

## Unreached lines
- none
