# C-08: sqlite3VdbeSerialGet (P1)

Proved: 512 properties per configuration, zero failures on lp64-le,
ilp32-le and lp64-be under proofs/CHECKS. serialGet is replaced by its
approved C-07 contract; no SQLite source or overlay span is changed.
The contract accepts every u32 type and arbitrary data bytes/Mem fields.
It writes only u, flags, n and z. It ensures the result flags (type 7:
MEM_Null or MEM_Real), type 10's zero n/nZero, and for types >=12 the
input pointer and length (type-12)/2. Exact decoded numbers belong to P3.

| Requires | Counterexample without it (lp64-le) | Caller justification / obligation |
| --- | --- | --- |
| Writable sizeof(Mem) at pMem | With only this clause removed: mem=NULL, type=10, extent=16, offset=3; flags store at 92005 fails. | C-15 supplies successive p->aMem cells (92125, 92143, 92146), requiring its own array-capacity proof. C-17 passes its automatic Mem mem1 (92620, 92706). No initial field value is needed. |
| For types 1..7, readable k bytes: 1,2,3,4,6,8,8 respectively | With only input requires absent: type=1, extent=offset=15; buf[0] at 92019 is outside the allocation. | C-15 passes aKey+d with d<=nKey (92134, 92143); Assumed A-001 supplies up to eight trailing bytes. C-17 passes aKey1+d1 (92706); its d1/slack proof must supply k bytes, as A-001 leaves for C-17. |

The setup bounds extent<=16 and offset<=extent, allocating nondet bytes
and a separate Mem. Input allocation succeeds to form buf+offset;
Mem allocation may fail, excluded only by the enforced contract.
These finite allocation bounds include short, exact, larger and interior
footprints; the code does not inspect object size/base. No byte is assumed.
For all other types k=0: no readability condition, even for long blobs.
The distinct allocations are a harness bound, not a separation requires:
each branch finishes all input reads before writing Mem, by inspection.

Proved footprint sufficiency: the final contract passes at each k.
Reducing each positive k by one gives these counterexamples:
types 1..5: (extent,offset)=(2,2),(3,2),(7,5),(7,4),(12,7),
failing buf[k-1] at 92019, 92027, 92035, 92043, 92055 respectively.
Type 6: (14,7) fails serialGet's eight-byte precondition at 92064.
Type 7: (15,8) fails that precondition in a separate type-7 run (1 FAILURE,
0 UNKNOWN). C-07 shows the actual eighth-byte read fails at seven bytes.
Zero cannot be reduced.
The short run has 6 FAILURE and 71 UNKNOWN follow-ons; no finding.
Removing only output requires has 170 FAILURE and 272 UNKNOWN; removing
only input requires has 29 FAILURE and 181 UNKNOWN. Details in the report.

Loops: none; no loop annotations or unwind settings are needed.
UB-CLASSES.md inspection: signed-byte products fit int, type 5's product
fits i64; input reads are unsigned-char accesses. No unsequenced effects,
uninitialized automatic reads, or alignment-increasing casts occur here.
The function is void. Debug assertions/testcase and __HP_cc's workaround
are outside these default configurations. These are inspection arguments,
not additional Proved claims. C-07 covers serialGet's body separately.

Assumed: A-001 remains a caller obligation, not validated by this card.
Trusted: CBMC, C semantics, transformations, malloc/free models and the
preprocessor as listed in TRUSTED.md. Tested: no native runtime claim.
Open questions: none requiring a decision; C-15/C-17 caller proofs remain.
Proved: coverage 123/123 lines. Tested: M-031/M-032 killed; overlay, scan
and includes checks pass. No mutant is equivalent.

## Unreached lines
- none
