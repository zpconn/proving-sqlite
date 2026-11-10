#include "sqlite3.c"
#include "contracts/sqlite3CorruptError.h"
u8 contract_sqlite3GetVarint32(const unsigned char *p, u32 *v)
  __CPROVER_ensures(1);

int contract_sqlite3VdbeRecordCompareWithSkip(int nKey1, const void *pKey1, UnpackedRecord *pPKey2, int bSkip)
  __CPROVER_ensures(1);

int contract_vdbeRecordCompareString(int nKey1, const void *pKey1, UnpackedRecord *pPKey2)
  __CPROVER_ensures(1);

void harness_vdbeRecordCompareString(void){
  int nKey1;
  const void *pKey1;
  UnpackedRecord *pPKey2;
  /* SETUP */
  pKey1 = malloc(16);
  pPKey2 = malloc(sizeof(UnpackedRecord));
  /* END SETUP */
  vdbeRecordCompareString(nKey1, pKey1, pPKey2);
}
