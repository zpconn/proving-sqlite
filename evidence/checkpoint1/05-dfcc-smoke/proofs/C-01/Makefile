CARD := C-01
PROOFS := p0 p1
p0_ENTRY := harness_sqlite3PutVarint
p0_ENFORCE := sqlite3PutVarint/contract_sqlite3PutVarint
p0_REPLACE := putVarint64/contract_putVarint64
p1_ENTRY := harness_putVarint64
p1_ENFORCE := putVarint64/contract_putVarint64
p1_LOOPS := unwind
p1_UNWINDSET := putVarint64_wrapped_for_contract_checking.0:2,putVarint64_wrapped_for_contract_checking.1:2,putVarint64_wrapped_for_contract_checking.2:2
include ../Makefile.common
