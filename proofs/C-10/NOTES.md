# C-10: vdbeRecordDecodeInt (P1), round 1

Proved: lp64-le, ilp32-le and lp64-be, 359 properties each, zero failures.
The contract requires readable bytes at aKey according to serial_type:
0/1: 1 byte; 2: 2; 3: 3; 4: 4; 5: 6; 6: 8; otherwise none.
It assigns nothing and adds no ensures: callers need only an i64 for
comparison, and P1 does not require a functional decoding specification.
Every u32 serial_type is admitted; the input bytes remain nondeterministic.
In particular case 0 is covered despite being excluded by the real caller.

| Requires | Counterexample without it (lp64-le) | Caller justification |
| --- | --- | --- |
| Conditional `__CPROVER_r_ok(aKey,k)` for serial_type <= 6 | Initial contract with requires(1): serial_type=1, extent=offset=5 reads outside the allocation at sqlite3.c:92559. 44 FAILURE and 227 UNKNOWN properties (355 total). | sqlite3VdbeRecordCompareWithSkip:92665-92673 excludes 0, 7 and >=10, then passes aKey1+d1. The checks at 92645 and 92805 bound d1 by nKey1; the remaining readable extent is C-17's modular obligation, using its own slack requires under Assumed A-001. Eight bytes beyond any d1<=nKey1 suffice; this card does not establish that allocation premise. |

The harness bounds extent<=16 and offset<=extent, allocates extent bytes,
excludes malloc failure, and passes input+offset. These setup restrictions
make pointer formation meaningful and bound allocation size; they are not
contract requires. All short tails, exact extents, larger tails and interior
pointers are represented. The contract alone excludes insufficient tails.
No initialization of input bytes, serial-type bound, or data assumption.

Footprint minimality: weakening each positive extent by one gives six
FAILURE and 35 UNKNOWN properties (359 total) on lp64-le. Witnesses:

| serial_type | extent | offset | Required k | Failing last-byte read |
| --- | --- | --- | --- | --- |
| 1 (same body as 0) | 15 | 15 | 1 | sqlite3.c:92559, aKey[0] |
| 2 | 15 | 14 | 2 | sqlite3.c:92562, aKey[1] |
| 3 | 14 | 12 | 3 | sqlite3.c:92565, aKey[2] |
| 4 | 9 | 6 | 4 | sqlite3.c:92568, aKey[3] |
| 5 | 9 | 4 | 6 | sqlite3.c:92573, aKey[5] |
| 6 | 8 | 1 | 8 | sqlite3.c:92578, aKey[7] |

Each witness has exactly k-1 remaining bytes; the final k contract passes.
The no-read cases need zero bytes, with no r_ok clause at all.
These short-buffer failures are outside the final requires, not findings.
Loops: none; no invariants or explicit unwind bounds are needed.
UB-CLASSES.md supplies the effective-type argument for the corresponding
signed/unsigned casts at 92569 and 92579; that argument is not Proved here.

## Unreached lines
- none

## Validation
Coverage: 21/21 lines per configuration, 63/63 total, no gaps.
Mutants: M-038 and M-039 killed on lp64-le; no equivalents.
Overlay check: zero spans; scan: zero problems.
Assumed: no boundary callee; the caller's storage obligation belongs to C-17.
Trusted: CBMC, its C semantics, transformations and library models, and the
preprocessor, as listed in TRUSTED.md. Tested: no native runtime claim.
Open questions: none.
