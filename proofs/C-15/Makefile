CARD := C-15
PROOFS := unpack
unpack_ENTRY := harness_unpack
unpack_ENFORCE := sqlite3VdbeRecordUnpack/contract_sqlite3VdbeRecordUnpack
unpack_REPLACE := sqlite3GetVarint32/contract_sqlite3GetVarint32 sqlite3VdbeSerialGet/contract_sqlite3VdbeSerialGet sqlite3VdbeSerialTypeLen/contract_sqlite3VdbeSerialTypeLen sqlite3VdbeMemSetNull/contract_sqlite3VdbeMemSetNull
unpack_LOOPS := contracts
include ../Makefile.common
