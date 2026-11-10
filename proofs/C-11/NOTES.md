# C-11: NaN classification and integer/float comparison (P1)

Contracts: neither function requires anything of its scalar arguments or
writes caller-visible memory. sqlite3IsNaN returns nonzero exactly for NaN;
sqlite3IntFloatCompare returns an integer in [-1,1].
The NaN relation is needed for the comparator's float-to-integer safety;
the comparison range permits its caller to negate the result safely.
Both harnesses use unrestricted locals and empty SETUP blocks.
sqlite3_rtree_dbl is double under all frozen configurations (11723);
prove.py checks argument types. This avoids scan.py treating double as a
macro because of SQLite's inactive OMIT_FLOATING_POINT definitions.
Results are assigned to locals to avoid its bare-call declaration heuristic.

Proved: sqlite3IsNaN, 33 properties/configuration, zero failed on all three.
The comparator is NOT Proved: 28 ordinary checks pass, but the dedicated
float-to-integer check fails at r=-2^63 on each configuration. The generated
check demands r>-2^63, excluding the representable signed minimum.
No input restrictions were added. See reports/C-11-b1.md for the decision.

| Requires | Counterexample without it | Caller justification |
| --- | --- | --- |
| None | Not applicable | All i64/double values are admitted at sqlite3.c:92426, 92671 and 92707. |

Footprint minimality: not applicable; there are no pointer or length inputs.
Loops: neither function has a loop; memcpy uses the Trusted library model.
Assumed: no ledger obligations or boundary contracts.
Trusted: CBMC semantics, transformations, library models and preprocessor
as listed in TRUSTED.md. Tested: upstream's r=-2^63 boundary calls return
1 for i=0 and 0 for i=INT64_MIN under ASan/UBSan/float-cast-overflow.
Coverage: 48/48 lines across configurations; no gaps. This ran before the
type-alias/result-local syntax adjustment; the inputs and calls are identical.
Mutants not run: the unmodified baseline already fails the conversion check,
so mutation failures could not establish sensitivity to the planted defect.
Overlay check and final scan pass; no SQLite or frozen files changed.

## Unreached lines
- none

## Open questions
NEEDS-DECISION: correct the Trusted checker's rejection of valid -2^63
conversion through an approved tooling/checker change; retain invalid-value
checks and mutants M-042/M-043. No requires can legitimately exclude -2^63.
