# PROPERTIES

What milestone 1 proves, from GOAL.md §2. The statements are GOAL.md's, changed only where bring-up showed it wrong; "Changes from GOAL.md §2" at the end lists each change and its evidence. A claim of any of these is *proved* only when CBMC verified it under the frozen checks (proofs/CHECKS) on every configuration in proofs/CONFIGS (AGENTS.md §4).

Function names and lines are upstream/sqlite3.c's, at the line that names the function (evidence/bringup/01-lines.txt). The 22 functions and their callees are in GOAL.md Appendix A, confirmed against the pin in evidence/checkpoint1/01-scope.md.

## P1. No undefined behavior

For each function f in Appendix A, with in-scope callees replaced by their proved contracts and boundary callees by contracts recorded in LEDGER.md, CBMC proves f's harness on every configuration, with every option in proofs/CHECKS and no failed property. That is: under f's requires, f triggers no check, its ensures hold, it writes only what its assigns lists, and every loop keeps its invariant and decreases its measure (or, for a loop bounded by construction at 16 iterations or fewer, is unwound with unwinding assertions: builder §2.6).

Requires may state sizes, allocation, aliasing and the values of struct fields. They never constrain data bytes: those of a record or page being decoded, or the string and blob contents a Mem points at. A decoder whose read extent depends on data bytes gets its worst-case footprint (9 bytes for a varint).

"Every option in proofs/CHECKS" includes the `%float-to-int` pass: a second CBMC run with `--conversion-check`, restricted to float-to-integer conversions (UB-CLASSES.md). The undefined behaviors CHECKS does not catch are argued case by case in UB-CLASSES.md and are not *proved*.

## P2. Varints round-trip

For every u64 v:
- sqlite3PutVarint writes n bytes, 1 ≤ n ≤ 9, and nothing else.
- sqlite3GetVarint on those bytes returns n and v.
- `getVarint32` returns n and v when v ≤ 0xffffffff, and n and 0xffffffff otherwise.
- sqlite3VarintLen(v) is n for v < 2^63, and 10 for v ≥ 2^63. This is what the code does, measured natively in bring-up §1.8.1: 9 at 2^63−1, and 10 at 2^63 and 2^64−1 (evidence/bringup/08-probes.md). The encoding of a v ≥ 2^63 is 9 bytes long, so for those v sqlite3VarintLen is one more than n.

"Nothing else": no byte beyond the first n changes. "On those bytes": the decoders read only the n bytes sqlite3PutVarint wrote. The getVarint32 clause is about the macro (upstream/sqlite3.c:22361), whose one-byte case is inline and which calls sqlite3GetVarint32 otherwise.

## P3. Serial values decode as the file format says

For every serial type t, and any bytes b of which the first k are readable, where k is `ref_serial_bytes(t)`, sqlite3VdbeSerialGet(b, t, m) leaves in m what `ref_serial_get` in proofs/spec/record_format.h says:
- k is t's Content Size in the file format table for t ≤ 9;
- k is 0 for t = 10 and 11 (departure D2);
- k is 0 for t ≥ 12, since nothing is read (departure D3).

That reference is written from the serial type table of SQLite's file format document (section 2.1, "Record Format"; the copy at the pin is evidence/spec/fileformat2.html), in at most 60 lines, each case citing its row. SQLite's departures from the table are written out there and here:
- **D1. A NaN double decodes as NULL.** Row 7 says the value is an IEEE 754-2008 64-bit float, and the code gives MEM_Null when those bits are a NaN.
- **D2. Types 10 and 11 follow the code.** The table gives them Content Size "variable" ("reserved for internal use … the meanings of these codes can shift from one release to the next"). The code reads 0 bytes for both and gives:
  - 10: NULL with MEM_Zero, n = 0 and u.nZero = 0;
  - 11: NULL.
- **D3. For t ≥ 12, nothing is read.** m points at b (MEM_Ephem: the bytes are not copied), with length (t−12)/2. It is a blob if t is even and text if t is odd. For odd t, (t−12)/2 in integer arithmetic is the table's (t−13)/2.
- **D4. Types 8 and 9 decode as 0 and 1 with no schema-format check.** The table gives each "(Only available for schema format 4 and higher.)"; the schema format number is a database header field (§1.3.10, offset 44), and format 4 is the one that "adds two new boolean record type values (serial types 8 and 9)". sqlite3VdbeSerialGet has no schema format to look at and checks none: `pMem->u.i = serial_type-8; pMem->flags = MEM_Int;` (upstream/sqlite3.c:92071–92072). So P3, and the reference, give the integers 0 and 1 for types 8 and 9 whatever the database's schema format. Whether a record in a format 1–3 database can hold them is the writer's matter, outside milestone 1.

"Leaves in m" is about the value: m's flags exactly, and the field the type uses. That field is u.i for an integer, the bits of u.r for a real, and z and n for a blob or text, plus n and u.nZero for type 10. Nothing is said of Mem's other fields, which the code doesn't set: m->enc for text is the caller's.

## Changes from GOAL.md §2

1. **P3's k for types 10 and 11** (Zach, checkpoint 1 instructions): GOAL.md says k is "t's size in the file format table for t ≤ 11", but the table at the pin gives "variable" for 10 and 11 (evidence/spec/fileformat2.html). The code reads nothing for them, so k is 0, stated as departure D2.
2. **P3, "leaves in m"**: GOAL.md does not say which Mem fields count. This file names them (above), including MEM_Ephem for t ≥ 12, which is how the code says "points at b" (upstream/sqlite3.c:92082).
3. **P1, "every option in proofs/CHECKS"**: CHECKS has no single float-to-integer option (bring-up §1.4, PROGRESS.md item 4), so the `%float-to-int` pass stands for it.
4. **P1, loops**: unwinding with unwinding assertions is allowed for a loop bounded by construction at 16 iterations or fewer (builder §2.6, checkpoint 0 decision A), besides loop contracts.
5. **P2, sqlite3VarintLen**: GOAL.md's statement matches what §1.8.1 measured, so it is unchanged; the measured values are cited.
6. **P3, types 8 and 9** (auditor, checkpoint 1 fix 3): the table limits them to schema format 4 and higher; the code doesn't check, so P3 states that as departure D4.
7. **P1 for sqlite3IntFloatCompare, r = −2^63** (Zach's decision on C-11, evidence/approvals/C-11-f2i-exact-min/): CBMC 6.11's float-to-int check rejects that one input, whose conversion at 92434 C11 defines (TRUSTED.md). The harness excludes that input, which also takes it out of the enforcement of contract_sqlite3IntFloatCompare that C-17 relies on, so both no undefined behaviour and the contract (a result in [−1, 1], nothing assigned) are argued there (UB-CLASSES.md). Wherever sqlite3IntFloatCompare's result is stated, RESULTS.md included (tools/results.py), it reads: proved for every other (i, r); argued and tested at r = −2^63.
