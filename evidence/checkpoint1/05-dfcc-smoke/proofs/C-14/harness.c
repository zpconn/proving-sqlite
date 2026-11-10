#include "sqlite3.c"
#include "contracts/sqlite3DbMallocRaw.h"
UnpackedRecord * contract_sqlite3VdbeAllocUnpackedRecord(KeyInfo *pKeyInfo)
  __CPROVER_ensures(1);

void harness_sqlite3VdbeAllocUnpackedRecord(void){
  KeyInfo *pKeyInfo;
  /* SETUP */
  pKeyInfo = malloc(sizeof(KeyInfo));
  /* END SETUP */
  sqlite3VdbeAllocUnpackedRecord(pKeyInfo);
}
