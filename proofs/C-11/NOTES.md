# C-11: NaN classification and integer/float comparison (P1), round 2

Proved: sqlite3IsNaN on all three configurations, 33 properties each.
sqlite3IntFloatCompare: proved for every other (i, r); argued and tested at r = −2^63.
Its 29 properties per configuration pass with the approved exception below.
All 186 checks pass, including the three float-to-integer checks.

Contracts: neither function has requires or writes caller-visible memory.
sqlite3IsNaN ensures nonzero exactly for NaN (`x != x`), needed by the
comparator's conversion guard; sqlite3IntFloatCompare ensures [-1,1],
needed for safe negation at sqlite3.c:92671. Both have empty assigns.
The comparator replaces sqlite3IsNaN with its separately Proved contract.

| Requires / harness restriction | Counterexample without it | Caller justification / authority |
| --- | --- | --- |
| No contract requires | Not applicable | All scalar values admitted at sqlite3.c:92426, 92671 and 92707. |
| SETUP only: `__CPROVER_assume(r != -0x1p63)` | All three configurations fail only `sqlite3IntFloatCompare.overflow.1` at upstream 92434, i=0, r bits 0xc3e0000000000000 (−2^63). | Approved checker exception, evidence/approvals/C-11-f2i-exact-min/APPROVED.md; PROPERTIES.md change 7 and UB-CLASSES.md's argued row for 92434. Not a caller obligation. |

The assume above is the only constraint on r or i; x is unrestricted.
Both inputs use their exact parameter types: sqlite3_rtree_dbl is double
at 11723 in all frozen configurations. No bytes are constrained.
Without the assume, all 28 ordinary comparator properties still pass;
the sole failing conversion check demands r > −2^63 instead of r >= −2^63.
The trace reports overlay 92438, upstream 92434 after removing PROOF spans.
Round-2 commands, timings and traces are summarized in reports/C-11-b2.md.

At r = −2^63, sqlite3IsNaN returns zero and both range guards are false.
C11 6.3.1.4p1 defines (i64)r: the integral value is exactly INT64_MIN.
Then i<y cannot hold; i>y returns +1 at 92436. Otherwise i=INT64_MIN,
(double)i equals r exactly, and the final ternary at 92440 returns 0.
In general the -1 return and final ternary only produce -1, 0 or 1.
Thus the [-1,1] ensures holds for every i at the excluded r as well.
Empty assigns holds: only locals are written, including the NaN helper's
local memcpy destination. Comparisons and the representable integer-to-double
conversion cause no UB (UB-CLASSES.md, 6.3.1.4p2 row). This argues both P1
safety and the full contract used by C-17 for every r, without new requires.
Tested: the approval's native.txt checks i=0,-1,1,INT64_MIN,INT64_MIN+1,
INT64_MAX at this r under ASan/UBSan/float-cast-overflow: all six agree,
exit 0. This finite native evidence is not a CBMC proof of the excluded input.

Footprint minimality: not applicable; no pointer or length inputs.
Loops: neither function loops; no loop annotations or unwind bounds needed.
Assumed: no ledger entries or boundary contracts; no new ledger drafts.
Trusted: CBMC semantics, transformations, memcpy model and preprocessor,
including the documented exact-minimum checker defect (TRUSTED.md).
Coverage: 48/48 lines, no gaps, with the final harness. Inactive isnan-library
and testcase branches produce no goals under the frozen configurations.
Mutants: M-040/M-041 killed by memcpy checks; M-042/M-043 killed by the
retained float-to-integer check, all on lp64-le; none called equivalent.

## Unreached lines
- none

## Open questions
None. The approved exception is the only qualification to the result above.
