# C-01: varint writers (P1), round 2

Proved: both contracts on lp64-le, ilp32-le and lp64-be, 225 properties
per configuration, zero failures under the unchanged proofs/CHECKS.
Each requires nine writable bytes at p, permits writes only to p[0..8],
and ensures a return in [1,9]. This is the maximum uniform footprint;
encoding contents and exact value-dependent length belong to C-02's P2.
put64 enforces the helper; put enforces the wrapper with the helper replaced.

The harness chooses nondet size_t extent and offset, allocates extent bytes,
and passes output+offset. SETUP bounds extent<=16 and offset<=extent and
excludes malloc failure so forming the pointer is valid. It does NOT require
nine remaining bytes: the contract alone excludes insufficient storage.
Sizes 0..16 include short objects, exact nine-byte tails, and larger tails;
offset also exercises interior pointers. These are bounded harness sizes,
not extra contract requirements on callers. Value and initial bytes are
unrestricted. No helper defines or substitutes SQLite code.

| Requires | Counterexample when that requires alone is deleted (lp64-le) | Caller justification |
| --- | --- | --- |
| putVarint64: `__CPROVER_w_ok(p,9)` | extent=3, offset=3, v=9223372037123211264: out-of-bounds p[8] at sqlite3.c:37971; 11 FAILURE, 52 UNKNOWN properties. | sqlite3PutVarint forwards the same pointer at sqlite3.c:38001; its modular proof checks the helper precondition. External direct users have the draft obligation below. |
| sqlite3PutVarint: `__CPROVER_w_ok(p,9)` | extent=8, offset=8, v=0: out-of-bounds p[0] at sqlite3.c:37993; 9 FAILURE, 21 UNKNOWN properties, including helper precondition failure on another path. | No higher in-scope SQLite caller. C-02's harness supplies buffer[9]. External caller obligation is the report's unnumbered ledger draft; sqlite3.c:108087–108088 supplies aByte[10] as one example only. |

These deletion checks leave assigns and ensures unchanged and use the final
harness. They address review issues 1–2 independently of footprint minimality.

Footprint minimality: separate scratch contracts require/frame eight bytes;
both proofs execute the helper body, with its loops unwound at 10.
put64: extent=11, offset=3, v=2^63; put: extent=13, offset=5,
v=2305843009214742528. Both have exactly eight remaining bytes and fail
p[8] at sqlite3.c:37971. Each reports 3 FAILURE and 24 UNKNOWN properties,
not 27 bugs. Nine-byte contracts pass above. These are not findings under
the final requires. Reproduction commands and traces are in the report.

Loops: all three helper loops use unwind 10 with unwinding assertions;
DFCC's renamed body appears in put64_UNWINDSET. No invariants are needed
under the bounded-loop exception (all are below 16 iterations).
- sqlite3.c:37973: i=7 down through zero, eight iterations.
- sqlite3.c:37980: high-byte branch not taken; at most 56 bits remain,
  exhausted by seven-bit shifts in at most eight iterations.
- sqlite3.c:37986: copies n bytes, at most eight iterations.
The card's wording "both loops" is a typo; all three are covered.

Coverage: 18/18 helper and 9/9 wrapper lines per configuration, 81/81 total;
zero uncovered or unexplained goals. SQLite's default NDEBUG at
sqlite3.c:15192–15193 removes its debug assertion at sqlite3.c:37985.
The contract independently checks the return bound. Harness adds no flags.
Mutation checks: M-001, M-002, M-003, M-006, M-007 killed; no equivalents.
Overlay check: zero spans; scan: zero problems.

Assumed: external output-storage obligation is only a ledger draft, pending
orchestrator ID; no boundary callee. PROPERTIES.md and LEDGER.md are absent
in this pilot; the card supplies P1. C-02 is now an approved example.
Trusted: project-design CBMC/C/library models and preprocessor; TRUSTED.md
is not yet present. Tested: no native runtime claim. Open questions: no
blocker; orchestrator assigns the ledger draft's ID (review issue 4).
