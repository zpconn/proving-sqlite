CARD := C-11
PROOFS := isnan compare
isnan_ENTRY := harness_sqlite3IsNaN
isnan_ENFORCE := sqlite3IsNaN/contract_sqlite3IsNaN
isnan_LOOPS := none
compare_ENTRY := harness_sqlite3IntFloatCompare
compare_ENFORCE := sqlite3IntFloatCompare/contract_sqlite3IntFloatCompare
compare_REPLACE := sqlite3IsNaN/contract_sqlite3IsNaN
compare_LOOPS := none
include ../Makefile.common
