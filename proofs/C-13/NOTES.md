# C-13: sqlite3VdbeMemSetNull (P1)

Proved: all three configurations, 69 properties each, zero failures under
proofs/CHECKS. The contract requires writable storage from pMem through the
end of flags, and neither MEM_Agg nor MEM_Dyn in flags. It ensures flags is
exactly MEM_Null and assigns only pMem->flags. No other field is read or
written on this path; no string/blob bytes or other fields are constrained.

| Requires | Counterexample without it (lp64-le) | In-scope caller justification |
| --- | --- | --- |
| `__CPROVER_w_ok(pMem, offsetof(Mem, flags) + sizeof(pMem->flags))` | extent=56, offset=1: no remaining bytes; concrete out-of-bounds flags read at 86608 and write at 86611, plus contract/frame checks (6 FAILURE, 29 UNKNOWN). | RecordUnpack uses a writable aMem cell: 92125, 92138-92143, 92145-92146. At 92153, u>0 and subtracting (u<nField) selects the last decoded cell. C-15 must discharge this at its modular call site; allocation layout is 92102-92107. |
| `!VdbeMemDynamic(pMem)` | With storage alone, extent=22, offset=0 reaches the removed helper at 86609: `vdbeMemClearExternAndSetNull.assertion.1` fails (1 FAILURE). | SerialGet at 92143 sets flags to Null, Null/Zero, Int, Real, or Ephem with Blob/Str (91960, 91977, 92005-92083); none has MEM_Agg or MEM_Dyn. The cleanup at 92153 selects that last decoded cell. This is the card/Appendix A scope restriction; C-15 proves the call-site obligation. |

The harness allocates nondet extent<=2*sizeof(Mem) and chooses a nondet
Mem-element offset of 0 or 1, with offset*sizeof(Mem)<=extent. These setup
bounds make pointer arithmetic valid; malloc failure is excluded. They do
not supply the contract's storage or flags requirements. Short allocations,
exact tails, larger allocations, and interior pointers are represented.
All allocated bytes start nondet. No field values are assigned in SETUP.
These are harness bounds, not contract bounds; the function neither examines
the allocation base/extent nor uses any member except flags on this path.

Proved footprint sufficiency: the prefix ends at byte 22 on LP64 and byte
18 on ILP32. No full-Mem extent is required. Changing only that requires
length to one less fails on every configuration: LP64 extent=77, offset=1
(sizeof(Mem)=56), leaving 21 bytes; ILP32 extent=57, offset=1 (sizeof(Mem)=40),
leaving 17 bytes. Both source accesses fail, with 6 FAILURE and 29 UNKNOWN
properties per configuration. The final requirement passes, including
exact-tail cases in the harness.
Addressing the flags field inside w_ok itself initially failed a pointer
primitive check for extent=18; testing the prefix at pMem avoids forming
an out-of-object field pointer before validating the storage.

Loops: none. Callee contracts/boundary assumptions: none. The card's removed
helper is proved unreachable under the final requires; admitting dynamic
flags fails explicitly, rather than silently omitting its effects.

## Unreached lines
- sqlite3.c:86609-86610: !VdbeMemDynamic(pMem) excludes the destructor call and its branch-exit instruction, attributed to the closing brace/else line.

## Validation and scope
Tested validation tools: coverage 9/15 lines, 6 excluded, 0 unexplained;
M-046 and M-047 killed by the exact-flags postcondition; overlay/scan/includes
pass. Detailed Proved results and reproduction: reports/C-13-b1.md.
Assumed: no new LEDGER.md entry; both requires are C-15 call-site obligations.
Trusted: CBMC, its transformations/C semantics/library models, and the
preprocessor/configurations listed in TRUSTED.md. Tested: no native claim.
Open questions: none; this contract intentionally covers non-dynamic Mems.
