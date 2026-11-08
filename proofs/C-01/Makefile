CARD := C-01
PROOFS := put64 put
put64_ENTRY := harness_putVarint64
put64_ENFORCE := putVarint64/contract_putVarint64
put64_LOOPS := unwind
put64_UNWINDSET := putVarint64_wrapped_for_contract_checking.0:10,putVarint64_wrapped_for_contract_checking.1:10,putVarint64_wrapped_for_contract_checking.2:10
put_ENTRY := harness_sqlite3PutVarint
put_ENFORCE := sqlite3PutVarint/contract_sqlite3PutVarint
put_REPLACE := putVarint64/contract_putVarint64
put_LOOPS := none
include ../Makefile.common
