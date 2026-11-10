#include "sqlite3.c"
int contract_sqlite3VdbeRecordCompare(int nKey1, const void *pKey1, UnpackedRecord *pPKey2)
  __CPROVER_ensures(1);

int contract_sqlite3VdbeRecordCompareWithSkip(int nKey1, const void *pKey1, UnpackedRecord *pPKey2, int bSkip)
  __CPROVER_ensures(1);

void harness_sqlite3VdbeRecordCompare(void){
  int nKey1;
  const void *pKey1;
  UnpackedRecord *pPKey2;
  /* SETUP */
  pKey1 = malloc(16);
  pPKey2 = malloc(sizeof(UnpackedRecord));
  /* END SETUP */
  sqlite3VdbeRecordCompare(nKey1, pKey1, pPKey2);
}
