CARD := C-19
PROOFS := p0
p0_ENTRY := harness_vdbeRecordCompareString
p0_ENFORCE := vdbeRecordCompareString/contract_vdbeRecordCompareString
p0_REPLACE := sqlite3CorruptError/contract_sqlite3CorruptError sqlite3GetVarint32/contract_sqlite3GetVarint32 sqlite3VdbeRecordCompareWithSkip/contract_sqlite3VdbeRecordCompareWithSkip
p0_LOOPS := unwind
p0_UNWINDSET := vdbeRecordCompareString_wrapped_for_contract_checking.0:2,memcmp.0:17
include ../Makefile.common
