# C-09: serial decoding (P3), round 1

Proved: every u32 serial type and every input byte pattern agree with the
frozen ref_serial_get on lp64-le, ilp32-le and lp64-be: 612 properties each,
zero failures. Both SQLite functions execute their actual overlay bodies.
No contracts, replacements, PROOF spans or new predicates are used.

Contract in plain English: allocate exactly ref_serial_bytes(t) input bytes
and supply a separate writable Mem with arbitrary initial fields. Check its
flags and the type's value fields using ref_serial_get, including departures
D1-D4. P3 imposes no frame condition on other Mem fields; there is no DFCC
assigns clause here. C-07 and C-08 own the functions' modular P1 contracts.
No serial type, data byte or initial Mem field is restricted. The input is
never written by either decoder; the reference sees the original bytes.

| Requires/setup | Counterexample without it (lp64-le) | Justification |
| --- | --- | --- |
| Exactly k readable bytes, k=ref_serial_bytes(t). | Initial independent extent<=8: t=1, non-NULL malloc(0), buf[0] out of bounds at sqlite3.c:92019. | P3 and C-09 explicitly require an allocation of this size; no in-scope caller or external ledger obligation. |
| malloc succeeds when k>0. | Delete the sole assume: t=7, k=8, bytes=NULL; serialGet reads buf[0] at sqlite3.c:91950. | P3's readable-byte premise; NULL remains allowed when k=0. |

The local Mem supplies its full writable storage by construction, separately
from the input allocation. SETUP computes only the allocation size using the
reference table's cases because it cannot call ref_serial_bytes. A separate
assertion checks that size expression against the frozen function. Every
u32 t has an allocation satisfying SETUP; there is no conditional call.

Footprint minimality: exact k passes on every configuration. Separate scratch
lp64-le proofs keep the same checks, fix each t below, and allocate k-1 bytes:

| t | k | k-1 | SQLite out-of-bounds read (upstream line) |
| --- | --- | --- | --- |
| 1 | 1 | 0 | buf[0], 92019 |
| 2 | 2 | 1 | buf[1], 92027 |
| 3 | 3 | 2 | buf[2], 92035 |
| 4 | 4 | 3 | buf[3], 92043 |
| 5 | 6 | 5 | (buf+2)[3], 92055 |
| 6, 7 | 8 | 7 | (buf+4)[3], 91951 (one run per t) |

All other types require zero bytes, already minimal. These deliberately
short/NULL allocations violate P3's premise; they are not SQLite findings.
The report gives exact reproduction instructions and FAILURE/UNKNOWN counts.

Loops: SQLite has none here; ref_be.0 has at most eight iterations, unwound
at 9 with unwinding assertions under the bounded-loop exception. No invariant.
Coverage: 40/40 wrapper and 10/10 helper lines on each configuration.
All seven assigned mutants (M-033..M-037, M-064, M-065) fail only the P3 value
assertion on lp64-le; none is equivalent. The card's prose lists only five,
but the frozen MUTANTS also assigns the two checkpoint-1 additions to C-09.
Tested: overlay, scan and includes checks pass; no native runtime claim.
Assumed: no boundary contract or new ledger
entry. Trusted: CBMC/C semantics, malloc/memcpy models and preprocessor as
listed in TRUSTED.md. Open questions: none.

## Unreached lines
- none
