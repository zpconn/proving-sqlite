CARD := C-15
PROOFS := p0
p0_ENTRY := harness_sqlite3VdbeRecordUnpack
p0_ENFORCE := sqlite3VdbeRecordUnpack/contract_sqlite3VdbeRecordUnpack
p0_REPLACE := sqlite3GetVarint32/contract_sqlite3GetVarint32 sqlite3VdbeMemSetNull/contract_sqlite3VdbeMemSetNull sqlite3VdbeSerialGet/contract_sqlite3VdbeSerialGet sqlite3VdbeSerialTypeLen/contract_sqlite3VdbeSerialTypeLen
p0_LOOPS := unwind
p0_UNWINDSET := sqlite3VdbeRecordUnpack_wrapped_for_contract_checking.0:2
include ../Makefile.common
