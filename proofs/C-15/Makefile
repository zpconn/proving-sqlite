# MEASUREMENT ONLY (orchestrator, Zach's item 7, 2026-11-12): C-15 on the legacy-unwind pass, exact symbolic
# allocations, no nKey bound. Not a proof for merge; local branch wip/c15-unwind.
CARD := C-15
PROOFS := unwind
unwind_ENTRY := harness_unwind
unwind_ENFORCE := sqlite3VdbeRecordUnpack/contract_sqlite3VdbeRecordUnpack
unwind_REPLACE := sqlite3GetVarint32/contract_sqlite3GetVarint32 sqlite3VdbeSerialTypeLen/contract_sqlite3VdbeSerialTypeLen sqlite3VdbeMemSetNull/contract_sqlite3VdbeMemSetNull serialGet/contract_serialGet
unwind_LOOPS := unwind
unwind_UNWINDSET := sqlite3VdbeRecordUnpack.0:4
unwind_CONTRACTS := legacy
include ../Makefile.common
