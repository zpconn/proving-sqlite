# C-04: sqlite3GetVarint32 (P1), round 1

Proved: separate/shared harnesses on lp64-le, ilp32-le and lp64-be,
237/245 properties respectively, zero failures under frozen CHECKS.
Requires nine readable bytes at p and sizeof(u32) writable bytes at v.
Assigns only *v; ensures a return in [1,9]. No data-byte or separation
requires. Decoded contents and saturation belong to C-02's real-code P2.
The long path replaces sqlite3GetVarint with its approved C-03 contract.
Its input requirement is discharged by the same p; local u64 v64 at
38183 supplies its output at 38201. No boundary contract is used.

Both harnesses choose nondet extents 0..24 and interior/one-past offsets.
Input offsets count bytes; output offsets count u32 elements and are
bounded by extent/sizeof(u32), preserving alignment. SETUP excludes NULL,
not short tails. The enforced contract alone excludes inadequate storage.
Separate and shared allocations cover disjoint and overlapping regions.
These bounded harnesses do not prove every allocation size; the function
uses only relative reads/writes and never queries allocation size/address.
All bytes are nondet. No high-bit assumption on p[0] is needed: SQLite's
assertions at 38188 and 38202 are removed by its own default NDEBUG.
The unrestricted function can return 1 on the long path; [1,9] is the
byte-count bound needed by idx increments at 92137 and 92630/92640.

| Requires | Counterexample with only this requires deleted, lp64-le | Caller justification |
| --- | --- | --- |
| `__CPROVER_r_ok(p,9)` | input extent/offset=15/15; output extent/u32 offset=19/0; p[1] at 38190 out of bounds. 17 FAILURE, 181 UNKNOWN. | C-15: 92131 and 92137, using A-001's max(nKey,1)+8 readable extent and idx<nKey. C-17: 92630, 92640, 92714, 92748; C-19: 92957. Their pending proofs must establish nine bytes from each call pointer using A-001's comparator slack, still undetermined. |
| `__CPROVER_w_ok(v,sizeof(*v))` | input extent/offset=24/14; output extent/u32 offset=3/0; *v at 38192 out of bounds. 6 FAILURE, 70 UNKNOWN. | Outputs are local u32 szHdr/serial_type (92125, 92135), s1/szHdr1/serial_type (92626, 92614, 92657), or int serial_type (92945), accessed by corresponding unsigned type at 92957. |

The initial no-requires run also fails concrete input/output accesses.
Deletion checks retain the final frame/ensures and separate harness.
Footprint minimality: nine-byte/four-byte sufficiency is Proved above;
one-less negative variants give these concrete counterexamples:
- Input 8: extent/offset=8/0, output extent/u32 offset=19/3; the ninth
  byte read at 38151 fails (1 FAILURE, 24 UNKNOWN). This scratch variant
  executes the real sqlite3GetVarint body rather than replacing its call,
  so failure establishes an actual read, not merely a callee precondition.
- Output 3: extent/u32 offset=3/0, input extent/offset=24/14; the store
  at 38192 fails (6 FAILURE, 70 UNKNOWN).
UNKNOWN statuses are solver follow-ons, not additional counterexamples.
These negative checks do not satisfy the final requires; no finding.

Loops: none. Source inspection for UB-CLASSES.md: character reads permit
aliasing; RHS reads precede each *v store; n and v64 are assigned before
use by the real callee; all paths return. Output pointers are aligned
u32 storage (or corresponding signed int). These arguments need review.

## Unreached lines
- none

## Validation and obligations
Coverage: 15/15 executable lines per harness/configuration, 90/90 total.
M-019/M-020 killed; overlay, scan and include audits pass.
Reproduction commands and evidence are in reports/C-04-b1.md.
Assumed: A-001 supplies record slack; its callers and the comparator
slack obligations remain pending. No new boundary assumption is used.
Trusted: CBMC, its semantics/library models and the preprocessor as in
TRUSTED.md. Tested: no native runtime claim. Open questions: no blocker;
future caller cards must discharge the stated storage requirements.
