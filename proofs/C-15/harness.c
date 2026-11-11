#include "sqlite3.c"
#include "contracts/sqlite3GetVarint32.h"
#include "contracts/sqlite3VdbeSerialGet.h"
#include "contracts/serialGet.h"
#include "contracts/sqlite3VdbeSerialTypeLen.h"
#include "contracts/sqlite3VdbeMemSetNull.h"
#include "contracts/sqlite3VdbeRecordUnpack.h"
#include <stdlib.h>

void harness_unpack(void){
  int nKey;
  size_t mem_offset;
  u16 capacity;
  const void *bytes;
  void *allocation;
  UnpackedRecord *record;
  Mem *cells;
  KeyInfo *key;

  /* SETUP */
  __CPROVER_assume(nKey >= 0);
  mem_offset = ((sizeof(UnpackedRecord) + 7) / 8) * 8;
  bytes = malloc((size_t)(nKey > 0 ? nKey : 1) + 8);
  allocation = malloc(mem_offset + sizeof(Mem) * capacity);
  __CPROVER_assume(allocation != 0);
  record = allocation;
  cells = allocation + mem_offset;
  key = malloc(sizeof(KeyInfo));
  __CPROVER_assume(bytes != 0 && record != 0 && cells != 0 && key != 0);
  record->aMem = cells;
  record->pKeyInfo = key;
  record->nField = capacity;
  /* END SETUP */

  sqlite3VdbeRecordUnpack(nKey, bytes, record);
}
