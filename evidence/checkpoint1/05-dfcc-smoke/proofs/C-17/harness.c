#include "sqlite3.c"
#include "contracts/sqlite3CorruptError.h"
#include "contracts/vdbeCompareMemString.h"
int contract_isAllZero(const char *z, int n)
  __CPROVER_ensures(1);

int contract_serialGet7(const unsigned char *buf, Mem *pMem)
  __CPROVER_ensures(1);

u8 contract_sqlite3GetVarint32(const unsigned char *p, u32 *v)
  __CPROVER_ensures(1);

int contract_sqlite3IntFloatCompare(i64 i, double r)
  __CPROVER_ensures(1);

int contract_sqlite3VarintLen(u64 v)
  __CPROVER_ensures(1);

int contract_sqlite3VdbeRecordCompareWithSkip(int nKey1, const void *pKey1, UnpackedRecord *pPKey2, int bSkip)
  __CPROVER_ensures(1);

void contract_sqlite3VdbeSerialGet(const unsigned char *buf, u32 serial_type, Mem *pMem)
  __CPROVER_ensures(1);

u32 contract_sqlite3VdbeSerialTypeLen(u32 serial_type)
  __CPROVER_ensures(1);

i64 contract_vdbeRecordDecodeInt(u32 serial_type, const u8 *aKey)
  __CPROVER_ensures(1);

void harness_sqlite3VdbeRecordCompareWithSkip(void){
  int nKey1;
  const void *pKey1;
  UnpackedRecord *pPKey2;
  int bSkip;
  /* SETUP */
  pKey1 = malloc(16);
  pPKey2 = malloc(sizeof(UnpackedRecord));
  /* END SETUP */
  sqlite3VdbeRecordCompareWithSkip(nKey1, pKey1, pPKey2, bSkip);
}
