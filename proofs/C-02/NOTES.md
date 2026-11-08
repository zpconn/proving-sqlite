# C-02: P2 varint round trip

Proved: every u64 value, on lp64-le, ilp32-le and lp64-be; 450 properties
per configuration, zero failures under proofs/CHECKS. No function is replaced.
This relational harness needs no separately enforceable function contract.

Contract: the encoder has nine writable bytes, initially arbitrary. It returns
n in [1,9], leaves every buffer byte at index >= n unchanged, and its encoding
decodes to the original value and n. getVarint32 uses SQLite's actual macro,
returns n, and saturates values above 0xffffffff. VarintLen equals n below
2^63 and equals 10 otherwise. The decoder allocation contains exactly n bytes.
The encoder's external writes are its output prefix; decoder outputs are the
separate local u64/u32 objects. No contracts or PROOF spans are added.

| Requires / setup condition | Counterexample without it | Why supplied here |
|---|---|---|
| Nine writable encoder bytes | Eight bytes: putVarint64.pointer_dereference.5 at sqlite3.c:37971; v=0x40000000fffffffe writes p[8] | Local buffer[9]; this card has no in-scope callers |
| Non-NULL decoder allocation | Removing the NULL assume permits malloc failure and a NULL destination in the prefix copy | SETUP checks malloc success; no external allocator assumption |
| Exactly n readable decoder bytes, populated by the encoder | Allocating n-1 and copying only n-1 fails bounds, including v=0, n=1 at sqlite3.c:38024 | Fresh malloc(extent), used only when extent==n; n is Proved in [1,9] |
| Valid, distinct decoder outputs | No extra assumption; local typed objects establish this by construction | decoded64 and decoded32, passed by address (macro takes decoded32) |

The independent nondet extent ranges from 1 to 9 only to select allocation
sizes: every Proved n has a matching extent for every value. The conditional
extent==n does not restrict value or assume encoded bytes. All initial buffer
bytes and the u64 value are nondet. Bytes copied to encoded come solely from
sqlite3PutVarint. The buffer snapshot is a copy, not a byte constraint.

Footprint minimality: nine encoder bytes pass and eight fail. Exact n decoder
bytes pass; n-1 fails. Both negative experiments used the same harness in /tmp,
with only allocation/copy extents changed; see the report for reproduction.
Bounds checks on buffer[9] exclude access outside the object; the suffix
assertions check all remaining bytes inside it. There is no decoder slack.

Loops: no invariants; every loop is bounded by construction below 16 iterations.
putVarint64.0 has eight iterations; .1 and .2 have at most eight on its
non-nine-byte branch. All three use unwind bound 10 with assertions.
sqlite3VarintLen.0 shifts by seven until zero (at most ten condition evaluations),
with unwind bound 11. The harness snapshot, suffix and prefix loops each run
at most nine times, with bound 10. All verification unwinding assertions pass.

Coverage: 133/133 goal lines per configuration (399/399 total); no uncovered
goals. Per function: PutVarint 9, putVarint64 18, GetVarint 87, GetVarint32 15,
VarintLen 4. SQLite's default NDEBUG removes its debug assert statements;
those have no executable goals under the required configuration flags.
Mutants: M-004, M-005 and M-008 through M-016 all killed on lp64-le by P2
value/length assertions (11/11); no equivalence arguments. Both scans pass.

Assumed: no ledger entries or boundary contracts. This pilot has no LEDGER.md,
PROPERTIES.md, or approved example directory yet; the card supplies P2.
Trusted: CBMC, its C/library models and preprocessing, as specified by the
project; this card adds no trust item. Tested: no native runtime claim.
Open questions: none.
