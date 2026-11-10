# C-03: sqlite3GetVarint (P1), round 1

Proved: separate/shared allocation harnesses on lp64-le, ilp32-le and
lp64-be: 331/339 properties respectively, zero failures (2,010 total).
The unchanged CHECKS include float-to-integer discovery; none applies here.
Requires nine readable bytes at p and one writable u64 at v. Assigns *v
only. Ensures a return in [1,9], and >3 if the first three input bytes
had their continuation bits set. That condition uses old bytes, so aliasing
cannot change its meaning. Decoded contents belong to C-02's real-code P2.

Both harnesses bound nondet allocation sizes to 0..24 bytes and choose
interior offsets, including one-past pointers and inadequate tails.
Input offsets count bytes; output offsets count u64 elements and are
bounded by extent/sizeof(u64), preserving alignment. SETUP excludes NULL
allocations but never requires the final read/write footprints or fixes
any data bytes. The contract alone excludes insufficient tails.
Separate allocations and a shared allocation cover disjoint and overlapping
storage; no non-aliasing requires is needed. These are bounded harnesses,
not a proof for every allocation size. The decoder neither queries object
size nor uses addresses except within its relative read/write footprints.

| Requires | Counterexample with this requires alone deleted (lp64-le) | Caller justification |
| --- | --- | --- |
| `__CPROVER_r_ok(p,9)` | input extent=7, offset=7: first read at 38024 is out of bounds; output extent=9, offset=0 is valid. 31 FAILURE, 248 UNKNOWN, including history-expression checks. | C-04 forwards p unchanged at 38201 after reading p[1..2]; its own worst-case footprint must supply nine bytes. This caller proof is pending. External callers have the report's ledger draft. |
| `__CPROVER_w_ok(v,sizeof(*v))` | input extent=23, offset=7; output extent=7, offset=0: *v at 38025 is out of bounds. 11 FAILURE, 39 UNKNOWN. | C-04 declares u64 v64 at 38183 and passes &v64 at 38201; C-02 passes &decoded64. External callers have the report's ledger draft. |

The initial no-requires run also found real read/write bounds failures.
Deletion experiments retain the final assigns/ensures and harness.
Proved footprint sufficiency above; the one-less negative checks use the
separate harness, changing only the relevant requires in scratch:
- Input 8: extent=22, offset=14, eight 0x80 bytes; the ninth-byte read at
  38151 fails (1 FAILURE, 24 UNKNOWN). Output extent=15, offset=0.
- Output 7: extent=23, u64 offset=2, seven remaining bytes; *v at 38025
  fails (11 FAILURE, 39 UNKNOWN). Input extent=24, byte offset=6.
UNKNOWN is a follow-on solver status, not an additional counterexample.
None of these negative checks satisfies the final requires.

C-04's macro path has p[0..2] continuation bits set on reaching 38201;
the postcondition then supplies 4..9 without a data-byte requires.
C-02 executes the real decoder with an exact encoded-length allocation;
it does not replace this decoder by its worst-case-footprint contract.

Loops: none; no unwinding or PROOF spans are needed.
Source inspection: signed-char reads (38024, 38028) are allowed character
accesses; character alignment is 1. a, b and s are assigned before use,
stores follow all input reads on each path, and all paths return 1..9.
These UB-CLASSES.md arguments require independent reviewer confirmation.
SQLite's default NDEBUG removes the assertions at 38034-38035.

## Unreached lines
- none

## Validation and obligations
Coverage: 87/87 executable lines per harness/configuration; no gaps.
Mutants M-017/M-018 killed; overlay, scan and include audit pass.
Assumed: proposed external storage obligation, pending a ledger ID; no
boundary callee. C-04 must discharge its own input-footprint obligation.
Trusted: CBMC, its semantics/library models, and the preprocessor, as in
TRUSTED.md. Tested: no native runtime claim. Open questions: no blocker.
