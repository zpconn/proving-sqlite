# The ledger agent's second run: what it must cover (kept by the orchestrator)

It runs before §5, after C-15 to C-20 settle (Zach, §4 instructions, 2026-11-10). Its prompt names this file.

## Entries that changed after run 1 (2026-11-10, reports/ledger-2026-11-10.md)
- **A-001**, with each comparator card's slack S once C-17 to C-20 fix it, and C-15's bounds if its bounded P1 is approved.
- **A-005**, restated by C-01's reopened round for a footprint that depends on the value written (Zach, 2026-11-11).
- **A-006**, memcmp's boundary contract (B2, landed 2026-11-11): test its requires and its result range at the call sites C-17 and C-19 replace.
- Any entry C-17's round 4 adds or changes for B1.

## Repros to try (Zach, 2026-11-11)
1. **F-002 through preupdate_new**, as a possible second repro: `INSERT INTO t2 SELECT * FROM t1`, with matching schemas so xferOptimization runs, t1 from a corrupt database file, and a preupdate hook that calls `sqlite3_preupdate_new`. Source reading (LEDGER.md A-001, path 2): with SQLITE_ENABLE_PREUPDATE_HOOK, xferOptimization copies t1's stored record with OP_RowData (142204–142207) into the register that preupdate_new unpacks (96086–96094). Nothing has tested that yet.
2. **Path 3, a hypothesis, not a claim:** the same xferOptimization statement may carry file records into sqlite3BtreeInsert's BTREE_SAVEPOSITION copy (82916–82924), and so overread like F-002. The orchestrator's source reading says xferOptimization's inserts don't set SAVEPOSITION (142200–142207, 142260–142268). Try a repro either way, and say which.

## Coverage gaps from run 1
- A-004: no application log callback was installed, so a callback that writes where it shouldn't is untested.
- A-001: the nKey = 0 case was never reached.
