#include "sqlite3.c"
#include "contracts/sqlite3DbMallocRaw.h"
#include "contracts/sqlite3VdbeAllocUnpackedRecord.h"
#include <stdlib.h>

void harness_alloc(void){
  KeyInfo *key;
  size_t extent;

  /* SETUP */
  __CPROVER_assume(extent <= sizeof(KeyInfo));
  key = malloc(extent);
  __CPROVER_assume(key != 0);
  /* END SETUP */

  sqlite3VdbeAllocUnpackedRecord(key);
}
