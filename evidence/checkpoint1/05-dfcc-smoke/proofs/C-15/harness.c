#include "sqlite3.c"
u8 contract_sqlite3GetVarint32(const unsigned char *p, u32 *v)
  __CPROVER_ensures(1);

void contract_sqlite3VdbeMemSetNull(Mem *pMem)
  __CPROVER_ensures(1);

void contract_sqlite3VdbeRecordUnpack(int nKey, const void *pKey, UnpackedRecord *p)
  __CPROVER_ensures(1);

void contract_sqlite3VdbeSerialGet(const unsigned char *buf, u32 serial_type, Mem *pMem)
  __CPROVER_ensures(1);

u32 contract_sqlite3VdbeSerialTypeLen(u32 serial_type)
  __CPROVER_ensures(1);

void harness_sqlite3VdbeRecordUnpack(void){
  int nKey;
  const void *pKey;
  UnpackedRecord *p;
  /* SETUP */
  pKey = malloc(16);
  p = malloc(sizeof(UnpackedRecord));
  /* END SETUP */
  sqlite3VdbeRecordUnpack(nKey, pKey, p);
}
