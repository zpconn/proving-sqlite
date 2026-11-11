# C-07: serialGet and serialGet7 (P1)

Proved: both contracts on lp64-le, ilp32-le and lp64-be; 437 properties
per configuration, zero failures under the unchanged proofs/CHECKS.
Both require eight readable bytes and a writable Mem object; only u and
flags may change. serialGet sets MEM_Int for type 6, otherwise MEM_Null
or MEM_Real. serialGet7 returns 0 with MEM_Real or 1 with MEM_Null.
Exact decoded values belong to C-09's P3, which executes the real bodies.
No restriction on serial_type, data bytes, or initial Mem fields is needed.

| Requires (both functions) | Counterexample without it, lp64-le | Caller justification / obligation |
| --- | --- | --- |
| `__CPROVER_r_ok(buf,8)` | serialGet: extent=12, offset=12; serialGet7: extent=5, offset=5. Both read beyond the object at 91950 / 91984. | C-08 forwards buf for types 6/7 at 92060-92064 and must supply eight bytes. C-17 passes aKey1+d1 at 92670, 92696, 92778; its buffer/slack proof must establish eight remaining readable bytes (LEDGER A-001). These caller proofs are not claimed here. |
| `__CPROVER_w_ok(pMem,sizeof(Mem))` | Removing only this clause allows malloc to return NULL: serialGet fails the u.i store at 91956; serialGet7 fails memcpy's destination check at 91989 and flags at 91991. | C-08 forwards its writable output Mem at 92064. C-17 passes its automatic Mem mem1 declared at 92620, at all three sites above. No initial field value is read by either helper. |

The harness chooses extent<=16, offset<=extent, and allocates input bytes;
it excludes input malloc failure only to form the pointer. Neither setup
requires eight remaining bytes. Mem allocation may fail; its contract
alone excludes NULL. All input bytes and the u32 serial_type are nondet.
These finite allocation sizes include insufficient, exact, and larger
footprints and interior pointers; they are harness bounds, not caller
requirements. The functions do not inspect allocation size or base.
The harness uses distinct allocations; the contract has no separation
requirement. By inspection, both finish all buf reads before any Mem
write, so overlapping readable input does not require a new clause.
Writable sizeof(Mem) expresses a valid output object, not a claim that
all its bytes are written: assigns is exactly the eight-byte u and flags.

Proved footprint sufficiency: eight bytes pass above. A scratch contract
with r_ok(buf,7), all other clauses unchanged, fails each function's read
of buf[7] at 91951 / 91985, extent=16 and offset=9. Each has one concrete
FAILURE, plus 53 / 45 UNKNOWN follow-ons; these are not independent bugs.
The initial no-input-requires run has 16 FAILURE plus 136 / 128 UNKNOWN.
The no-output-requires run has 35 / 20 FAILURE plus 14 / 5 UNKNOWN.
All negative counterexamples violate the final requires; no finding.

Loops: none in either function; no unwinding or overlay spans needed.
Default NDEBUG removes debug assertions; mixed-endian float is disabled
on all three frozen configurations. memcpy uses its Trusted CBMC model.
The i64 access to u64 x at 91956 uses corresponding signed/unsigned types
(C11 6.5p7). Locals are initialized before reading; each non-void path
returns. Integer shifts are unsigned or fit int. memcpy writes double
bits without a type-punning cast; IEEE 754 representations do not trap.
These UB-CLASSES.md inspection arguments are not additional Proved claims.

## Unreached lines
- none

## Open questions
Coverage: 60/60 lines; M-027 through M-030 killed, none equivalent.
Overlay comparison, harness scan, and include checks pass.
Caller obligations above remain for C-08/C-17; no change to a frozen file,
another contract, or LEDGER.md is requested. No new Assumed boundary.
Trusted: TRUSTED.md dependencies. Tested: no native runtime claim.
