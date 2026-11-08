CARD := C-02
PROOFS := roundtrip
roundtrip_ENTRY := harness_roundtrip
roundtrip_LOOPS := unwind
roundtrip_UNWINDSET := putVarint64.0:10,putVarint64.1:10,putVarint64.2:10,sqlite3VarintLen.0:11,harness_roundtrip.0:10,harness_roundtrip.1:10,harness_roundtrip.2:10
roundtrip_COVER := sqlite3PutVarint putVarint64 sqlite3GetVarint sqlite3GetVarint32 sqlite3VarintLen
include ../Makefile.common
