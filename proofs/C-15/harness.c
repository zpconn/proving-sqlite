#include "sqlite3.c"
#include "contracts/sqlite3GetVarint32.h"
#include "contracts/sqlite3VdbeSerialGet.h"
#include "contracts/sqlite3VdbeSerialTypeLen.h"
#include "contracts/sqlite3VdbeMemSetNull.h"
#include "contracts/sqlite3VdbeRecordUnpack.h"
#include <stdlib.h>

void harness_unpack(void){
  int nKey;
  size_t extent;
  u16 capacity;
  const void *bytes;
  UnpackedRecord *record;
  Mem *cells;
  KeyInfo *key;

  /* SETUP */
  __CPROVER_assume(extent <= 64);
  __CPROVER_assume(capacity <= 4);
  bytes = malloc(64);
  record = malloc(sizeof(UnpackedRecord));
  cells = malloc(sizeof(Mem) * 4);
  key = malloc(sizeof(KeyInfo));
  __CPROVER_assume(bytes != 0 && record != 0 && cells != 0 && key != 0);
  record->aMem = cells;
  record->pKeyInfo = key;
  record->nField = capacity;
  /* END SETUP */

  sqlite3VdbeRecordUnpack(nKey, bytes, record);
}
