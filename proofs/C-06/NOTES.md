# C-06: serial type lengths (P1)

Proved: both contracts on lp64-le, ilp32-le and lp64-be; 30 properties
per configuration, zero failures under proofs/CHECKS.
sqlite3VdbeSerialTypeLen accepts every u32 and returns at most 2147483641
(2^31 - 7). sqlite3VdbeOneByteSerialTypeLen requires serial_type < 128;
its return remains within its u8 type (0..255). Both assign nothing.
No exact file-format length is claimed by this P1 card.

| Requires | Counterexample without it (lp64-le) | Caller justification |
| --- | --- | --- |
| OneByte: `serial_type < 128` | serial_type=128; sqlite3.c:91873, sqlite3SmallTypeSizes upper-bound check; 1 failed of 15 properties. | OP_Column tests t < 0x80 at sqlite3.c:99732 before the call at 99734; conversion to u8 preserves that value. No milestone-1 caller. |

The general function has no requires: RecordUnpack (92144) and
RecordCompareWithSkip (92633, 92804) may pass every decoded u32.
With an offset <= INT_MAX, adding its result cannot wrap u32:
2147483647 + 2147483641 = 4294967288 < 2^32.
The skip-first call at 92633 adds it to a byte-sized header length.
Callers must prove their own offset bounds; this card proves the addend.

Both harness inputs are uninitialized plain locals of exactly the parameter
type, with empty SETUP blocks. DFCC applies the contract precondition;
the harness does not independently restrict serial_type, so deleting the
requires exposes the bad index. No bytes, globals or table values are assumed.
DFCC leaves the table unconstrained: its u8 entries suffice for the general
return bound. The one-byte ensures states only the type bound, not the
initialized table's stronger maximum of 57. No table initializer is copied.

Footprint minimality: no pointer or slack requires. The sole range boundary
is tight: 0..127 passes and the immediately adjacent value 128 fails.
Loops: neither function contains a loop; no invariants or unwind settings.
SQLite's default NDEBUG removes the assertions at 91866-91867 and 91872.
Proved: coverage reaches 18/18 lines across configurations; no gaps.
Tested: mutation checks kill M-023..M-026 (4/4, no equivalents); overlay,
scan and include checks pass. See reports/C-06-b1.md for reproduction.

Assumed: no boundary callees or new ledger obligation. The one-byte caller
check is a source justification, not a proof of all of sqlite3VdbeExec.
Trusted: CBMC, its C semantics and transformations, and the preprocessor,
as listed in TRUSTED.md. Tested: no native runtime claim.
Open questions: none.

## Unreached lines
- none
