CARD := C-15
PROOFS := unpack unpack_start
unpack_ENTRY := harness_unpack
unpack_ENFORCE := sqlite3VdbeRecordUnpack/contract_sqlite3VdbeRecordUnpack
unpack_REPLACE := sqlite3GetVarint32/contract_sqlite3GetVarint32 sqlite3VdbeSerialTypeLen/contract_sqlite3VdbeSerialTypeLen sqlite3VdbeMemSetNull/contract_sqlite3VdbeMemSetNull serialGet/contract_serialGet
unpack_LOOPS := contracts
unpack_CONTRACTS := legacy
unpack_start_ENTRY := harness_unpack_start
unpack_start_ENFORCE := sqlite3VdbeRecordUnpack/contract_sqlite3VdbeRecordUnpack
unpack_start_REPLACE := sqlite3GetVarint32/contract_sqlite3GetVarint32 sqlite3VdbeSerialTypeLen/contract_sqlite3VdbeSerialTypeLen sqlite3VdbeMemSetNull/contract_sqlite3VdbeMemSetNull serialGet/contract_serialGet
unpack_start_LOOPS := contracts
unpack_start_CONTRACTS := legacy
include ../Makefile.common
