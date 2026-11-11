# C-14: sqlite3VdbeAllocUnpackedRecord (P1)

Proved: all three frozen configurations, 133 properties each, zero failures.
Requires a readable KeyInfo prefix through db and nKeyField < 65535.
On success, the result is writable as an UnpackedRecord, retains pKeyInfo,
has nField = nKeyField + 1, and aMem holds nField writable Mem objects.
NULL is permitted. Assigns is empty: only freshly allocated storage is
written (aMem, pKeyInfo, nField); no pre-existing caller object is changed.
The real allocator's omitted state changes remain Assumed under A-002.

The harness allocates a nondeterministic extent in [0,sizeof(KeyInfo)] and
excludes malloc failure. Initial bytes and all fields are unrestricted;
only the enforced contract restricts the readable prefix and count.
This includes exact-prefix, shorter, and larger allocations. The bound is
a harness bound, not a caller requirement; the code neither queries the
input allocation's size nor accesses beyond the two named input fields.
No record, string, or blob bytes are restricted or initialized.

Let E = offsetof(KeyInfo,db) + sizeof(sqlite3 *): 24 on LP64, 16 on ILP32.
| Requires | Counterexample without it (lp64-le) | Caller justification |
| --- | --- | --- |
| r_ok(pKeyInfo,E) | extent=0: out-of-bounds nKeyField at 92102 and db at 92103; 5 FAILURE, 115 UNKNOWN including contract reads. | No in-scope callers; report's draft A-NNN. KeyInfo allocation at 150538-150545 provides its header; external call examples at 74098, 102013, 107884, 109307. |
| nKeyField < 65535 | nKeyField=65535 allocates 3670056 bytes, returns nField=0; count equality fails (1 FAILURE, no UNKNOWN). | No in-scope callers; report's draft A-NNN. Ordinary KeyInfoAlloc calls with X>=1 enforce N<=65534 at 150537; all external paths remain an obligation. |

Proved footprint sufficiency: the final harness includes extent=E.
Negative minimality check: change only the readable extent to E-1;
extent=23 on lp64-le fails the db read at 92103 (1 FAILURE, 67 UNKNOWN).
The final E excludes that counterexample. No input-tail slack is required.
The initial run omitted the count requirement and found only the equality
failure above, not UB. No data-byte restriction was added in response.
Reproduction commands and scratch-variant recipes are in the report.

Loops: none; no invariants, unwinding settings, or overlay edits needed.
Proved checks do not include pointer alignment. Assumed: A-002 supplies
8-byte-aligned fresh storage. ROUND8P's offset is a multiple of eight
(40 on LP64, 32 on ILP32), so the Mem conversion preserves that alignment;
this is the UB-CLASSES.md argument, not a CBMC result.
Only initialized locals are read; field stores are separate statements;
all paths return a value. nKeyField's u16 range bounds allocation arithmetic.
Trusted: CBMC, its C semantics/library models, and the preprocessor as
listed in TRUSTED.md. Tested: no native runtime claim.

Coverage: 10/10 executable lines per configuration, including allocation
failure and success. Default NDEBUG removes the source assertion at 92101.
Mutants: M-048 killed by aMem extent; M-049 by count equality and aMem extent.
Overlay, scan, and all-config include checks pass.
Open questions: orchestrator assigns/reviews the external caller ledger draft.

## Unreached lines
- none
