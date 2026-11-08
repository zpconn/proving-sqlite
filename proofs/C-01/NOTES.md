# C-01: varint writers (P1)

The harness includes the unmodified overlay and leaves both `u64 value` and
all output bytes nondeterministic. There are no setup assumptions.
Each contract requires nine writable bytes starting at `p`, permits writes
only to `p[0..8]`, and ensures a return value in `[1,9]`.
The frame is the maximum footprint over all input values; encoding contents
and the exact value-dependent length are left to C-02's P2 proof.
`put64` enforces the helper contract; `put` enforces the public writer's
contract with the helper replaced by its separately enforced contract.

| Requires | Counterexample without sufficient extent | Caller justification |
| --- | --- | --- |
| `putVarint64`: `__CPROVER_w_ok(p,9)` | Eight-byte object, `v=2^60`: write to `p[8]` at sqlite3.c:37971 fails bounds and assigns checks. | sqlite3PutVarint forwards its unchanged pointer at sqlite3.c:38001; its contract requires nine bytes and the modular proof checks this call. External direct callers have the same obligation. |
| `sqlite3PutVarint`: `__CPROVER_w_ok(p,9)` | Eight-byte object, helper body executed: same bounds failure at sqlite3.c:37971. | No higher in-scope SQLite caller; C-02 is specified to allocate nine bytes. External caller obligation is drafted in the report. One source example is `aByte[10]` at sqlite3.c:108087, passed at sqlite3.c:108088. |

Footprint minimality: the initial lp64-le experiment used eight-byte output
objects, requires and frames, and executed the helper body in both proofs.
Both produced an actual out-of-bounds counterexample (not merely a failed
callee precondition). Changing the objects, requires and frames to nine
bytes establishes the sufficient size in the final proofs. No input value
or byte was restricted. Nine is the minimum uniform extent for all u64s;
it is not claimed necessary for each individual value.

Loops: all three helper loops are unwound with bound 10 and unwinding
assertions, using the DFCC-renamed function in the Makefile. No overlay
annotations or loop invariants are needed under builder rule 2.6.
- sqlite3.c:37973: `i=7` down through zero, eight iterations.
- sqlite3.c:37980: the high-byte branch was not taken, so at most 56 bits
  remain; shifting by seven exhausts them in at most eight iterations.
- sqlite3.c:37986: copies those `n` bytes, at most eight iterations.
The card's phrase "both loops" is a typo; the source has three. All are
within the permitted 16-iteration exception.

SQLite itself defines NDEBUG in this build (sqlite3.c:15192–15193), so its
debug assertion at sqlite3.c:37985 is compiled out. Harnesses add no flags
or macros disabling checks. The contract separately checks the return bound.

No approved card directory, PROPERTIES.md, LEDGER.md or TRUSTED.md exists
at this pilot's starting revision. The card and bring-up examples supply
the applicable property and contract layout. No boundary callee is used.

Proved: both contracts pass on lp64-le, ilp32-le and lp64-be, 191 checked
properties per configuration and zero failures. Coverage reaches 18/18
helper lines and 9/9 wrapper lines on each configuration: 81/81 total,
zero uncovered or unexplained lines. Coverage excludes the compiled-out
debug assertion described above; it does not supply the safety proof.
Mutation checks kill M-001, M-002, M-003, M-006 and M-007 on lp64-le;
none is treated as equivalent. Overlay and scan checks pass.
Open questions: none blocking this card; the report proposes an external
caller requirement for the orchestrator's future ledger.
